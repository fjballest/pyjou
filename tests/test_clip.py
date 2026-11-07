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

from PySide6.QtCore import Qt
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

# temporary journals are not recent ones
check(mainwin.istemp(a) and not mainwin.istemp("/Users/me/u/trade/DayJournalDAX"), "temporary directories")
mainwin.settings().setValue("recent", [a, "/Users/me/u/trade/DayJournalDAX"])
check(mainwin.recentjournals() == ["/Users/me/u/trade/DayJournalDAX"], "temporary journals left out of the recent ones")
mainwin.addrecent(b)
check(mainwin.recentjournals() == ["/Users/me/u/trade/DayJournalDAX"], "temporary journals not added")

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

# delete, asking first
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
def answer(button, dontask=False):
	def f():
		dl = getattr(w, "deldlg", None)
		if dl is None or not dl.isVisible():
			QTimer.singleShot(50, f)
			return
		dl.checkBox().setChecked(dontask)
		dl.button(button).click()
	QTimer.singleShot(50, f)
e = w.journal.find("day261014d.png")
w.journal.savenotes(e, "notes")
w.reveal(e)
w.clipcapture(False)
w.list.setFocus()
QTest.qWaitForWindowExposed(w)
answer(QMessageBox.StandardButton.Cancel)
QTest.keyClick(w.list, Qt.Key.Key_Delete)
check(w.journal.find("day261014d.png") is not None, "Del in the list asks, and cancel keeps it")
w.deldlg = None
answer(QMessageBox.StandardButton.Yes, dontask=True)
w.activateWindow()
w.list.setFocus()
QTest.qWait(100)
QTest.keyClick(w.list, Qt.Key.Key_Delete)
check(w.journal.find("day261014d.png") is None and not os.path.exists(os.path.join(b, "day261014d.png"))
	and not os.path.exists(os.path.join(b, "day261014d.txt")), "deleted with its notes")
check(w.clipped() is None, "the clipboard forgets it")
check(w.current is not None and w.current.name == "day261014c.png", "shows the one before it")
check(mainwin.settings().value("askdelete") in (False, "false"), "don't ask again remembered")
w.deldlg = None
w.reveal(w.journal.find("day261014c.png"))
w.deletecapture()
check(w.journal.find("day261014c.png") is None and w.deldlg is None, "deleted without asking")
mainwin.settings().setValue("askdelete", True)

# dragging a capture from the list to a day of the calendar moves it there
from datetime import date
from PySide6.QtCore import QDate, QPointF
from PySide6.QtGui import QDropEvent, QDragEnterEvent
import warnings
warnings.simplefilter("ignore", DeprecationWarning)
def cell(d):
	"""the middle of day d in the calendar"""
	w.calendar.setCurrentPage(d.year, d.month)
	v, m = w.calview, w.calview.model()
	for r in range(m.rowCount()):
		for c in range(m.columnCount()):
			p = v.visualRect(m.index(r, c)).center()
			if mainwin.calendardate(w.calendar, p) == d:
				return p
w.calendar.setCurrentPage(2026, 6)
cells = {mainwin.calendardate(w.calendar, w.calview.visualRect(w.calview.model().index(r, c)).center())
	for r in range(1, 7) for c in range(7)}
check(date(2026, 6, 1) in cells and date(2026, 5, 25) in cells and date(2026, 7, 5) in cells and len(cells) == 42,
	"the calendar cells' dates")
def drop(e, d):
	md = w.dragdata(w.items[e])
	p = QPointF(cell(d))
	vp = w.calview.viewport()
	en = QDragEnterEvent(p.toPoint(), Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
	QApplication.sendEvent(vp, en)
	ok = en.isAccepted()
	if ok:
		QApplication.sendEvent(vp, QDropEvent(p, Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
		QTest.qWait(50)
	return ok
w.reload()
names = [x.name for x in w.journal.entries]
day = next(n for n in names if "week" not in n)
e = w.journal.find(day)
w.journal.savenotes(e, "moved notes")
w.reload()
check(drop(day, date(2026, 10, 21)), "a capture can be dropped on a day")
n = w.journal.find("day261021.png")
check(n is not None and w.journal.find(day) is None and n.notes == "moved notes" and w.current is n, "moved to that day, with its notes, and shown")
check(w.calendar.selectedDate() == QDate(2026, 10, 21), "the calendar shows its day")
check(drop("day261021.png", date(2026, 10, 14)) and w.journal.find("day261021.png") is None
	and w.current.name.startswith("day261014") and w.current.name != "day261014.png", "to a day with captures: the next name")
wk = next((x.name for x in w.journal.entries if x.week), None)
if wk:
	check(drop(wk, date(2026, 10, 29)) and w.current.name == "day261025weekprof.png", "a week profile goes to the Sunday before")
md = w.dragdata(w.items[w.current.name])
check(w.owndrag(md) is w.current, "the window knows its own drags")
en = QDragEnterEvent(QPointF(5, 5).toPoint(), Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
w.dragEnterEvent(en)
check(not en.isAccepted(), "dropping it on the window does nothing")
w.close()
QApplication.clipboard().clear()	# a clipboard left set crashes Qt at exit
print("ALL OK")
