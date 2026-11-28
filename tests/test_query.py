#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_query.py
# Days of candles made to be what queries ask about: on even days Asia
# consolidates, London takes its low and New York then its high; on odd
# days price rises all day. Then the window of View ▸ Queries.
#
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

import numpy as np
import m15
import query
import sandbox

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

def path(turns, hours):
	"""the price at hours along turns [(hour, price)]"""
	hs, ps = zip(*turns)
	return np.interp(hours, hs, ps)

UP = [(-6, 100), (-4, 100), (0, 104), (2, 103), (3, 90), (9, 130), (17, 140)]	# Asia 100..104, London below, NY above
DOWN = [(-6, 60), (17, 140)]
rows = []
days = [n for n in range(query.dayn(date(2026, 1, 5)), query.dayn(date(2026, 2, 28))) if (n + 3) % 7 < 5]
for k, n in enumerate(days):
	turns = UP if k % 2 == 0 else DOWN
	base = 1000 * k
	for c in range(92):	# m15 from 18:00 to 17:00
		h0, h1 = -6 + c / 4, -6 + (c + 1) / 4
		o, cl = (float(x) + base for x in path(turns, [h0, h1]))
		hi, lo = max(o, cl) + 0.25, min(o, cl) - 0.25
		wall = n * 86400 + int(h0 * 3600)
		t = wall - m15.nyoffset(wall + 5 * 3600)
		rows.append([t, o, hi, lo, cl])
rows = np.array(rows, dtype=float)
d = tempfile.mkdtemp()
m15.writerows(os.path.join(d, m15.filename("TEST", rows[0][0])), rows)
# m5 from them: each m15 candle in three
low = []
for t, o, hi, lo, cl in rows:
	ps = np.linspace(o, cl, 4)
	for i in range(3):
		a, b = ps[i], ps[i + 1]
		low.append([t + 300 * i, a, max(a, b) + 0.1, min(a, b) - 0.1, b])
m15.writerows(os.path.join(d, m15.filename("TEST", low[0][0], 5)), np.array(low))

j = query.Journal(d)
n = len(days)
up = (n + 1) // 2
def one(text, **kw):
	r = j.run(text, **kw)
	print(r.text())
	return r

r = one("count day")
check(r.rows == [[str(n)]], "count day counts the days")
r = one("share day takes asia.low then asia.high")
check(r.rows[0][0] == f"{100 * up / n:.0f}%", "the days that took Asia's low and then its high")
r = one("share day soups asia.low")
check(r.rows[0][0] == f"{100 * up / n:.0f}%", "a turtle soup: Asia's low taken, back above it, not below again")
r = one("share day soups asia.high")
check(r.rows[0][0] == "0%", "no soup when price goes on past the high")
r = one("share day takes asia.high then asia.low")
check(r.rows[0][0] == "0%", "and none the other way")
r = one("dist day.cond")
got = dict((row[0], row[1]) for row in r.rows)
check(got.get("uptrend") == n, "the days rising are uptrends")
r = one("dist (when day takes asia.low).session")
got = dict((row[0], row[1]) for row in r.rows)
check(got.get("london") == up and got.get("none") == n - up, "Asia's low goes in London; the other days, never")
r = one("dist (when day takes asia.high).hour tf 5")
check(r.unit == "day" and j.models[5].c.tf == 5, "tf 5 takes the m5 candles")
r = one("list day where day takes asia.low")
check(len(r.periods) == up and all(p.kind == "day" for p in r.periods), "list gives the days")
r = one("dist week.low.day")
check(r.unit == "week", "a week's low: weeks are counted")
r = one("avg day.range by weekday")
check(r.headers[0] == "weekday" and len(r.rows) == 5, "by weekday")
r = one("share mon is uptrend in 2026-01")
check(all(p.date().month == 1 for p in r.periods), "in a month")
r = one("dist day.cond by asia.cond")
check(r.chart == "grid", "two things at once make a grid")
r = one("dist session.cond by session")
check(r.unit == "session" and [row[0] for row in r.rows] == ["asia", "london", "nyam", "nypm"], "sessions, any of them, by session")
r = one("count session")
check(r.rows == [[str(4 * n)]], "four sessions a day")
r = one("share session takes prev session.low by session")
check(dict((row[0], row[1]) for row in r.rows)["london"] == f"{100 * up / n:.0f}%", "the session before is the one before it, of any name")
r = one("dist prev day.dir")
check(r.n == n, "the day before")
try:
	j.run("dist day.cond wher asia is up")
	check(False, "an error")
except query.QueryError as e:
	check(e.pos == 14, "an error says where it is")
try:
	j.run("dist foo.high")
	check(False, "an error")
except query.QueryError as e:
	check("what is foo" in str(e), "and what is wrong")
# the thresholds in conditions.txt
query.writedefaults(d)
with open(os.path.join(d, query.CONDFILE), "a") as f:
	f.write("trend = 0.999\n")
r = one("dist day.cond")
check("uptrend" not in [row[0] for row in r.rows], "conditions.txt changes what a trend is")
os.remove(os.path.join(d, query.CONDFILE))
# only the days a search leaves
r = j.run("count day", only=({days[0], days[1]}, set()))
check(r.rows == [["2"]], "only the days the list leaves")

# opening gaps and FVGs
m = j.model(15)
g = m.gap("rthog", days[3])
c = m.c
k = int(np.searchsorted(c.wall, days[2] * 86400 + 16.25 * 3600)) - 1
o = int(np.searchsorted(c.wall, days[3] * 86400 + 9.5 * 3600))
check(g is not None and g.more["settle"] == c.c[k] and g.more["open"] == c.o[o] and g.more["dir"] == "up",
	"the rthog: the close at 16:15 the day before to the open at 09:30")
check(abs(g.attr("ce") - (g.low + g.high) / 2) < 1e-9 and g.attr("q4").low == g.attr("uq"), "its ce and quadrants")
check(m.gap("ndog", days[0 + 5]) is None and m.gap("nwog", days[5]) is not None and m.gap("ndog", days[6]) is not None,
	"no ndog on Mondays: that is the nwog")
r = one("dist day.close.rthog")
check(dict((row[0], row[1]) for row in r.rows).get("above") == n - 1, "price above the gap")
r = one("count day where asia.high inside day and not asia.low inside prev day")
check(r.rows == [[str(n)]], "inside a period")
r = one("share nyam touches rthog.ce")
check(r.rows[0][0] == "0%", "the gap's ce is not touched after it is made: price is far above")
r = one("avg day.fvgs")
check(float(r.rows[0][0]) > 10, "FVGs of a day")
r = one("dist nyam.lastfvg.dir")
check(dict((row[0], row[1]) for row in r.rows).get("bull", 0) > 0, "the last FVG and its kind")
r = one("avg nyam.fvgs5")
check(float(r.rows[0][0]) > 0 and 5 in j.models, "FVGs of another time frame")
r = one("share nyam touches nyam.fvg.ce")
check(r.n == n, "and their levels")

# rejects: to a level, or a wick past it, and away without a close past it
def candles(bars):
	t0 = days[0] * 86400 + 3 * 3600
	return query.Model(query.Candles.fromrows(np.array([[t0 + 900 * k - m15.nyoffset(t0 + 5 * 3600), *b]
		for k, b in enumerate(bars)], dtype=float)))
wick = candles([(110, 111, 105, 106), (106, 107, 99, 102), (102, 108, 101, 107), (107, 113, 106, 112)])
check(wick.reject(0, 4, 100, 1, 10) == 1, "a wick through the level, closing back, and away: a reject")
near = candles([(110, 111, 105, 106), (106, 107, 100.5, 102), (102, 108, 101, 107), (107, 113, 106, 112)])
check(near.reject(0, 4, 100, 1, 10) == 1 and near.reject(0, 4, 100, 0.2, 10) is None, "near it is a reject too; farther, not")
through = candles([(110, 111, 105, 106), (106, 107, 98, 99), (99, 108, 98, 107), (107, 113, 106, 112)])
check(through.reject(0, 4, 100, 1, 10) is None, "a close past it is no reject")
nobounce = candles([(110, 111, 105, 106), (106, 107, 99, 102), (102, 105, 101, 104), (104, 106, 103, 105)])
check(nobounce.reject(0, 4, 100, 1, 10) is None, "nor is staying by it")
under = candles([(90, 95, 89, 94), (94, 101, 93, 96), (96, 97, 88, 89)])
check(under.reject(0, 3, 100, 1, 10) == 1, "and from below, a resistance")
z = query.Zone("fvg", 100, 104, 0, 0, wick, dir="bull")
run = query.Run(wick, query.Parser("count day").query())
p = wick.day(days[0])
check(run.fill(p, z, None) == 1, "a bullish FVG is filled when price trades down to its low")
check(query.Run(nobounce, query.Parser("count day").query()).fill(p, query.Zone("fvg", 98, 104, 0, 0, nobounce, dir="bull"), None) is None,
	"and not before")
r = one("share day fills rthog")
check(r.rows[0][0] == "0%", "the gaps up of the rising days are not filled")
r = one("share day rejects asia.high")
check(r.rows[0][0] == f"{100 * up / n:.0f}%", "the Asia high rejected when London falls from it; taken on the rising days")

# each condition, from what price did in the day
shapes = {
	"consolidation": [(-6, 100), (0, 110), (6, 90), (17, 101)],	# up, down, back near the open
	"choppy": [(-6, 100), (-2, 110), (1, 100), (4, 110), (7, 100), (10, 110), (17, 111)],	# back and forth, closing high
	"downreversal": [(-6, 100), (2, 120), (17, 85)],	# up, then down past the open
	"upretrace": [(-6, 100), (8, 140), (17, 120)],	# up, giving back half
	"uptrend": [(-6, 100), (17, 140)],
	"mixed": [(-6, 100), (-2, 97), (10, 110), (17, 107)],	# up some, not near its high
}
crows = []
cdays = days[:len(shapes)]
for n, turns in zip(cdays, shapes.values()):
	for c in range(92):
		h0, h1 = -6 + c / 4, -6 + (c + 1) / 4
		o, cl = (float(x) for x in path(turns, [h0, h1]))
		wall = n * 86400 + int(h0 * 3600)
		crows.append([wall - m15.nyoffset(wall + 5 * 3600), o, max(o, cl), min(o, cl), cl])
cm = query.Model(query.Candles.fromrows(np.array(crows)))
got = [cm.cond(cm.day(n)) for n in cdays]
print(got)
want = ["consolidation", "consolidation", "downreversal", "upretrace", "uptrend", "mixed"]
check(got == want, "the conditions from what price did: " + ", ".join(shapes))
check(cm.swings(cm.day(cdays[1])) >= 4 and cm.swings(cm.day(cdays[4])) == 1, "swings counts the back and forth")

# the window, from the gear
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from mainwin import MainWindow
win = MainWindow()
win.openjournal(d)
win.resize(1100, 700)
win.show()
app.processEvents()
check(win.queryact in win.toolsmenu.actions(), "Queries is in the gear's menu")
win.queryact.trigger()
app.processEvents()
qw = win.querywin
check(qw is not None and qw.saved.count() == len(__import__("querywin").EXAMPLES), "it opens, with examples")
qw.edit.setEditText("dist (when day takes asia.low).session")
qw.run()
app.processEvents()
check(qw.res is not None and qw.table.rowCount() == len(qw.res.rows) and not qw.error.isVisible(), "a query shows its table")
img = qw.chart.grab().toImage()
blue = sum(1 for x in range(0, img.width(), 3) for y in range(0, img.height(), 3)
	if img.pixelColor(x, y).blue() > 180 and img.pixelColor(x, y).red() < 100)
check(blue > 20, "and its chart")
qw.grab().save(os.path.join(d, "queries.png"))
qw.edit.setEditText("dist day.cond by weekday")
qw.run()
app.processEvents()
qw.grab().save(os.path.join(d, "queries-grid.png"))
print("window", os.path.join(d, "queries.png"))
qw.edit.setEditText("dist day.cond whre")
qw.run()
check(qw.error.isVisible() and "expected" in qw.error.text(), "a wrong query says why")
import querywin
querywin.writequeries(d, [("asia", "share day takes asia.low then asia.high")])
qw.fillsaved()
check(qw.saved.count() == 1 and querywin.readqueries(d) == [("asia", "share day takes asia.low then asia.high")],
	"queries saved in the journal")
check(qw.tfbox.itemText(1) == "m2", "m2 is a time frame of the window")
le = qw.edit.lineEdit()
le.setText("")
le.setFocus()
from PySide6.QtTest import QTest
QTest.keyClicks(le, "dist day.c")
app.processEvents()
check(qw.words.completionCount() >= 2 and qw.words.popup().isVisible(), "the line offers words as they are typed")
qw.complete("cond")
check(le.text() == "dist day.cond", "and puts the one picked in place")
QTest.keyClicks(le, " whe")
qw.complete("where")
check(le.text() == "dist day.cond where", "keywords too")
qw.words.popup().hide()
qw.edit.setEditText("list day where day takes asia.low")
qw.run()
qw.showperiod(0)
app.processEvents()
check(win.datamode and win.datakey == ("d", qw.res.periods[0].date()), "a day of a list shows in the data view")
