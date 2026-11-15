#
# headless tests of the fib levels, rectangles, lines and circles saved by
# name in the drawing menus: QT_QPA_PLATFORM=offscreen python3 tests/test_presets.py
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

import drawbar
import mainwin
import ocrworker
import sandbox
from drawing import CircleShape, FibShape, LineShape, RectShape

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

d = tempfile.mkdtemp()
img = QImage(1600, 900, QImage.Format.Format_RGB32)
img.fill(QColor(240, 240, 230))
img.save(os.path.join(d, "day261013.png"))
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])
warned = []
QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a[2]))
app = QApplication(sys.argv)
w = mainwin.MainWindow(d)
w.resize(1500, 950)
w.show()
QTest.qWaitForWindowExposed(w)
v, vp, bar = w.view, w.view.viewport(), w.drawbar

def later(fn):
	"""run fn on the next dialog opened, then close it with fn's answer"""
	def f():
		dl = QApplication.activeModalWidget()
		if dl is None:
			QTimer.singleShot(30, f)
			return
		fn(dl)
	QTimer.singleShot(30, f)

def drag(a, b):
	QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
	for k in range(1, 6):
		QTest.mouseMove(vp, a + (b - a) * k / 5)
	QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
	app.processEvents()

def newshape(kind, a, b):
	"""draw one with the tool chosen, and return it"""
	before = set(v.shapes())
	drag(a, b)
	new = [s for s in v.shapes() if s not in before and isinstance(s, kind)]
	check(len(new) == 1, "drawn")
	return new[0]

def menu(kind):
	return [a.text() for a in bar.toolacts[kind].menu().actions() if a.text()]

# fibs: Clear unchecks all the levels; a name keeps them in the menu
def fibform(dl):
	dl.clear()
	check(not any(c.isChecked() for c in dl.checks), "Clear unchecks every level")
	dl.edits[0].setText("0.5")
	dl.edits[0].textEdited.emit("0.5")
	dl.edits[1].setText("0.705")
	dl.edits[1].textEdited.emit("0.705")
	dl.namebox.setText(" Mine ")
	dl.accept()
later(fibform)
bar.setfib("Custom")
check(bar.fibname == "Mine" and v.fiblevels == [0.5, 0.705], "the levels named are used")
check("Mine: 0.5 0.705" in menu("fib") and drawbar.savedfibs()["Mine"]["levels"] == [0.5, 0.705], "and saved in the menu")
bar.setfib("OTE")
bar.setfib("Mine")
check(v.fiblevels == [0.5, 0.705] and bar.fibacts["Mine"].isChecked(), "picked again from the menu")
def taken(dl):
	dl.namebox.setText("OTE")
	dl.accept()
	check(dl.isVisible() and warned and "OTE" in warned[-1], "a built-in name is refused")
	dl.reject()
later(taken)
bar.setfib("Custom")

# a rectangle saved with a name, from its form
w.toolacts["rect"].trigger()
drag(QPoint(200, 200), QPoint(400, 300))
r = [s for s in v.shapes() if isinstance(s, RectShape)][-1]
def rectform(dl):
	dl.fillbox.setChecked(True)
	dl.label.setText("OB")
	dl.namebox.setText("OB")
	dl.accept()
later(rectform)
v.editshape(r)
check("OB" in menu("rect") and drawbar.savedshapes("rect")["OB"]["label"] == "OB", "a rectangle saved by name")
bar.setshape("rect", "OB")
r2 = newshape(RectShape, QPoint(500, 200), QPoint(700, 300))
check(r2 is not r and r2.label == "OB" and r2.fill, "new rectangles look like it")

# lines, arrows and circles too
w.setcolor("#1e63d6")
w.toolacts["line"].trigger()
drag(QPoint(200, 500), QPoint(500, 500))
ln = [s for s in v.shapes() if isinstance(s, LineShape)][-1]
def lineform(dl):
	dl.label.setText("PDH")
	dl.dash.setCurrentIndex(dl.dash.findData("dash"))
	dl.namebox.setText("PDH")
	dl.accept()
later(lineform)
v.editshape(ln)
check("PDH" in menu("line") and drawbar.savedshapes("line")["PDH"]["dash"] == "dash", "a line saved by name")
w.setcolor("#e53935")
bar.setshape("line", "PDH")
check(v.tool == "line", "picking it takes the line tool")
l2 = newshape(LineShape, QPoint(200, 600), QPoint(500, 600))
check(l2.label == "PDH" and l2.dash == "dash" and l2.color == "#1e63d6", "new lines look like it")
bar.setshape("line", "Plain")
l3 = newshape(LineShape, QPoint(200, 420), QPoint(500, 420))
check(l3.label == "" and l3.color == "#e53935", "Plain draws with the color chosen")
w.toolacts["circle"].trigger()
drag(QPoint(800, 300), QPoint(900, 380))
c = [s for s in v.shapes() if isinstance(s, CircleShape)][-1]
def circleform(dl):
	dl.namebox.setText("Zone")
	dl.accept()
later(circleform)
v.editshape(c)
check("Zone" in menu("circle") and "Zone" not in menu("line"), "circles have their own")

# editing the saved ones: rename, reorder and remove
drawbar.saveshape("line", "EQH", {"color": "#000000", "width": 1.0, "dash": "dot"})
bar.remakemenu("line")
check(menu("line").index("PDH") < menu("line").index("EQH"), "in the order saved")
def edit(dl):
	check(dl.names() == ["PDH", "EQH"], "the saved ones listed")
	dl.list.setCurrentRow(0)
	dl.list.item(0).setText("PDL")	# renamed in place
	dl.list.setCurrentRow(1)
	dl.move(-1)
	check(dl.names() == ["EQH", "PDL"], "moved up")
	dl.list.item(0).setText("PDL")
	check(dl.names() == ["EQH", "PDL"], "a name already there is refused")
	dl.list.setCurrentRow(0)
	dl.remove()
	dl.accept()
later(edit)
bar.editsaved("line")
check(list(drawbar.savedshapes("line")) == ["PDL"] and "PDL" in menu("line") and "PDH" not in menu("line")
	and "EQH" not in menu("line"), "renamed and removed")
def editfibs(dl):
	dl.remove()
	dl.accept()
later(editfibs)
bar.editsaved("fib")
check(drawbar.savedfibs() == {} and not any(t.startswith("Mine") for t in menu("fib")) and bar.fibname == "OTE",
	"the fib levels removed; back to OTE")
w.pending = {}
w.close()
print("ALL OK")
