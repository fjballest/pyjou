#
# headless tests of the day rows and Edit ▸ Scale Panel:
# QT_QPA_PLATFORM=offscreen python3 tests/test_scale.py
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

import mainwin
import ocrworker

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

d = tempfile.mkdtemp()
for n in ("day261013.png", "day261014.png", "day261014b.png", "day261014c.png"):
	img = QImage(400, 200, QImage.Format.Format_RGB32)
	img.fill(QColor("white"))
	p = QPainter(img)
	p.fillRect(0, 100, 400, 2, QColor("black"))	# a level at y 100 in both charts
	p.fillRect(0, 180, 400, 20, QColor("blue"))	# the time axis
	p.end()
	img.save(os.path.join(d, n))
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])
app = QApplication.instance() or QApplication([])
w = mainwin.MainWindow(d)
w.resize(1200, 700)
w.show()
w.reveal(w.journal.find("day261014.png"))
app.processEvents()

# a row a day, with a chip for each capture
row = w.items["day261014.png"]
check(row is w.items["day261014c.png"] and row.text(0) == "Wed 14  · CPI" and len(w.list.chips(row)) == 3, "one row for the day, three chips")
check(w.list.chips(w.items["day261013.png"]) == [], "a day with one capture has no chips")
vp = w.list.viewport()
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, w.list.chiprect("day261014b.png").center())
check(w.current.name == "day261014b.png", "clicking a chip shows that capture")
w.list.setFocus()
QTest.keyClick(w.list, Qt.Key.Key_Right)
check(w.current.name == "day261014c.png", "right goes to the next chip")
QTest.keyClick(w.list, Qt.Key.Key_Left)
QTest.keyClick(w.list, Qt.Key.Key_Left)
check(w.current.name == "day261014.png", "left to the previous ones")
check(w.listentry().name == "day261014.png" and [e.name for e in w.selectedentries()] == ["day261014.png"], "the chip shown is the selected one")

# scale the right chart, split at x 200, kept below y 180
v = w.view
v.realsize()
app.processEvents()
asked = []
QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(a[2]), QMessageBox.StandardButton.Yes)[1])
def at(x, y):
	return v.mapFromScene(QPointF(x, y))
def drag(x, y0, y1):
	QTest.mousePress(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(x, y0))
	QTest.mouseMove(v.viewport(), at(x, (y0 + y1) / 2))
	QTest.mouseMove(v.viewport(), at(x, y1))
	QTest.mouseRelease(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(x, y1))
def finish(x, y):
	QTest.mouseDClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(x, y))
	for _ in range(20):
		QTest.qWait(20)
		if v.scaler is None:
			break
from drawing import LineShape, TextShape
v.additem(LineShape(QPointF(250, 100), QPointF(350, 100), "#ff0000", 2))	# on the right chart's level
v.additem(LineShape(QPointF(50, 100), QPointF(150, 100), "#00ff00", 2))	# on the left chart
v.additem(TextShape(QPointF(260, 185), "time", "#000000", 12))	# below the line
v.drawchanged.emit()
w.scalepanel()
check(v.scaler is not None and "two charts" in w.statusBar().currentMessage(), "scaling starts by asking for the split")
QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(200, 50))
QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(300, 180))
check(v.scaler["side"] == "right" and v.scaler["y"] == 180, "the right chart, kept below y 180")
# drag the chart: the level at 100 to 80, moved, not scaled
drag(300, 100, 80)
check(v.scalemap() == (1.0, -20.0) and asked == [], "a drag moves the chart, without asking yet")
check(abs(v.anchorat() - 80) < 0.01, "the price dragged is the one kept in place")
# the wheel scales about it
from PySide6.QtCore import QPoint
from PySide6.QtGui import QWheelEvent
def wheel(d):
	pos = QPointF(at(300, 120))
	ev = QWheelEvent(pos, QPointF(v.viewport().mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, d),
		Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
	QApplication.sendEvent(v.viewport(), ev)
wheel(120)
a, b = v.scalemap()
check(a > 1.05 and abs(v.anchorat() - 80) < 0.01, f"the wheel scales, keeping that price in place: x{a:.3f}")
# shift drag scales too, about the same price
drag_shift = lambda x, y0, y1: (QTest.mousePress(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, at(x, y0)),
	QTest.mouseMove(v.viewport(), at(x, y1)),
	QTest.mouseRelease(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, at(x, y1)))
drag_shift(300, 140, 130)
a2, _ = v.scalemap()
check(a2 > a and abs(v.anchorat() - 80) < 0.01, "a shift drag up stretches it, the price stays")
drag_shift(300, 130, 160)
a3, _ = v.scalemap()
check(a3 < a2 and abs(v.anchorat() - 80) < 0.01, "down shrinks it")
finish(300, 120)
check(asked and "right chart ×" in asked[0], f"a double click asks before replacing: {asked}")
img = QImage(os.path.join(d, "day261014.png"))
dark = lambda x, y: img.pixelColor(x, y).lightness() < 60
check(img.width() == 400 and img.height() == 200, "the same size")
check(dark(300, 80) and not dark(300, 101), "the right chart's level is where it was dragged")
check(dark(100, 100) and not dark(100, 80), "the left chart is as it was")
check(img.pixelColor(300, 190) == QColor("blue"), "below the line it is as it was")
check(v.scaler is None, "scaling ends")
saved = {sh.get("color"): sh for sh in w.journal.readdrawing(w.journal.find("day261014.png"))["shapes"]}
check(abs(saved["#ff0000"]["p1"][1] - 80) < 0.6 and abs(saved["#ff0000"]["p2"][1] - 80) < 0.6,
	f"a drawing on the chart scaled follows it: {saved['#ff0000']}")
check(saved["#00ff00"]["p1"][1] == 100, "one on the other chart stays")
check(saved["#000000"]["pos"] == [260, 185], "and one below the line too")
check("day261014.png" not in w.pending, "the drawings are saved with the image")

# saying no keeps the file
before = open(os.path.join(d, "day261013.png"), "rb").read()
w.reveal(w.journal.find("day261013.png"))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
w.scalepanel()
QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(200, 50))
QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(100, 180))
drag(100, 100, 140)
wheel(-120)
finish(100, 120)
check(open(os.path.join(d, "day261013.png"), "rb").read() == before and v.scaler is None, "no: the file stays")
check(v.pixitem.pixmap().toImage().pixelColor(100, 100).lightness() < 60, "and the image shown is the original")
# a double click with nothing dragged just ends; Esc cancels
w.scalepanel()
QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(200, 50))
QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(100, 180))
finish(100, 120)
check(v.scaler is None and open(os.path.join(d, "day261013.png"), "rb").read() == before, "nothing dragged: it just ends")
w.scalepanel()
v.setFocus()
QTest.keyClick(v, Qt.Key.Key_Escape)
check(v.scaler is None, "Esc cancels")
