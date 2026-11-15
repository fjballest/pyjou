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

# a double click on a fib opens its levels, checked, and changes them
from drawing import FibShape
from PySide6.QtCore import QPointF
w.toolacts["select"].trigger()
fib = FibShape(v.mapToScene(QPoint(300, 500)), v.mapToScene(QPoint(500, 700)), [0, 0.5, 1], "#000000", 2)
v.additem(fib)
seen = {}
def fiblevels(dl):
	seen["on"] = [e.text() for c, e in zip(dl.checks, dl.edits) if c.isChecked()]
	seen["title"] = dl.windowTitle()
	for c, e in zip(dl.checks, dl.edits):
		if e.text() == "0.5":
			c.setChecked(False)
		if e.text() == "0.705":
			c.setChecked(True)
	dl.diagbox.setChecked(True)
	seen["live"] = (list(fib.levels), fib.diagonal)
	dl.accept()
later(fiblevels)
QTest.mouseDClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, v.mapFromScene(QPointF((fib.xs()[0] + fib.xs()[1]) / 2, fib.ys()[1][1])))
check(seen.get("on") == ["0", "0.5", "1"] and seen.get("title") == "Fib Levels", "the form shows its levels checked")
check(fib.levels == [0, 0.705, 1] and fib.diagonal, "and changes them")
v.undo.undo()
check(fib.levels == [0, 0.5, 1] and not fib.diagonal, "undo puts them back")
check(seen.get("live") == ([0, 0.705, 1], True), "the fib shows the levels as they are edited")
def fibcancel(dl):
	for c, e in zip(dl.checks, dl.edits):
		if e.text() == "0.5":
			c.setChecked(False)
	seen["live"] = list(fib.levels)
	dl.reject()
later(fibcancel)
v.editfib(fib)
check(seen["live"] == [0, 1] and fib.levels == [0, 0.5, 1] and v.undo.canRedo(), "and Cancel puts them back, with nothing to undo")
fib.setSelected(True)
def custom(dl):
	for c, e in zip(dl.checks, dl.edits):
		c.setChecked(e.text() in ("0", "0.25", "1"))
	seen["live"] = list(fib.levels)
	dl.reject()
later(custom)
bar.setfib("Custom")
check(seen["live"] == [0, 0.25, 1] and fib.levels == [0, 0.5, 1], "Custom shows its levels on the fibs selected, and Cancel puts them back")
fib.setSelected(False)
v.scene().removeItem(fib)

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

# colors show on the drawing as they are picked, and Cancel puts them back
ln = LineShape(v.mapToScene(QPoint(300, 400)), v.mapToScene(QPoint(500, 420)), "#000000", 2)
v.additem(ln)
def pickred(dl):
	dl.setCurrentColor(QColor("#ff0000"))
	seen["live"] = ln.color
	dl.reject()
def lineform(dl):
	later(pickred)
	dl.color.click()
	seen["after"] = ln.color
	dl.width.setCurrentIndex(dl.width.findData(5.0))
	seen["width"] = ln.width
	dl.reject()
later(lineform)
v.editshape(ln)
check(seen["live"] == "#ff0000" and seen["after"] == "#000000", "a line shows the color picked, and Cancel puts it back")
check(seen["width"] == 5.0 and ln.width == 2, "and its width while the form is open")
ln.setSelected(True)
def pickblue(dl):
	dl.setCurrentColor(QColor("#0000ff"))
	seen["live"] = ln.color
	dl.accept()
later(pickblue)
bar.othercolor()
check(seen["live"] == "#0000ff" and ln.color == "#0000ff", "the bar's color shows on the selection, and OK keeps it")
v.undo.undo()
check(ln.color == "#000000", "in one undo step")
v.scene().removeItem(ln)

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
# Edit… changes a saved one with its form
def editline(dl):
	dl.list.setCurrentRow(0)
	def form(f):
		check(not f.namebox.isVisibleTo(f) and f.extend is not None, "the line form, without Save as")
		f.dash.setCurrentIndex(f.dash.findData("dot"))
		f.extend.setChecked(True)
		f.accept()
	later(form)
	dl.edit()
	dl.accept()
later(editline)
bar.editsaved("line")
pdl = drawbar.savedshapes("line")["PDL"]
check(pdl["dash"] == "dot" and pdl["extend"] is True and pdl["label"] == "PDH", "the saved line changed, its label kept")
def editfiblevels(dl):
	dl.list.setCurrentRow(0)
	def form(f):
		check(not f.namerow.isVisibleTo(f) and [e.text() for c, e in zip(f.checks, f.edits) if c.isChecked()] == ["0.5", "0.705"],
			"the fib form with its levels, without a name")
		for c, e in zip(f.checks, f.edits):
			if e.text() == "0.79":
				c.setChecked(True)
		f.accept()
	later(form)
	dl.edit()
	dl.accept()
later(editfiblevels)
bar.setfib("Mine")
bar.editsaved("fib")
check(drawbar.savedfibs()["Mine"]["levels"] == [0.5, 0.705, 0.79] and v.fiblevels == [0.5, 0.705, 0.79],
	"a level added to the saved fib, and drawn with it as it is in use")
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
