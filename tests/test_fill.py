#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_fill.py
# data charts as wide as their window, their drawings kept as on the chart of its own width;
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
import sandbox
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
data = m15.Data(j)
d = date(2026, 11, 4)
import dataview
from dataview import mapdrawing

def settle(w):
	for _ in range(40):
		app.processEvents()
		time.sleep(0.02)

w = mainwin.MainWindow(j)
w.resize(1900, 800)
w.show()
w.setdatamode(True)
w.showdata(("d", d), force=True)
settle(w)
g = w.datageom
vp = w.view.maximumViewportSize()
check(g.W0 == 1800 and abs(g.W / g.H - vp.width() / vp.height()) < 0.02 and g.W > 1800,
	f"a wide window: the chart is as wide ({g.W} x {g.H}, view {vp.width()} x {vp.height()})")
img = w.view.pixitem.pixmap()
check(img.width() == g.W, "drawn that wide")
check(g.mapped() and not g.unzoomed().mapped() and g.unzoomed().W == 1800, "its drawings kept as on its own width")
draw = {"shapes": [{"kind": "line", "p1": [500.0, 300.0], "p2": [900.0, 600.0]}]}
there = mapdrawing(mapdrawing(draw, g.unzoomed(), g), g, g.unzoomed())
check(all(abs(a - b) < 0.2 for a, b in zip(there["shapes"][0]["p1"] + there["shapes"][0]["p2"], [500, 300, 900, 600])),
	"and moved to the chart shown and back")
data.savedrawing("d", d, draw, 15)
w.showdata(("d", d), force=True)
settle(w)
shown = w.view.drawingdata()
x = shown["shapes"][0]["p1"][0] if shown and shown.get("shapes") else None
check(x is not None and abs(x - g.X(g.unzoomed().t(500))) < 1, "a saved drawing shown where its times are")
w.resize(1100, 800)
settle(w)
time.sleep(0.3)
settle(w)
g2 = w.datageom
check(g2.W < g.W, f"a narrower window draws it again narrower: {g2.W}")

# the room right of the last candle, set by dragging the grip on the time axis
from PySide6.QtTest import QTest
from PySide6.QtCore import QPointF, Qt as _Qt
w.resize(1600, 800)
settle(w)
time.sleep(0.3)
settle(w)
g = w.datageom
check(g.margin == 0 and w.marginshare() is None, "no margin without indicators, until set")
vp = w.view.viewport()
def at(x, y):
	return w.view.mapFromScene(QPointF(x, y))
grip = at(dataview.gripx(g), g.T + g.ph + 6)
QTest.mousePress(vp, _Qt.MouseButton.LeftButton, _Qt.KeyboardModifier.NoModifier, grip)
to = at(g.L + g.pw * 0.75, g.T + g.ph + 6)
QTest.mouseMove(vp, to)
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import QEvent
ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(to), QPointF(vp.mapToGlobal(to)), _Qt.MouseButton.NoButton,
	_Qt.MouseButton.LeftButton, _Qt.KeyboardModifier.NoModifier)
app.sendEvent(vp, ev)
settle(w)
QTest.mouseRelease(vp, _Qt.MouseButton.LeftButton, _Qt.KeyboardModifier.NoModifier, to)
settle(w)
g2 = w.datageom
share = w.marginshare()
check(share is not None and abs(share - 0.25) < 0.02, f"dragged to a quarter of the width: {share}")
check(abs((dataview.gripx(g2) - g2.L) / g2.pw - 0.75) < 0.02 and g2.margin > 0, "the candles end where the grip was left")
w.datazooms[("d", d, 15)] = (g2.whole[0], g2.whole[1], g2.whole[2] + 3, g2.whole[3] - 3)
w.showdata(("d", d), force=True)
settle(w)
g3 = w.datageom
check(abs((dataview.gripx(g3) - g3.L) / g3.pw - 0.75) < 0.02, "the same share when zoomed")
grip = at(dataview.gripx(g3), g3.T + g3.ph + 6)
QTest.mouseDClick(vp, _Qt.MouseButton.LeftButton, _Qt.KeyboardModifier.NoModifier, grip)
settle(w)
check(w.marginshare() is None and w.datageom.margin == 0, "a double click on it: as the indicators need again")
print("ALL OK")
os._exit(0)
