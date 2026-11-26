#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_v3.py
# notes and search in the data view, the main window of the Window menu,
# and new windows in other time frames, laid out with the one they came from.
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()
from datetime import date, datetime, timezone

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
import mainwin
import m15
import ocrworker
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])

j = tempfile.mkdtemp()
img = QImage(800, 450, QImage.Format.Format_RGB32)
img.fill(QColor(240, 240, 230))
img.save(os.path.join(j, "day261110.png"))
start = int(datetime(2026, 11, 1, 23, 0, tzinfo=timezone.utc).timestamp())	# Sunday 1 Nov 18:00 New York
src = tempfile.mkdtemp()
with open(os.path.join(src, "MNQ.m15.csv"), "w") as f:
	f.write("time,open,high,low,close\n")
	for k in range(96 * 7 * 2):
		p = 1000 + (k % 40)
		f.write(f"{start + 900 * k},{p},{p + 2},{p - 2},{p + 1}\n")
m15.importfile(j, os.path.join(src, "MNQ.m15.csv"))

w = mainwin.MainWindow(j)
w.show()
app.processEvents()
w.setdatamode(True)
w.showdata(("d", date(2026, 11, 3)), force=True)
check(not w.notes.isReadOnly() and w.notes.toPlainText() == "", "notes can be written in the data view")
w.notes.setPlainText("gap up at the open")
w.showdata(("d", date(2026, 11, 4)))
check(w.data.readnotes("d", date(2026, 11, 3)) == "gap up at the open", "kept when going to another day")
check("¶" in w.datapanel.rows[("d", date(2026, 11, 3))].text(0), "the day marked as having notes")
w.showdata(("d", date(2026, 11, 3)))
check(w.notes.toPlainText() == "gap up at the open", "and shown again")
check(w.searchbox.isVisible(), "the search in the data view")
w.searchbox.setText("CPI")
w.applysearch()
days = [k for k in w.datapanel.keys() if k[0] == "d"]
check(days == [("d", date(2026, 11, 10))], "searching the news tags")
check(("w", date(2026, 11, 9)) in w.datapanel.keys() and ("w", date(2026, 11, 2)) not in w.datapanel.keys(), "with the week it is in")
w.searchbox.setText("gap")
w.applysearch()
check([k for k in w.datapanel.keys() if k[0] == "d"] == [("d", date(2026, 11, 3))], "and the notes")
w.searchbox.setText("")
w.applysearch()
check(len([k for k in w.datapanel.keys() if k[0] == "d"]) == 10, "all again")
w.setdatamode(False)
check(not w.datamode and w.current is not None, "back to the captures")

# new windows in other time frames, laid out with this one (on a screen
# with room for them: the offscreen one is small)
import winlayout
from PySide6.QtCore import QRect
winlayout.screenof = lambda w: QRect(0, 0, 2560, 1400)
w.setdatamode(True)
w.showdata(("d", date(2026, 11, 3)), force=True)
w.filltfwindows()
names = [a.text() for a in w.newwinmenu.actions()]
check("New Window in h1" in names and "New Window in m15" in names, "a menu of time frames")
next(a for a in w.newwinmenu.actions() if a.text() == "New Window in h1").trigger()
app.processEvents()
w2 = w.tfkids[-1]
check(w2.datatf == 60 and w2.datashowntf == 60 and w2.datakey == ("d", date(2026, 11, 3)), "a window in h1 on the same day")
w.tfwindow(240)
app.processEvents()
w3 = w.tfkids[-1]
check(w3.datatf == 240 and len(w.tfkids) == 2, "and another in h4")
g1, g2, g3 = w.frameGeometry(), w2.frameGeometry(), w3.frameGeometry()
check(not g1.intersects(g2) and not g2.intersects(g3) and not g1.intersects(g3) and g1.left() == 0, "laid out around it, without overlapping")

# the main window is the one with the list
check(w2.mainwindow() is w and w.mainwindow() is w, "the main window: the one with its list")
w.showpanel(w.left, w.listact, False, keep=False)
w3.showpanel(w3.left, w3.listact, True, keep=False)
check(w2.mainwindow() is w3, "or another with its list shown")
for x in (w2, w3):
	x.close()
sys.stdout.flush()
print("ALL OK")
sys.stdout.flush()
os._exit(0)
