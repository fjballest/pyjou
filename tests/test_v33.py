#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_periods.py
# 3.3: profile lines on or off, scrolls by the edges and center of data
# charts, zooming that keeps the axes, indicator folders, room past the last bar.
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

from PySide6.QtCore import QPoint, QPointF, Qt, QEvent
from PySide6.QtGui import QWheelEvent
import dataview

def settle():
	end = time.time() + 60
	while time.time() < end:
		app.processEvents()
		if not w.datapending and not getattr(w, "dataviewsoon", False):
			break
		time.sleep(0.01)
	app.processEvents()

w = mainwin.MainWindow(j)
w.resize(1400, 900)
w.show()
app.processEvents()
w.setdatamode(True)
w.showdata(("d", d), force=True)
settle()
g = w.datageom
check(g is not None and g.ok and w.view.mode == "fit", "a day of the data shown")

# the profile lines
calls = []
real = data.profile
w.data.profile = lambda *a, **k: (calls.append(k), real(*a, **k))[1]
w.redrawdata()
check(any(k.get("prices") for k in calls), "the profile is drawn")
calls.clear()
w.setprofilelines(False)
check(not any(k.get("prices") for k in calls) and not w.view.hidden, "Profile Lines off: no profile, the drawings still shown")
check(mainwin.settings().value("dataprofile") in (False, "false"), "and it is remembered")
w.setprofilelines(True)
calls.clear()
w.redrawdata()
check(any(k.get("prices") for k in calls), "on again")

def scene2view(x, y):
	return QPointF(w.view.mapFromScene(QPointF(x, y)))

def wheel(x, y, dy=120, dx=0, pixels=False):
	at = scene2view(x, y)
	ev = QWheelEvent(at, QPointF(w.view.viewport().mapToGlobal(at.toPoint())), QPoint(dx, dy) if pixels else QPoint(),
		QPoint(0, 0) if pixels else QPoint(dx, dy), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
		Qt.ScrollPhase.NoScrollPhase, False)
	return ev

g = w.datageom
cx, cy = g.L + g.pw / 2, g.T + g.ph / 2
check(w.wheelzone(g, QPointF(cx, cy)) == "z", "a scroll at the center zooms")
check(w.wheelzone(g, QPointF(g.L + 5, cy)) == "p" and w.wheelzone(g, QPointF(g.L + g.pw - 5, cy)) == "p", "by the left and right edges it scales the prices")
check(w.wheelzone(g, QPointF(cx, g.T + 5)) == "t" and w.wheelzone(g, QPointF(cx, g.T + g.ph - 5)) == "t", "by the top and bottom ones the times")
check(w.wheelzone(g, QPointF(g.L + g.pw * 0.15, g.T + g.ph * 0.15)) == "s", "elsewhere it scrolls")
check(w.wheelzone(g, QPointF(g.L + g.pw + 30, cy)) == "p" and w.wheelzone(g, QPointF(cx, g.T + g.ph + 20)) == "t", "and the axes still scale")

key = ("d", d, w.datashowntf)
check(w.dataaxis(wheel(cx, cy)), "the center taken")
settle()
v = w.datazooms.get(key)
check(v is not None and v[0] - v[1] < g.top - g.bot and v[3] - v[2] < g.t1 - g.t0, "zoomed in on both axes")
check(w.view.mode == "fit", "the image still fits: the axes are shown")
g1 = w.datageom
w.dataaxis(wheel(g1.L + 5, cy, -120))
settle()
v2 = w.datazooms.get(key)
check(v2[2:] == v[2:] and v2[0] - v2[1] > v[0] - v[1], "the left edge scaled the prices only")
g2 = w.datageom
w.dataaxis(wheel(cx, g2.T + g2.ph - 5, 120))
settle()
v3 = w.datazooms.get(key)
check(v3[:2] == v2[:2] and v3[3] - v3[2] < v2[3] - v2[2], "the bottom edge the times only")
g3 = w.datageom
w.dataaxis(wheel(g3.L + g3.pw * 0.15, g3.T + g3.ph * 0.15, -40, 0, True))
settle()
v4 = w.datazooms.get(key)
check(abs((v4[0] - v4[1]) - (v3[0] - v3[1])) < 1e-6 and v4[0] < v3[0] and v4[2:] == v3[2:], "a scroll elsewhere moves the prices")
g4 = w.datageom
w.dataaxis(wheel(g4.L + g4.pw * 0.15, g4.T + g4.ph * 0.15, 0, -60, True))
settle()
v5 = w.datazooms.get(key)
check(v5[2] > v4[2] and abs((v5[3] - v5[2]) - (v4[3] - v4[2])) < 1e-6, "and sideways the times")

w.zoominact.trigger()
settle()
v6 = w.datazooms.get(key)
check(v6 is not None and v6[3] - v6[2] < v5[3] - v5[2] and w.view.mode == "fit", "Zoom + zooms the chart, its axes shown")
w.view.zoom(1.5, w.view.viewport().rect().center())	# as a pinch does
settle()
check(w.datazooms.get(key) != v6 and w.view.mode == "fit", "pinching too")
w.fitact.trigger()
settle()
check(w.datazooms.get(key) is None and w.datageom.view() is None, "Fit shows all of it again")

# the indicator folders
f1, f2 = tempfile.mkdtemp(), tempfile.mkdtemp()
for f, txt in ((f1, "one"), (f2, "two")):
	with open(os.path.join(f, "Same.txt"), "w") as fh:
		fh.write('indicator("Same %s", overlay = true)\nplot(close)\n' % txt)
with open(os.path.join(f2, "Other.pine"), "w") as fh:
	fh.write('indicator("Other", overlay = true)\nplot(open)\n')
indicators.setfolders([f1, f2])
have = dict(indicators.scripts())
check(have.get("Same") == os.path.join(f1, "Same.txt") and "Other" in have, "scripts found in the other folders, the first one wins")
indicators.setfolders([f2, f1])
check(dict(indicators.scripts())["Same"] == os.path.join(f2, "Same.txt"), "in the order given")
imp = os.path.join(src, "Same.txt")
with open(imp, "w") as fh:
	fh.write('indicator("Same imported", overlay = true)\nplot(close)\n')
indicators.importfiles([imp])
check(dict(indicators.scripts())["Same"].startswith(indicators.DIR) and indicators.imported("Same"), "the imported ones come first")
check(not indicators.imported("Other"), "those of other folders aren't imported")
indicators.remove("Other")
check(os.path.exists(os.path.join(f2, "Other.pine")), "and removing one leaves its folder alone")
w.fillindicators()
rm = [a for a in w.indmenu.actions() if a.text().replace("&", "") == "Remove"]
check(rm and [a.text() for a in rm[0].menu().actions()] == ["Same"], "the Remove menu has the imported ones only")
check(any("Folders" in a.text().replace("&", "") for a in w.indmenu.actions()), "Indicator Folders… in the menu")
indicators.setfolders([])
indicators.setenabled([])

# room past the last bar
script = os.path.join(src, "Ahead.txt")
with open(script, "w") as fh:
	fh.write('''indicator("Ahead", overlay = true)
if barstate.islast
    label.new(bar_index + 12, high, "ahead")
    line.new(bar_index - 5, low, bar_index + 12, low)
''')
w.datazooms.pop(key, None)
w.showdata(("d", d), force=True)
settle()
g0 = w.datageom
check(g0.margin == 0, "no room without indicators drawing past the last bar")
indicators.importfiles([script])
w.showdata(("d", d), force=True)
settle()
g = w.datageom
check(g.margin > 0 and g.t1 > g.vt1 and g.lastend() == g0.lastend(), "room kept past the last bar for what they draw there")
need = g.tx(g.lastend()) + 12 * g.cw
check(g.t1 >= need - 1e-9 or g.margin >= dataview.MAXMARGIN * (g.vt1 - g.t0) - 1e-9, "enough for it, or as much as is allowed")
check(g.view() is None and g.mapped(), "the whole day, its drawings moved there")
w.dataaxis(wheel(g.L + g.pw / 2, g.T + g.ph / 2))
settle()
g = w.datageom
check(g.view() is not None and g.margin > 0 and g.lastend() < g0.lastend(), "zoomed in, as the last candle shown, with room after it")
print("ALL OK")
os._exit(0)
