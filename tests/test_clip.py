#
# headless tests of cut, copy and paste of captures: QT_QPA_PLATFORM=offscreen python3 tests/test_clip.py
#
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

import journal
import mainwin
import ocrworker
import sandbox

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

def mkimage(d, name):
	img = QImage(800, 450, QImage.Format.Format_RGB32)
	img.fill(QColor(240, 240, 230))
	img.save(os.path.join(d, name))

a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
mkimage(a, "day261014.png")
mkimage(a, "day261011weekprof.png")
with open(os.path.join(a, "day261014.txt"), "w") as f:
	f.write("FVG at the open")
with open(os.path.join(a, "day261014" + journal.DRAWEXT), "w") as f:
	json.dump({"shapes": [{"kind": "text", "text": "hello"}]}, f)
ja = journal.Journal(a)
ja.settext(ja.find("day261014.png"), [["DAX", 0.9]])
ja.savecache()
mkimage(b, "day261014.png")	# b has that day already
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])

# the journal
jb = journal.Journal(b)
n = jb.paste(ja, ja.find("day261014.png"))
check(n == "day261014b.png", "pasted with the next name for its day")
e = jb.find(n)
check(e.notes == "FVG at the open" and "hello" in e.drawtext and e.tags == ["DAX"], "with its notes, drawing and tags")
check(not jb.needsocr(e), "no need to read it again")
check(os.path.exists(os.path.join(a, "day261014.png")), "a copy leaves the original")
n = jb.paste(ja, ja.find("day261011weekprof.png"), move=True)
check(n == "day261011weekprof.png" and jb.find(n).week, "a week profile keeps its name when free")
check(not os.path.exists(os.path.join(a, "day261011weekprof.png")) and ja.find("day261011weekprof.png") is None,
	"a move removes it from its journal")
n = ja.paste(ja, ja.find("day261014.png"))
check(n == "day261014b.png" and ja.find(n).notes == "FVG at the open", "a copy in the same journal")

# the window
app = QApplication.instance() or QApplication([])
w = mainwin.MainWindow(a)
w.show()
w.reveal(w.journal.find("day261014.png"))
w.updateclipacts()
check(w.cutact.isEnabled() and w.copyact.isEnabled(), "cut and copy for a capture")
w.clipcapture(True)
c = w.clipped()
check(c == {"dir": w.journal.dir, "name": "day261014.png", "cut": True}, "cut on the clipboard")
check(w.items["day261014.png"].foreground(0).color() == QColor("gray"), "the capture cut is gray")
w.pastecapture()
check(os.path.exists(os.path.join(a, "day261014.png")), "a cut pasted in its own journal stays")
w.openjournal(b)
w.updateclipacts()
check(w.pasteact.isEnabled(), "paste in another journal")
w.pastecapture()
check(w.journal.find("day261014c.png") is not None and w.current.name == "day261014c.png", "pasted and shown")
check(not os.path.exists(os.path.join(a, "day261014.png")) and not os.path.exists(os.path.join(a, "day261014.txt"))
	and not os.path.exists(os.path.join(a, "day261014" + journal.DRAWEXT)), "a cut is moved")
check(w.clipped() is None, "a cut can't be pasted twice")
check(w.journal.find("day261014c.png").notes == "FVG at the open", "the notes went with it")
w.reveal(w.journal.find("day261014.png"))
w.clipcapture(False)
w.pastecapture()
check(w.journal.find("day261014d.png") is not None and w.clipped() is not None, "a copy can be pasted again")
w.close()
QApplication.clipboard().clear()	# a clipboard left set crashes Qt at exit
print("ALL OK")
