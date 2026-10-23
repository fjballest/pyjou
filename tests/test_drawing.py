#
# headless tests of the drawings: QT_QPA_PLATFORM=offscreen python3 tests/test_drawing.py
#
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import journal
import mainwin
import ocrworker
from drawing import CircleShape, LineShape, PencilShape, TextShape

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

d = tempfile.mkdtemp()
for i, n in enumerate(["day261012.png", "day261013.png"]):
	img = QImage(1600, 900, QImage.Format.Format_RGB32)
	img.fill(QColor(240, 240 - 40 * i, 230))
	img.save(os.path.join(d, n))
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])

app = QApplication(sys.argv)
w = mainwin.MainWindow(d)
w.resize(1500, 950)
w.show()
QTest.qWaitForWindowExposed(w)
v = w.view
vp = v.viewport()
check(w.current.name == "day261013.png" and v.hasimage(), "image shown")

def drag(a, b):
	QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
	for k in range(1, 6):
		QTest.mouseMove(vp, a + (b - a) * k / 5)
	QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
	app.processEvents()

def kinds():
	return [s.kind for s in v.shapes()]

w.toolacts["arrow"].trigger()
check(v.tool == "arrow", "arrow tool")
drag(QPoint(100, 100), QPoint(400, 250))
check(kinds() == ["arrow"], "an arrow drawn")
a = v.shapes()[0].todict()
p1 = v.mapToScene(QPoint(100, 100))
check(abs(a["p1"][0] - p1.x()) < 1 and abs(a["p1"][1] - p1.y()) < 1, "in image coordinates")
w.toolacts["line"].trigger()
drag(QPoint(500, 300), QPoint(700, 300))
w.toolacts["circle"].trigger()
drag(QPoint(200, 350), QPoint(320, 430))
drag(QPoint(600, 600), QPoint(601, 601))
check(kinds() == ["arrow", "line", "circle"], "a line and a circle; a click draws nothing")
w.setcolor("#1e63d6")
w.toolacts["text"].trigger()
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(800, 150))
t = [s for s in v.shapes() if isinstance(s, TextShape)][0]
check(t.editing() and v.tool == "select", "text box being written")
QTest.keyClicks(vp, "EQH sweep")
QTest.keyClick(vp, Qt.Key.Key_Left)	# in the text, not to the previous image
check(w.current.name == "day261013.png", "arrows move in the text while writing")
v.commitedit()
check(t.toPlainText() == "EQH sweep" and t.color == "#1e63d6" and not t.editing(), "text written in blue")
check(v.undo.count() == 4, "four undo steps")

v.undo.undo()
check(kinds() == ["arrow", "line", "circle"], "undo the text")
v.undo.redo()
check(kinds()[-1] == "text", "redo the text")
v.undo.undo(); v.undo.undo()
check(kinds() == ["arrow", "line"], "undo the circle")
v.undo.redo()
check(kinds() == ["arrow", "line", "circle"], "redo the circle")
v.undo.redo()
check(kinds() == ["arrow", "line", "circle", "text"], "redo the text again")

# select and move the line
w.toolacts["select"].trigger()
line = [s for s in v.shapes() if s.kind == "line"][0]
mid = QPoint(600, 300)
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, mid)
check(line.isSelected() and w.delact.isEnabled(), "click selects the line")
before = line.todict()
drag(mid, QPoint(600, 400))
after = line.todict()
dy = v.mapToScene(QPoint(600, 400)).y() - v.mapToScene(mid).y()
check(abs(after["p1"][1] - before["p1"][1] - dy) < 1.5, "drag moves it")
v.undo.undo()
check(abs(line.todict()["p1"][1] - before["p1"][1]) < 0.1, "undo the move")
v.undo.redo()
# color of the selection
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(600, 400))
w.setcolor("#2e7d32")
check(line.color == "#2e7d32", "recolor the selection")
v.undo.undo()
check(line.color == "#e53935", "undo the color")
v.setwidth(8.0)
check(line.width == 8.0, "new width for the selection")
# delete
QTest.keyClick(vp, Qt.Key.Key_Delete)
check("line" not in kinds(), "Del deletes the selection")
v.undo.undo()
check("line" in kinds(), "undo the delete")
# a click on the image deselects; drag on it pans, not moves
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(1000, 700))
check(not v.scene().selectedItems(), "clicking the image deselects")

# shift keeps lines horizontal or vertical
S = Qt.KeyboardModifier.ShiftModifier
for tool, b, flat in (("line", QPoint(830, 230), "y"), ("arrow", QPoint(760, 420), "x")):
	w.toolacts[tool].trigger()
	a0 = QPoint(700, 200)
	old = set(v.shapes())
	QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a0)
	QTest.mouseMove(vp, b)
	QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, S, b)
	s = [x for x in v.shapes() if x not in old][0].todict()
	i = 1 if flat == "y" else 0
	check(s["kind"] == tool and s["p1"][i] == s["p2"][i] and s["p1"][1 - i] != s["p2"][1 - i],
		f"shift keeps the {tool} {'horizontal' if flat == 'y' else 'vertical'}")
	v.undo.undo()
w.toolacts["line"].trigger()
old = set(v.shapes())
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(700, 200))
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(830, 230))
s = [x for x in v.shapes() if x not in old][0].todict()
check(s["p1"][1] != s["p2"][1], "without shift any slope")
v.undo.undo()
check(sorted(kinds()) == ["arrow", "circle", "line", "text"], "test lines undone")

# free hand
w.toolacts["pencil"].trigger()
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(900, 500))
for k in range(40):
	QTest.mouseMove(vp, QPoint(900 + 5 * k, 500 + round(30 * __import__("math").sin(k / 4))))
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(1095, 500))
pen = [s for s in v.shapes() if s.kind == "pencil"]
check(len(pen) == 1 and len(pen[0].points) > 20, "a free hand stroke")
v.undo.undo()
check("pencil" not in kinds(), "undo the stroke")
v.undo.redo()
check("pencil" in kinds(), "redo the stroke")
w.toolacts["select"].trigger()

# saved only when asked
QTest.qWait(mainwin.SAVEDELAY + 300)
p = os.path.join(d, "day261013" + journal.DRAWEXT)
check(not os.path.exists(p) and w.windowTitle().endswith("(unsaved)") and w.saveact.isEnabled(),
	"unsaved drawings in the title")
w.step(-1)
w.step(1)
check(len(v.shapes()) == 5 and not os.path.exists(p) and "(unsaved)" in w.windowTitle(),
	"unsaved drawings kept when going to another image and back")
w.reload()
check(len(v.shapes()) == 5 and v.undo.count() == 0, "reload keeps them")
v.undo.clear()
w.drawchanged()
w.saveact.trigger()
check(os.path.exists(p) and "(unsaved)" not in w.windowTitle() and not w.saveact.isEnabled(), "save")
saved = json.load(open(p))
check(sorted(s["kind"] for s in saved["shapes"]) == ["arrow", "circle", "line", "pencil", "text"], "saved next to the image")
check([s["text"] for s in saved["shapes"] if s["kind"] == "text"] == ["EQH sweep"], "with the text")
w.grab().save(os.path.join(sys.argv[1] if len(sys.argv) > 1 else d, "drawing.png"))

# away and back
w.step(-1)
check(w.current.name == "day261012.png" and kinds() == [] and v.undo.count() == 0, "another image has its own drawings")
w.step(1)
check(sorted(kinds()) == ["arrow", "circle", "line", "pencil", "text"] and v.undo.count() == 0, "drawings read back")
check(sorted(type(s).__name__ for s in v.shapes()) == sorted(x.__name__ for x in (LineShape, LineShape, CircleShape, PencilShape, TextShape)),
	"as the shapes they were")
# the text boxes are searched
w.searchbox.setText("sweep")
QTest.qWait(400)
check([e.name for e in w.shown] == ["day261013.png"], "search finds the text in a drawing")
w.searchbox.setText("")
QTest.qWait(400)
# undoing back to what was saved is not unsaved
t = [s for s in v.shapes() if isinstance(s, TextShape)][0]
t.setSelected(True)
v.deleteselected()
check("(unsaved)" in w.windowTitle(), "a change is unsaved")
v.undo.undo()
check("(unsaved)" not in w.windowTitle(), "undoing it is not")
# editing a text box
t = [s for s in v.shapes() if isinstance(s, TextShape)][0]
t.startedit()
QTest.keyClicks(vp, "liquidity")
v.commitedit()
check(t.toPlainText() == "liquidity" and v.undo.count() == 1, "edit a text box")
v.undo.undo()
check(t.toPlainText() == "EQH sweep", "undo the edit")
# emptying a text box deletes it
t.startedit()
QTest.keyClick(vp, Qt.Key.Key_Delete)
v.commitedit()
check("text" not in kinds(), "an emptied text box goes")
v.undo.undo()
check("text" in kinds(), "and comes back with undo")
# removing everything removes the file
v.scene().clearSelection()
for s in v.shapes():
	s.setSelected(True)
v.deleteselected()
w.step(-1)
check(os.path.exists(p), "leaving the image doesn't save")
# quitting asks
asked = []
mainwin.QMessageBox.question = staticmethod(lambda *a, **k: asked.append(a[2]) or answers.pop(0))
answers = [mainwin.QMessageBox.StandardButton.Cancel]
w.close()
check(w.isVisible() and asked and "not saved" in asked[0], "quitting with unsaved drawings asks, cancel stays")
answers = [mainwin.QMessageBox.StandardButton.Save]
w.close()
check(not w.isVisible() and not os.path.exists(p), "save on quit; no drawings, no file")
w.close()
print("ALL OK")
