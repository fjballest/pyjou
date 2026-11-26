#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_periods.py
# charts of days, weeks and months in the data view.
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
import time
from datetime import date, datetime, timezone

import numpy as np

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
import m15
import mainwin
import indicators
import ocrworker
from dataview import Geom
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])

check([m15.tfname(t) for t in (m15.DAILY, m15.WEEKLY, m15.MONTHLY)] == ["D", "W", "M"], "D, W and M time frames")

# 70 weekdays of m15 from Sunday 18:00, 6 Sep 2026
j = tempfile.mkdtemp()
src = tempfile.mkdtemp()
first = int(datetime(2026, 9, 6, 22, 0, tzinfo=timezone.utc).timestamp())
rng = np.random.default_rng(5)
rows = []
p = 1000.0
for day in range(98):
	if day % 7 in (5, 6):
		continue
	for k in range(92):
		t = int(m15.daystart([m15.Data.dayn(date(2026, 9, 7)) + day])[0]) + k * 900
		o = p
		p = round(p + rng.normal(0, 2), 2)
		rows.append((t, o, max(o, p) + 1, min(o, p) - 1, p))
with open(os.path.join(src, "MNQ.m15.csv"), "w") as f:
	f.write("time,open,high,low,close\n")
	for r in rows:
		f.write("%d,%g,%g,%g,%g\n" % r)
m15.importfile(j, os.path.join(src, "MNQ.m15.csv"))
a = np.array(rows)

data = m15.Data(j)
d = date(2026, 11, 4)
st, o, h, l, c, en = data.periodbars("d", d, m15.DAILY)
last = (a[:, 0] >= st[-1]) & (a[:, 0] < en[-1])
check(len(st) == 43 and o[-1] == a[last][0, 1] and h[-1] == a[last, 2].max() and c[-1] == a[last][-1, 4],
	"daily candles up to the day picked")
st, o, h, l, c, en = data.periodbars("w", date(2026, 10, 26), m15.WEEKLY)
check(len(st) == 8 and m15.dayof(st[-1]) == date(2026, 10, 26) and m15.dayof(en[-1] - 60) == date(2026, 10, 30),
	"weekly ones up to the week picked")
st, o, h, l, c, en = data.periodbars("d", d, m15.MONTHLY)
check(len(st) == 3 and m15.dayof(st[-1]) == date(2026, 11, 2) and m15.dayof(en[-1] - 60) == d, "monthly ones, the last so far")

g = Geom(data, "d", d, m15.DAILY)
check(g.periods and g.ok and abs(g.tx(int(g.starts[10])) - 10) < 1e-9, "a candle a step on the chart")
x, y = g.X(20.5), g.Y(1000)
hours, price = g.when(x, y)
q = g.where(hours, price)
check(q is not None and abs(q[0] - x) < 1 and abs(q[1] - y) < 1, "the crosshair goes to the same time in other charts")
v = g.zoomed("t", 30, 0.01)
check(v is not None and abs((v[3] - v[2]) - 10) < 1e-9, "zooming in shows ten candles at least")
check(g.lastend() == int(g.ends[-1]), "the last candle shown ends the day picked")

w = mainwin.MainWindow(j)
w.show()
app.processEvents()
w.setdatamode(True)
names = [w.tfcombo.itemText(i) for i in range(w.tfcombo.count())]
check(names[-3:] == ["D", "W", "M"], "picked on the toolbar: " + str(names))
w.setdatatf(m15.DAILY)
w.showdata(("d", d), force=True)
check(w.datageom.periods and w.datashowntf == m15.DAILY and "Data D" in w.titlelabel.text(), "the data view draws days")
w.showdata(("w", date(2026, 10, 26)), force=True)
check(w.datageom.kind == "w" and m15.dayof(w.datageom.starts[-1]) == date(2026, 10, 30), "a week shows the days up to its Friday")
w.filltfwindows()
check("New Window in M" in [a.text() for a in w.newwinmenu.actions()], "and new windows in months")

script = os.path.join(src, "Range.txt")
with open(script, "w") as f:
	f.write('''indicator("Range", overlay = true)
wh = request.security(syminfo.tickerid, "W", high, lookahead = barmerge.lookahead_on)
if barstate.islast
    label.new(bar_index, high, timeframe.period + " " + str.tostring(wh))
    line.new(bar_index - 5, wh, bar_index, wh)
''')
indicators.importfiles([script])
w.showdata(("d", d), force=True)
end = time.time() + 60
while w.datapending and time.time() < end:
	app.processEvents()
	time.sleep(0.01)
rs, _ = indicators.results(w.data, w.getlow, w.datageom, w.datashowntf)
wk = (a[:, 0] >= data.periodbars("d", d, m15.WEEKLY)[0][-1]) & (a[:, 0] < data.periodbars("d", d, m15.WEEKLY)[5][-1])
check(rs and rs[0].error is None and [lb.text for lb in rs[0].labels] == ["D " + mainwin.m15.price(a[wk, 2].max()).replace(".00", "")],
	"indicators run on days too: " + str([lb.text for lb in rs[0].labels]))
print("ALL OK")
os._exit(0)
