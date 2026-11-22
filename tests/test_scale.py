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
check(row is w.items["day261014c.png"] and row.text(0) == "Wed 14" and len(w.list.chips(row)) == 3, "one row for the day, three chips")
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

# scale the right chart, at x 200, about y 180: the level at 100 goes to 60 with x1.5
v = w.view
v.realsize()
app.processEvents()
asked = []
QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(a[2]), QMessageBox.StandardButton.Yes)[1])
def at(x, y):
	return v.mapFromScene(QPointF(x, y))
w.scalepanel()
check(v.scaler is not None and "two charts" in w.statusBar().currentMessage(), "scaling starts by asking for the split")
QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(200, 50))
QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(300, 180))
check(v.scaler["side"] == "right" and v.scaler["y"] == 180, "the right chart, kept below y 180")
QTest.mousePress(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(300, 100))
QTest.mouseMove(v.viewport(), at(300, 60))
QTest.mouseRelease(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(300, 60))
for _ in range(20):
	QTest.qWait(20)
	if asked:
		break
check(asked and "right chart ×1.500" in asked[0], f"asks before replacing: {asked}")
img = QImage(os.path.join(d, "day261014.png"))
dark = lambda x, y: img.pixelColor(x, y).lightness() < 60
check(img.width() == 400 and img.height() == 200, "the same size")
check(dark(300, 61) and not dark(300, 101), "the right chart's level moved up")
check(dark(100, 100) and not dark(100, 61), "the left chart is as it was")
check(img.pixelColor(300, 190) == QColor("blue"), "below the line it is as it was")
check(v.scaler is None, "scaling ends")

# saying no keeps the file
before = open(os.path.join(d, "day261013.png"), "rb").read()
w.reveal(w.journal.find("day261013.png"))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
w.scalepanel()
QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(200, 50))
QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(100, 180))
QTest.mousePress(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(100, 100))
QTest.mouseMove(v.viewport(), at(100, 140))
QTest.mouseRelease(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(100, 140))
QTest.qWait(50)
check(open(os.path.join(d, "day261013.png"), "rb").read() == before and v.scaler is None, "no: the file stays")
check(v.pixitem.pixmap().toImage().pixelColor(100, 100).lightness() < 60, "and the image shown is the original")
# Esc cancels
w.scalepanel()
v.setFocus()
QTest.keyClick(v, Qt.Key.Key_Escape)
check(v.scaler is None, "Esc cancels")
