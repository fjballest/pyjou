#
# headless tests of File ▸ Export: QT_QPA_PLATFORM=offscreen python3 tests/test_export.py
#
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QFileDialog

import mainwin
import sandbox
import ocrworker
from drawing import RectShape

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

d = tempfile.mkdtemp()
for n in ("day261013.png", "day261014.png", "day261019weekprof.png"):
	img = QImage(400, 200, QImage.Format.Format_RGB32)
	img.fill(QColor(240, 240, 230))
	img.save(os.path.join(d, n))
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])

app = QApplication.instance() or QApplication([])
w = mainwin.MainWindow(d)
w.show()
names = [a.text() for a in w.menuBar().actions()[0].menu().actions()]
check("&Export Selected…" in names and "Export &All…" in names, "the File menu has both")

# draw a red box on one, not saved yet
w.reveal(w.journal.find("day261014.png"))
w.view.additem(RectShape(QRectF(10, 10, 100, 50), "#ff0000", 4))
w.view.drawchanged.emit()
app.processEvents()
check("day261014.png" in w.pending, "a drawing not saved")

out = os.path.join(tempfile.mkdtemp(), "all")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out, ""))
w.export(True)
z = zipfile.ZipFile(out + ".zip")
check(sorted(z.namelist()) == ["day261013.png", "day261014.png", "day261019weekprof.png"], f"all shown, as PNGs: {z.namelist()}")
check(z.getinfo("day261014.png").compress_type == zipfile.ZIP_DEFLATED, "compressed")
img = QImage.fromData(z.read("day261014.png"))
check(img.width() == 400 and img.pixelColor(10, 30).red() > 200 and img.pixelColor(10, 30).green() < 80,
	"with its drawing, at its size")
check(z.read("day261013.png") == open(os.path.join(d, "day261013.png"), "rb").read(), "one with no drawing as it is")

# only the one selected
out = os.path.join(tempfile.mkdtemp(), "one.zip")
w.export(False)
check(zipfile.ZipFile(out).namelist() == ["day261014.png"], "only the selected one")

# a group selected: its captures
g = w.items["day261014.png"].parent()
while g.parent() is not None:
	g = g.parent()
w.list.setCurrentItem(g)
out = os.path.join(tempfile.mkdtemp(), "group.zip")
w.export(False)
check(len(zipfile.ZipFile(out).namelist()) == 3, "the captures of the year selected")

# a search leaves out the others
w.searchbox.setText("nothing-matches-this")
w.applysearch()
out = os.path.join(tempfile.mkdtemp(), "none.zip")
w.export(True)
check(not os.path.exists(out), "nothing shown, nothing exported")
