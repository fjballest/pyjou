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

import drawbar
import journal
import mainwin
import viewer
import ocrworker
import sandbox
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
# the ends of a line selected can be dragged; the corners of a circle too
line.setSelected(True)
end = v.mapFromScene(line.handles()[1])
check(v.handleat(end) == (line, 1), "the handle at the end of the line selected")
img = v.grab().toImage()
c = img.pixelColor(end.x() + 2, end.y() + 2)
check(c.red() > 200 and c.green() > 200 and c.blue() > 200, "the handle is drawn")
start = line.handles()[0]
drag(end, QPoint(760, 200))
h = line.handles()
check(abs(h[1].x() - v.mapToScene(QPoint(760, 200)).x()) < 1 and abs(h[1].y() - v.mapToScene(QPoint(760, 200)).y()) < 1
	and abs(h[0].x() - start.x()) < 0.1 and abs(h[0].y() - start.y()) < 0.1, "dragging it moves that end only")
check(line.isSelected(), "still selected")
v.undo.undo()
check(abs(line.handles()[1].x() - v.mapToScene(end).x()) < 1, "undo the reshape")
v.undo.redo()
check(abs(line.handles()[1].y() - v.mapToScene(QPoint(760, 200)).y()) < 1, "redo it")
end = v.mapFromScene(line.handles()[1])
a = v.mapFromScene(line.handles()[0])
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import QEvent, QPointF
def move(p, mods):
	v.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, QPointF(p), QPointF(vp.mapToGlobal(p)), Qt.MouseButton.NoButton,
		Qt.MouseButton.LeftButton, mods))
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
move(QPoint(end.x() + 40, a.y() + 15), Qt.KeyboardModifier.ShiftModifier)
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(end.x() + 40, a.y() + 15))
h = line.handles()
check(abs(h[1].y() - h[0].y()) < 0.1, "with shift the end stays level with the other")
v.undo.undo()
circle = [s for s in v.shapes() if s.kind == "circle"][0]
v.scene().clearSelection()
circle.setSelected(True)
r0 = circle.mapRectToScene(circle.rect())
check(v.handleat(end) is None, "only the handles of what is selected")
br = v.mapFromScene(circle.handles()[2])
drag(br, br + QPoint(50, 30))
r1 = circle.mapRectToScene(circle.rect())
check(abs(r1.topLeft().x() - r0.topLeft().x()) < 0.1 and r1.width() > r0.width() + 30, "a corner of the circle resizes it")
v.undo.undo()
v.scene().clearSelection()
# a rectangle: the middle of a side moves just that side; shift keeps a corner level or plumb
from drawing import RectShape, LineShape, fromdict
from PySide6.QtCore import QRectF, QTimer
box = RectShape(QRectF(300, 300, 200, 100), "#000000", 2)
v.additem(box)
box.setSelected(True)
right = v.mapFromScene(box.handles()[5])
check(v.handleat(right) == (box, 5), "a handle in the middle of the right side")
drag(right, right + QPoint(80, 40))
r = box.mapRectToScene(box.rect())
check(r.top() == 300 and r.bottom() == 400 and r.left() == 300 and r.right() > 560, "the right side moves, the top and bottom stay")
corner = v.mapFromScene(box.handles()[2])
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, corner)
move(corner + QPoint(60, 15), Qt.KeyboardModifier.ShiftModifier)
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, corner + QPoint(60, 15))
r2 = box.mapRectToScene(box.rect())
check(r2.bottom() == 400 and r2.right() > r.right() + 30, "with shift a corner moved mostly across keeps its height")
v.undo.undo(); v.undo.undo()
check(box.mapRectToScene(box.rect()) == QRectF(300, 300, 200, 100), "undo both")
v.scene().removeItem(box)
# a line can extend across the image
sr = v.sceneRect()
hl = LineShape(QPointF(400, 200), QPointF(600, 200), "#000000", 2, extend=True)
v.additem(hl)
e = hl.drawn()
check(abs(min(e.x1(), e.x2()) - sr.left()) < 0.1 and abs(max(e.x1(), e.x2()) - sr.right()) < 0.1 and e.y1() == 200,
	"a horizontal line extended goes from the left edge to the right one")
vl = LineShape(QPointF(500, 300), QPointF(500, 400), "#000000", 2, extend=True)
v.additem(vl)
e = vl.drawn()
check(abs(min(e.y1(), e.y2()) - sr.top()) < 0.1 and abs(max(e.y1(), e.y2()) - sr.bottom()) < 0.1, "a vertical one from top to bottom")
vl.setPos(100, 0)
check(abs(vl.mapToScene(vl.drawn().p1()).x() - 600) < 0.1 and vl.boundingRect().height() >= sr.height(), "moved, it still spans the image")
dd = hl.todict()
check(dd.get("extend") is True and fromdict(dd).extend, "kept when saved")
check("extend" not in LineShape(QPointF(0, 0), QPointF(5, 5), "#000000", 2).todict(), "not saved when off")
hl.edit = v.editshape
QTimer.singleShot(100, lambda: (v.shapedlg.extend.setChecked(False), v.shapedlg.accept()))
v.editshape(hl)
w.activateWindow()
QTest.qWaitForWindowActive(w)	# the form took it
check(not hl.extend and hl.drawn() == hl.line(), "the line form turns it off")
v.undo.undo()
check(hl.extend, "undo turns it on again")
# a label at an end of a line extended: the line stops before it
hl.setprops({"label": "PDH", "align": "left"})
lr = hl.mapRectToScene(hl.labelrect())
e = hl.drawn()
check(abs(lr.left() - sr.left()) < 0.1 and abs(lr.center().y() - 200) < 0.1, "Left: the label at the left edge, across the line")
check(min(hl.mapToScene(e.p1()).x(), hl.mapToScene(e.p2()).x()) > lr.right()
	and abs(max(hl.mapToScene(e.p1()).x(), hl.mapToScene(e.p2()).x()) - sr.right()) < 0.1, "the line starts after it")
hl.setprops({"align": "right"})
lr = hl.mapRectToScene(hl.labelrect())
check(abs(lr.right() - sr.right()) < 0.1 and max(hl.mapToScene(hl.drawn().p1()).x(), hl.mapToScene(hl.drawn().p2()).x()) < lr.left(),
	"Right: at the right edge, the line stopping before it")
vl.setprops({"label": "open", "align": "right"})
lr = vl.mapRectToScene(vl.labelrect())
check(abs(lr.bottom() - sr.bottom()) < 0.1 and max(vl.mapToScene(vl.drawn().p1()).y(), vl.mapToScene(vl.drawn().p2()).y()) < lr.top(),
	"a vertical line: Right puts it at the bottom")
vl.edit = v.editshape
names = []
QTimer.singleShot(100, lambda: (names.extend(v.shapedlg.align.itemText(i) for i in range(3)), v.shapedlg.reject()))
v.editshape(vl)
w.activateWindow()
QTest.qWaitForWindowActive(w)
check(names == ["Center", "Top", "Bottom"], "its form says Top and Bottom")
hl.setprops({"align": "center"})
check(hl.mapRectToScene(hl.labelrect()).center().x() == 500, "Center: in the middle of its points, as before")
# drawings selected are copied with the copy key and pasted under the mouse
v.scene().clearSelection()
hl.setSelected(True)
n = len(v.shapes())
old = set(v.shapes())
v.setFocus()
QTest.keyClick(vp, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
md = QApplication.clipboard().mimeData()
check(md.hasFormat(viewer.DRAWMIME), "copied")
at = QPointF(700, 600)
check(v.pastedrawings(at) and len(v.shapes()) == n + 1, "pasted")
new = (set(v.shapes()) - old).pop()
check(new.isSelected() and not hl.isSelected() and new.extend and new.label == "PDH"
	and abs(new.mapToScene(new.line().center()).y() - 600) < 25, "a copy, selected, where the mouse is")
v.undo.undo()
check(len(v.shapes()) == n, "undo the paste")
QTest.keyClick(vp, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
check(len(v.shapes()) == n + 1, "the paste key pastes")
v.undo.undo()
QApplication.clipboard().clear()
v.scene().removeItem(hl); v.scene().removeItem(vl)
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
# the crosshair follows the mouse on the image, but not while drawing
w = mainwin.MainWindow(d)
w.resize(1500, 950)
w.show()
QTest.qWaitForWindowExposed(w)
v, vp = w.view, w.view.viewport()
v.setcrosshair(True)
w.toolacts["select"].trigger()
QTest.mouseMove(vp, QPoint(300, 200))
app.processEvents()
c = v.mapToScene(QPoint(300, 200))
check(v.cross is not None and abs(v.cross.x() - c.x()) < 1 and abs(v.cross.y() - c.y()) < 1, "the crosshair is at the mouse")
check(vp.cursor().shape() == Qt.CursorShape.CrossCursor, "a cross cursor")
img = vp.grab().toImage()
check(img.pixelColor(300, 40) != img.pixelColor(310, 40) or img.pixelColor(300, 41) != img.pixelColor(310, 41)
	or img.pixelColor(300, 43) != img.pixelColor(310, 43), "its vertical line is drawn")
vp.grab().save(os.path.join(sys.argv[1] if len(sys.argv) > 1 else d, "crosshair.png"))
w.toolacts["line"].trigger()
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(300, 200))
QTest.mouseMove(vp, QPoint(400, 260))
check(v.cross is None, "no crosshair while drawing")
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(400, 260))
QTest.mouseMove(vp, QPoint(420, 270))
check(v.cross is not None, "back after drawing")
w.toolacts["select"].trigger()
v.setFocus()
QTest.keyClick(vp, Qt.Key.Key_X)
check(not v.crosshair and v.cross is None and not w.drawbar.crossact.isChecked(), "X turns it off")
check(vp.cursor().shape() == Qt.CursorShape.OpenHandCursor, "the hand again")
check(drawbar.fibsettings().value("crosshair") in (False, "false"), "remembered")
w.drawbar.crossact.trigger()
check(v.crosshair, "the Cross button turns it on")
# copying the image, with its drawings, to the clipboard
QApplication.clipboard().clear()
w.copyimgact.trigger()
ci = QApplication.clipboard().image()
pm = QImage(w.journal.path(w.current))
check(not ci.isNull() and ci.size() == pm.size(), "the image copied at its size")
q = v.mapToScene(QPoint(350, 230))
check(any(ci.pixelColor(int(q.x()) + dx, int(q.y()) + dy) != pm.pixelColor(int(q.x()) + dx, int(q.y()) + dy)
	for dx in range(-3, 4) for dy in range(-3, 4)), "with its drawings")
QApplication.clipboard().clear()
w.pending = {}	# the line drawn, not to be saved
w.close()
print("ALL OK")
