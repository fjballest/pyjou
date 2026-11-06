#
# headless tests of the Window menu layouts: QT_QPA_PLATFORM=offscreen python3 tests/test_layout.py
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

import winlayout as wl

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

r = QRect(0, 0, 1200, 800)
g = wl.grid(r, 3)
check([x.getRect() for x in g] == [(0, 0, 600, 400), (600, 0, 600, 400), (0, 400, 1200, 400)], "a mosaic of 3, the last one wider")
check(len(wl.grid(r, 4)) == 4 and wl.grid(r, 4)[3].getRect() == (600, 400, 600, 400), "a mosaic of 4")
check([x.getRect() for x in wl.mainleft(r, 3)] == [(0, 0, 600, 800), (600, 0, 600, 400), (600, 400, 600, 400)], "main on the left")
check([x.getRect() for x in wl.maintop(r, 3)] == [(0, 0, 1200, 400), (0, 400, 600, 400), (600, 400, 600, 400)], "main on top")
check(wl.mainleft(r, 1)[0] == r, "main alone fills it")
check(sum(x.width() for x in wl.split(QRect(0, 0, 1001, 10), 3)) == 1001, "no pixels lost")
c = wl.cascade(r, 3)
check(len(c) == 3 and c[0].topLeft() != c[1].topLeft(), "cascade")

app = QApplication.instance() or QApplication([])
ws = [QMainWindow() for _ in range(3)]
for i, w in enumerate(ws):
	w.setWindowTitle(f"w{i}")
	w.resize(300, 200)
	w.show()
tool = QWidget(None, Qt.WindowType.Tool)
tool.setWindowTitle("tool")
tool.show()
app.processEvents()
check(wl.windows(ws[1])[0] is ws[1] and tool not in wl.windows(ws[1]) and len(wl.windows(ws[1])) == 3,
	"the windows, the active one first, no tool windows")
scr = wl.screenof(ws[1])
wl.layout(wl.grid, ws[1])
app.processEvents()
cells = wl.grid(scr, 3)
check(ws[1].frameGeometry() == cells[0] and {(w.frameGeometry().x(), w.frameGeometry().y()) for w in ws} ==
	{(c.x(), c.y()) for c in cells}, "tile puts the active one first, the others in the other cells")
wl.layoutone(lambda s: wl.halves(s)[1], ws[2])
app.processEvents()
check(ws[2].frameGeometry() == wl.halves(scr)[1], "right half, with its frame")
m = wl.windowmenu(ws[0])
m.aboutToShow.emit()
titles = [a.text() for a in m.actions()]
check("&Tile" in titles and "Left &Half" in titles and "w0" in titles and "tool" not in titles, "the menu")
check([a.isChecked() for a in m.actions() if a.text() == "w0"] == [True], "this window checked")
print("ALL OK")
