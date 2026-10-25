#
# headless tests of the panels and the zoom gestures: QT_QPA_PLATFORM=offscreen python3 tests/test_panels.py
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QNativeGestureEvent, QPointingDevice
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import mainwin
import ocrworker

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

d = tempfile.mkdtemp()
img = QImage(1600, 900, QImage.Format.Format_RGB32)
img.fill(QColor(240, 240, 230))
img.save(os.path.join(d, "day261012.png"))
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])

app = QApplication(sys.argv)
w = mainwin.MainWindow(d)
w.show()
QTest.qWaitForWindowExposed(w)
check(w.left.isVisible() and w.bottom.isVisible(), "both panels shown at first")
vw = w.view.viewport().width()
w.listact.trigger()
QTest.qWait(30)
check(not w.left.isVisible() and not w.listact.isChecked() and w.view.viewport().width() > vw, "the list hides, the image grows")
vh = w.view.viewport().height()
w.notespanelact.trigger()
QTest.qWait(30)
check(not w.bottom.isVisible() and w.view.viewport().height() > vh, "the notes hide, the image grows")
w.notesact.trigger()
check(w.bottom.isVisible() and w.notespanelact.isChecked(), "Edit Notes shows them again")
w.findact.trigger()
check(w.left.isVisible() and w.listact.isChecked(), "Search shows the list again")
w.listact.trigger()
w.close()
w2 = mainwin.MainWindow(d)
w2.show()
QTest.qWaitForWindowExposed(w2)
check(not w2.left.isVisible() and w2.bottom.isVisible(), "remembered")
w2.listact.trigger()

# double clicks don't zoom; a double tap does
v = w2.view
v.fit()
s0 = v.scale_()
QTest.mouseDClick(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, v.viewport().rect().center())
check(abs(v.scale_() - s0) < 1e-6, "a double click doesn't zoom")
def gesture(kind, value=0.0):
	pos = QPointF(v.viewport().rect().center())
	ev = QNativeGestureEvent(kind, QPointingDevice.primaryPointingDevice(), 2, pos, pos, v.viewport().mapToGlobal(pos),
		value, QPointF(), 0)
	QApplication.sendEvent(v.viewport(), ev)
gesture(Qt.NativeGestureType.SmartZoomNativeGesture)
check(abs(v.scale_() - 2 * s0) < 1e-6, "a double tap zooms in")
gesture(Qt.NativeGestureType.SmartZoomNativeGesture)
gesture(Qt.NativeGestureType.SmartZoomNativeGesture)
check(abs(v.scale_() - s0) < 1e-6, "the third one fits again")
gesture(Qt.NativeGestureType.ZoomNativeGesture, 0.5)
check(abs(v.scale_() - 1.5 * s0) < 1e-6, "pinching zooms")
w2.close()
print("ALL OK")
