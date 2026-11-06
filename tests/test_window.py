#
# headless tests of New Window: QT_QPA_PLATFORM=offscreen python3 tests/test_window.py
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

import mainwin
import ocrworker
import sandbox

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
for d, names in ((a, ("day261013.png", "day261014.png", "day261015.png")), (b, ("day261020.png",))):
	for n in names:
		img = QImage(800, 450, QImage.Format.Format_RGB32)
		img.fill(QColor(240, 240, 230))
		img.save(os.path.join(d, n))
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])

app = QApplication.instance() or QApplication([])
w = mainwin.MainWindow(a)
w.show()
w.reveal(w.journal.find("day261014.png"))
w2 = w.newwindow()
app.processEvents()
check(w2 in mainwin.windows and w2.isVisible(), "a new window")
check(w2.journal.dir == w.journal.dir and w2.current.name == "day261014.png", "at the same journal and image")
check(w2.size() == w.size(), "with the same size")
w2.step(1)
check(w2.current.name == "day261015.png" and w.current.name == "day261014.png", "each one browses on its own")
w2.openjournal(b)
check(w2.journal.dir == os.path.realpath(b) or w2.journal.dir == os.path.abspath(b), "it can open another journal")
check(w.journal.dir == os.path.abspath(a), "the first one stays")

# notes written in one window show in the other one on the same journal
w3 = w.newwindow()
w3.notes.setPlainText("FVG")
w3.savenotes()
w.reload()
check(w.notes.toPlainText() == "FVG", "notes written in another window")

for x in (w2, w3):
	x.close()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
check(mainwin.windows == [], "closed windows go away")
w.close()
QApplication.clipboard().clear()
print("ALL OK")
