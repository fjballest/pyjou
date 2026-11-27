#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_pine.py
# the Pine subset: parsing, what scripts compute bar by bar, the higher time
# frames, and indicators drawn on the data charts.
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
from datetime import date, datetime, timezone

import numpy as np

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

import pine
from pine import runtime as R
from pine.parse import parse, PineError
import m15

def bars(n, tf=15, start=None):
	"""n candles of tf minutes from Monday 2 Nov 2026 00:00 UTC: a Series"""
	t0 = start or int(datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc).timestamp())
	t = np.arange(n) * tf * 60 + t0
	c = 100 + np.arange(n) % 7
	o = c - 1
	return R.Series(t * 1000, o, c + 1, o - 1, c, (t + tf * 60) * 1000, str(tf))

def run(src, S=None, sources=None):
	S = S or bars(50)
	r = pine.run(pine.Script(src, "test"), S, sources or (lambda k: None))
	if r.error:
		print(r.error)
		print(getattr(r, "trace", ""))
	return r

def labels(r):
	return [lb.text for lb in r.labels]

# lines and blocks
src = '''
//@version=6
indicator("T", overlay = true,
     max_labels_count = 500)
x = 1 +
     2
f(a, b = 3) =>
    a * b
if bar_index == 0
    label.new(bar_index, 0, str.tostring(x) + " " + str.tostring(f(2)) + " " + str.tostring(f(2, b = 5)))
'''
r = run(src)
check(r.error is None and labels(r) == ["3 6 10"], "continuation lines, functions with defaults and named arguments")

# var, history, := and loops
src = '''
indicator("T")
var int n = 0
n += 1
float s = 0
for i = 1 to 3
    s += i
for i = 3 to 1
    s += 0
c = close - close[1]
if barstate.islast
    label.new(bar_index, 0, str.tostring(n) + " " + str.tostring(s) + " " + str.tostring(n[2]) + " " + str.tostring(c, "#.##"))
'''
r = run(src, bars(10))
S = bars(10)
check(labels(r) == ["10 6 8 " + R.tostring(S.c[9] - S.c[8], "#.##")], "var, history of variables and of built-ins, for loops")

# types, methods, arrays, switch, tuples, if as a value
src = '''
indicator("T")
type Zone
    float hi
    float lo = 0
    array<int> marks
method width(Zone z) =>
    z.hi - z.lo
method add(Zone z, int k) =>
    z.marks.push(k)
    z.marks.size()
pair(x) =>
    [x, x * 2]
kind(int k) =>
    switch k
        1 => "one"
        2 => "two"
        => "many"
var zones = array.new<Zone>()
if bar_index < 3
    zones.push(Zone.new(10 + bar_index, marks = array.new<int>()))
[a, b] = pair(4)
v = if a > 3
    "big"
else
    "small"
if barstate.islast
    z = zones.get(2)
    z.add(5)
    label.new(bar_index, 0, str.tostring(z.width()) + " " + str.tostring(z.add(6)) + " " + kind(2) + kind(7) + " " + str.tostring(b) + " " + v + " " + str.tostring(zones.size()))
'''
r = run(src, bars(5))
check(labels(r) == ["12 2 twomany 8 big 3"], "types with defaults, methods, arrays, switch, tuples and if values")

# block scopes: the same name in two blocks, and a global declared later
src = '''
indicator("T")
if bar_index > 0
    w = 1
    label.new(bar_index, 0, "a" + str.tostring(w))
var array<int> w = array.new<int>()
w.push(bar_index)
if barstate.islast
    label.new(bar_index, 0, str.tostring(w.size()))
'''
r = run(src, bars(4))
check(labels(r)[-1] == "4" and labels(r)[0] == "a1", "a block's variable is not the global of the same name")

# call sites keep their own state; ta functions
src = '''
indicator("T")
up(src) => ta.change(src) > 0
ph = ta.pivothigh(high, 2, 2)
var int pivots = 0
if not na(ph)
    pivots += 1
a = up(close)
b = up(open[3])
s = ta.sma(close, 3)
if barstate.islast
    label.new(bar_index, 0, str.tostring(pivots) + " " + str.tostring(a) + str.tostring(b) + " " + str.tostring(s, "#.###"))
'''
S = bars(30)
r = run(src, S)
want = sum(1 for k in range(2, 28) if all(S.h[k] > S.h[j] for j in (k - 2, k - 1, k + 1, k + 2)))
check(labels(r) == [f"{want} {R.tostring(S.c[29] > S.c[28])}{R.tostring(S.o[26] > S.o[25])} {R.tostring(sum(S.c[27:30]) / 3, '#.###')}"],
	"pivots, and ta state kept for each call site")

# time
src = '''
indicator("T")
if barstate.islast
    label.new(bar_index, 0, str.format_time(time, "yyyy-MM-dd HH:mm", "America/New_York") + " " + str.tostring(hour) + " " + str.tostring(dayofweek == dayofweek.monday) + " " + str.tostring(not na(time(timeframe.period, "0930-1600", "America/New_York"))))
'''
r = run(src, bars(4 * 15))	# Monday 00:00 UTC + 14:45, 09:45 New York
check(labels(r) == ["2026-11-02 09:45 9 true true"], "times in New York, sessions")

# drawings: the oldest go past max_lines_count
src = '''
indicator("T", max_lines_count = 5)
l = line.new(bar_index, low, bar_index, high)
if bar_index == 3
    l.delete()
'''
r = run(src, bars(20))
check(len(r.lines) == 5 and r.lines[-1].x1 == 19, "the oldest lines go past the limit")

# errors
try:
	parse("x = (1 +\n")
	check(False, "a parse error")
except PineError:
	check(True, "bad scripts are refused")
r = run('indicator("T")\nx = undefinedthing + 1\n')
check(r.error and "undefinedthing" in r.error, "and named: " + r.error)
r = run('indicator("T")\na = array.new<float>()\nx = a.get(3)\n')
check(r.error and "IndexError" in r.error and "(line 3) at bar 0" in r.error, "runtime errors say where: " + r.error)


# higher and lower time frames from the journal's data
from pine.feed import Feed

def mkdata(rows, tf):
	d = m15.Data.__new__(m15.Data)
	d.dir, d.tf, d.files, d.symbol = None, tf, [], "MNQ"
	d.setrows(rows)
	return d

rng = np.random.default_rng(3)
first = int(datetime(2026, 11, 1, 23, 0, tzinfo=timezone.utc).timestamp())	# Sunday 18:00 New York
t = []
for day in range(5):
	t.append(first + day * 86400 + np.arange(23 * 60) * 60)
t = np.concatenate(t)
c = 1000 + np.cumsum(rng.normal(0, 1, len(t))).round(2)
o = np.r_[c[0], c[:-1]]
rows = np.column_stack([t, o, np.maximum(o, c) + 0.5, np.minimum(o, c) - 0.5, c])
m1 = mkdata(rows, 1)
data = mkdata(m15.resample(rows, 15), 15)
upto = int(datetime(2026, 11, 5, 15, 0, tzinfo=timezone.utc).timestamp())	# Thursday 10:00 New York
feed = Feed(data, m1, upto)
S = feed.chart(15, 5000)
check(S.t[-1] // 1000 + 900 == upto and S.tfp == "15", "the chart's bars end with the last one shown")
days = feed(("D", 1))
check(days.n == 4 and days.t[0] // 1000 == first, "days start at 18:00 New York")
src = '''
indicator("T")
[on, d0] = request.security(syminfo.tickerid, "D", [high, time], lookahead = barmerge.lookahead_on)
off = request.security(syminfo.tickerid, "D", high)
prev = request.security(syminfo.tickerid, "D", high[1], lookahead = barmerge.lookahead_on)
lows = request.security_lower_tf(syminfo.tickerid, "1", low)
if barstate.islast or bar_index == 10
    label.new(bar_index, 0, str.tostring(on) + " " + str.tostring(off) + " " + str.tostring(prev) + " " + str.tostring(lows.size()) + " " + str.tostring(lows.min()))
'''
r = run(src, S, feed)
i = 10
ends = [days.t[k + 1] // 1000 for k in range(3)] + [upto]
dayhigh = [float(rows[(rows[:, 0] >= days.t[k] // 1000) & (rows[:, 0] < ends[k]), 2].max()) for k in range(4)]
k10 = days.find(S.t[i])
last = S.n - 1
lows10 = rows[(rows[:, 0] >= S.t[i] // 1000) & (rows[:, 0] < S.t[i] // 1000 + 900), 3]
want10 = f"{R.tostring(dayhigh[k10])} {R.tostring(dayhigh[k10 - 1]) if k10 else 'NaN'} {R.tostring(dayhigh[k10 - 1]) if k10 else 'NaN'} 15 {R.tostring(float(lows10.min()))}"
check(labels(r)[0] == want10, "a day's high with and without lookahead, its history, and the m1 lows in a bar")
check(labels(r)[1].split()[:2] == [R.tostring(dayhigh[3])] * 2, "on the last bar, the day so far either way")
check(labels(r)[1].split()[2] == R.tostring(dayhigh[2]), "and the day before's high, from its history")

# on the data charts
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
import mainwin
import sandbox
import indicators
import ocrworker
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])

j = tempfile.mkdtemp()
src = tempfile.mkdtemp()
with open(os.path.join(src, "MNQ.m15.csv"), "w") as f:
	f.write("time,open,high,low,close\n")
	for row in m15.resample(rows, 15):
		f.write("%d,%g,%g,%g,%g\n" % tuple(row))
m15.importfile(j, os.path.join(src, "MNQ.m15.csv"))
script = os.path.join(src, "Highs.txt")
with open(script, "w") as f:
	f.write('''//@version=6
indicator("Highs", overlay = true)
dh = request.security(syminfo.tickerid, "D", high, lookahead = barmerge.lookahead_on)
var line l = na
if barstate.islast
    l := line.new(bar_index - 20, dh, bar_index, dh, color = color.fuchsia, width = 3, extend = extend.both)
    label.new(bar_index, dh, "day high", style = label.style_label_left)
''')
import time
def settle(w, seconds=60):
	"""wait for the runs of w's chart, made in the background"""
	end = time.time() + seconds
	while w.datapending and time.time() < end:
		app.processEvents()
		time.sleep(0.01)
	app.processEvents()

w = mainwin.MainWindow(j)
w.show()
app.processEvents()
w.setdatamode(True)
key = ("d", date(2026, 11, 4))
w.showdata(key, force=True)
check(w.dataoverlay is None, "no indicators until some are imported")
before = QImage(w.datapath)
names = indicators.importfiles([script])
check(names == ["Highs"] and indicators.enabled() == ["Highs"], "imported, and on")
w.indicatorschanged()
check(w.datapending, "run in the background")
settle(w)
check(not w.datapending, "and drawn when done")
check(w.dataoverlay is not None and isinstance(w.view.pixitem, mainwin.ChartItem) and w.view.pixitem.overlay is w.dataoverlay,
	"what it draws goes on the chart and on its sharp redraw")
after = QImage(w.datapath)
fuchsia = QColor(224, 64, 251)
def hasfuchsia(img):
	for y in range(0, img.height(), 2):
		for x in range(0, img.width(), 4):
			c = img.pixelColor(x, y)
			if abs(c.red() - fuchsia.red()) < 30 and abs(c.green() - fuchsia.green()) < 30 and abs(c.blue() - fuchsia.blue()) < 30:
				return True
	return False
check(not hasfuchsia(before) and hasfuchsia(after), "the line is drawn in the chart's image, the one captures take")
w.fillindicators()
acts = [a for a in w.indmenu.actions() if a.isCheckable()]
check([a.text() for a in acts] == ["Highs"] and acts[0].isChecked(), "the Indicators menu lists it, checked")
acts[0].setChecked(False)
check(indicators.enabled() == [] and w.dataoverlay is None and not hasfuchsia(QImage(w.datapath)), "unchecked, it goes away")
acts[0].setChecked(True)
settle(w)
w2 = mainwin.MainWindow(j)
check(indicators.enabled() == ["Highs"], "the choice is remembered")
w.datazooms[(key[0], key[1], w.datashowntf)] = (w.datageom.top, w.datageom.bot, 2.0, 9.0)
w.showdata(key, force=True)
check(w.datapending and w.dataoverlay is not None, "zoomed in, the last run of the chart is shown while the new one is made")
w.addchart()
check(not w.datapending, "a capture waits for the runs")
w.journal.load()
caps = [e for e in w.journal.entries if e.day == date(2026, 11, 4)]
check(caps and hasfuchsia(QImage(w.journal.path(caps[-1]))), "Add Chart as Capture keeps what the indicators drew")
del w.datazooms[(key[0], key[1], w.datashowntf)]
w.showdata(key, force=True)
settle(w)

# inputs
src2 = os.path.join(src, "Inputs.txt")
with open(src2, "w") as f:
	f.write('''indicator("Inputs", overlay = true)
G = "Main"
n = input.int(3, "Count", minval = 1, maxval = 9, group = G)
c = input.color(color.fuchsia, "Color", group = G, inline = "a")
w = input.int(2, "", options = [1, 2, 3], group = G, inline = "a")
on = input.bool(true, "Show", group = G)
s = input.string("dotted", "Style", options = ["solid", "dashed", "dotted"])
if barstate.islast and on
    label.new(bar_index, close, str.tostring(n) + " " + str.tostring(w) + " " + s)
''')
indicators.importfiles([src2])
w.indicatorschanged()
settle(w)
def lastlabel():
	rs, _ = indicators.results(w.data, w.getlow, w.datageom, w.datashowntf)
	r = [r for r in rs if r.title == "Inputs"][0]
	return [lb.text for lb in r.labels]
check(lastlabel() == ["3 2 dotted"], "inputs take their defaults")
seen = {}
def edit(dlg):
	ed = {spec.title: (get, put, wd) for spec, get, put, wd in dlg.editors}
	seen.update({k: type(v[2]).__name__ for k, v in ed.items()})
	ed["Count"][1](5)
	ed[""][1](3)
	ed["Style"][1]("solid")
	return True
w.indicatorinputs("Inputs", edit)
check(seen == {"Count": "QSpinBox", "Color": "QPushButton", "": "QComboBox", "Show": "QCheckBox", "Style": "QComboBox"},
	"the inputs dialog has a field for each, as TradingView: " + str(seen))
settle(w)
check(lastlabel() == ["5 3 solid"], "and the indicator runs with the new values")
check(set(indicators.inputs("Inputs")) == {"Main|Count|", "Main||a", "|Style|"}, "only those changed are kept")
w.indicatorinputs("Inputs", lambda dlg: [put(spec.defval) for spec, get, put, wd in dlg.editors] and True)
settle(w)
check(lastlabel() == ["3 2 dotted"] and indicators.inputs("Inputs") == {}, "back to the defaults")
indicators.remove("Inputs")

# the session rectangles
check(w.sessionsact.isChecked(), "session rectangles are drawn")
w.setsessions(False)
check(not mainwin.dataview.SHOWSESSIONS and mainwin.settings().value("datasessions") in (False, "false"), "and not, remembered")
w.setsessions(True)

with open(script, "w") as f:
	f.write('indicator("Bad")\nx = nosuchname\n')
indicators.importfiles([script])
w.indicatorschanged()
settle(w)
w.showdata(key, force=True)
check("Bad: line 2: unknown name 'nosuchname'" in w.statusBar().currentMessage(), "a script that fails says why")
print("ALL OK")
os._exit(0)
