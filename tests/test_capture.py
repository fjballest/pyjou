#
# headless tests of adding captures: QT_QPA_PLATFORM=offscreen python3 tests/test_capture.py
#
import os
import sys
import tempfile
import time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

from PySide6.QtCore import QMimeData, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDropEvent, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import capture
import journal
import mainwin
import ocrworker

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

def mkimage(path, made, fmt=None):
	img = QImage(800, 450, QImage.Format.Format_RGB32)
	img.fill(QColor(230, 240, 250))
	img.save(path, fmt)
	t = time.mktime(made.timetuple()) + 3600 * 10
	os.utime(path, (t, t))
	return path

# the dates written in the charts
d = capture.datesin(["mié 26-10-14", "26-10-14   09.30", "Modificado: 29 sept 2026", "15 Sep 25.410,0",
	"Captura de pantalla 2026-10-23 a las 9.30.12", "14/10/2026", "Oct 14, 2026", "mar 26",
	"4035 25.440,0", "H25.674,5 L25.665,5"], 2026)
check(d == {date(2026, 10, 14): 4, date(2026, 9, 29): 1, date(2026, 9, 15): 1, date(2026, 10, 23): 1},
	f"dates found {dict(d)}")

src = tempfile.mkdtemp()
def raw(*texts):
	return [[t, 0.9] for t in texts]

# the last date in the image not after the day the file was changed
p = mkimage(os.path.join(src, "Captura de pantalla.png"), date(2026, 10, 15))
best, week, cands = capture.guess(p, raw("mié 26-10-14", "jue 26-10-15", "jue 26-10-15 mié 26-10-14", "lun 26-10-19"))
check(best == date(2026, 10, 15) and not week, f"the last day not after the file's {best} {week}")
check([c for c, _ in cands] == [date(2026, 10, 15), date(2026, 10, 14), date(2026, 10, 19)],
	f"the guess first, then the others as found {cands}")
check(list(capture.datesin(["14 Sep 2026 26-09-21"])) == [date(2026, 9, 14), date(2026, 9, 21)], "in the order written")
best, week, cands = capture.guess(p)
check(best == date(2026, 10, 15) and not week and len(cands) == 1, "no OCR yet: the file date")
best, week, _ = capture.guess(p, raw("lun 26-10-19"))
check(best == date(2026, 10, 15), "all dates after the file's: the file date")
# a Sunday and the Friday after: a week profile for that Sunday
best, week, _ = capture.guess(p, raw("dom 26-10-11", "lun 26-10-12", "vie 26-10-16", "mié 26-10-14"))
check(best == date(2026, 10, 11) and week, f"Sunday and its Friday: week profile {best} {week}")
best, week, _ = capture.guess(p, raw("dom 26-10-04", "vie 26-10-16", "mié 26-10-14"))
check(best == date(2026, 10, 14) and not week, "a Sunday without its Friday doesn't count")
# a weekend day is a week profile, named on its Sunday
p = mkimage(os.path.join(src, "sun.png"), date(2026, 10, 18))
best, week, _ = capture.guess(p, None)
check(best == date(2026, 10, 18) and week, "changed on Sunday: week profile")
best, week, _ = capture.guess(p, raw("lun 26-10-19"))
check(best == date(2026, 10, 18) and week, "a week profile made on Sunday shows the Monday after")
best, week, _ = capture.guess(p, raw("sáb 26-10-17", "vie 26-10-16"))
check(best == date(2026, 10, 18) and week, "Saturday found: week profile on the Sunday")
check(capture.weekname(date(2026, 10, 19)) == date(2026, 10, 18) and
	capture.weekname(date(2026, 10, 22)) == date(2026, 10, 18), "weekname")

# names: the first capture of a day has none, then b, c...
jd = tempfile.mkdtemp()
mkimage(os.path.join(jd, "day261014.png"), date(2026, 10, 14))
mkimage(os.path.join(jd, "day261011weekprof.png"), date(2026, 10, 11))
j = journal.Journal(jd)
check(j.newname(date(2026, 10, 15)) == "day261015.png", "first of a day")
check(j.newname(date(2026, 10, 14)) == "day261014b.png", "second of a day")
check(j.newname(date(2026, 10, 11), True) == "day261011weekprofb.png", "second week profile")
mkimage(os.path.join(jd, "day261014b.png"), date(2026, 10, 14))
j.load()
check(j.newname(date(2026, 10, 14)) == "day261014c.png", "third of a day")

# the window: a capture dropped is added after the dialog
ocrworker.ocrcommand = lambda: (sys.executable, ["-c",
	"import json, sys\n"
	"for l in sys.stdin:\n"
	"    print(json.dumps({'path': l.strip(), 'raw': [['mié 26-10-14', 0.9], ['EQH sweep', 0.9]]}), flush=True)"])
app = QApplication(sys.argv)
w = mainwin.MainWindow(jd)
w.show()
QTest.qWaitForWindowExposed(w)
dlgs = []
def answer():
	dl = QApplication.activeModalWidget()
	if not isinstance(dl, capture.CaptureDialog) or dl.raw is None:
		QTimer.singleShot(50, answer)
		return
	dlgs.append((dl.date(), dl.week(), dl.name(), dl.cands.count()))
	dl.accept()
QTimer.singleShot(50, answer)
new = mkimage(os.path.join(src, "shot.jpg"), date(2026, 10, 14), "JPG")
md = QMimeData()
md.setUrls([QUrl.fromLocalFile(new)])
ev = QDropEvent(QPointF(100, 100), Qt.DropAction.CopyAction, md, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
w.dropEvent(ev)
for _ in range(200):
	QTest.qWait(50)
	if w.journal.find("day261014c.png"):
		break
check(dlgs and dlgs[0][:3] == (date(2026, 10, 14), False, "day261014c.png"), f"dialog guessed {dlgs}")
e = w.journal.find("day261014c.png")
check(e is not None and w.current is e, "added and shown")
check(QImage(os.path.join(jd, "day261014c.png")).width() == 800, "converted to PNG")
check(os.path.exists(new), "the original is kept")
check("EQH" in e.tags and not w.journal.needsocr(e), "the OCR is kept as its tags")
# picking a date found sets the week profile box: on for weekend days
dl = capture.CaptureDialog(w.journal, new)
dl.candlist = [(date(2026, 10, 17), "a Saturday"), (date(2026, 10, 14), "a Wednesday"), (date(2026, 10, 18), "a Sunday")]
dl.candpicked(0)
check(dl.week() and dl.date() == date(2026, 10, 18) and dl.name() == "day261018weekprof.png", "Saturday: week profile on Sunday")
dl.candpicked(1)
check(not dl.week() and dl.date() == date(2026, 10, 14), "Wednesday: a day")
dl.candpicked(2)
check(dl.week() and dl.date() == date(2026, 10, 18), "Sunday: week profile")
dl.weekbox.setChecked(False)
check(not dl.week() and dl.date() == date(2026, 10, 18), "the box can be changed by hand")
dl.reject()
# dropping an image of the journal itself does nothing
from PySide6.QtWidgets import QMessageBox
said = []
QMessageBox.information = staticmethod(lambda *a, **k: said.append(a[2]))
w.addcaptures([os.path.join(jd, "day261014.png")])
check(said and "already" in said[0], "already in the journal")
# not images are not taken
md2 = QMimeData()
md2.setUrls([QUrl.fromLocalFile(os.path.join(jd, "notes.txt"))])
check(w.droppedimages(QDropEvent(QPointF(1, 1), Qt.DropAction.CopyAction, md2,
	Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)) == [], "only images")
# a double click on a capture of the list changes its date, with its notes and drawing
e = w.journal.find("day261014b.png")
w.journal.savenotes(e, "some notes")
w.journal.savedrawing(e, {"version": 1, "shapes": [{"kind": "text", "pos": [10, 10], "text": "EQH", "color": "#000000", "size": 22}]})
w.journal.settext(e, raw("vie 26-10-16", "SIBI"))
w.reload()
def answer2():
	dl = QApplication.activeModalWidget()
	if not isinstance(dl, capture.CaptureDialog):
		QTimer.singleShot(50, answer2)
		return
	dlgs.append((dl.windowTitle(), dl.date(), dl.week(), dl.name(), [c for c, _ in dl.candlist]))
	dl.candpicked([c for c, _ in dl.candlist].index(date(2026, 10, 16)))	# the day found in the image
	dlgs.append(dl.name())
	dl.accept()
dlgs.clear()
QTimer.singleShot(50, answer2)
it = w.items["day261014b.png"]
w.list.itemDoubleClicked.emit(it, 0)
for _ in range(100):
	QTest.qWait(50)
	if w.journal.find("day261016.png"):
		break
check(dlgs[0][:4] == ("Change Date", date(2026, 10, 14), False, "day261014b.png"), f"opens with its date {dlgs}")
check(date(2026, 10, 16) in dlgs[0][4], "offers the dates read before")
check(dlgs[1] == "day261016.png", "a date with no capture gets the plain name")
n = w.journal.find("day261016.png")
check(n is not None and w.journal.find("day261014b.png") is None and w.current is n, "renamed and shown")
check(os.path.exists(os.path.join(jd, "day261016.txt")) and os.path.exists(os.path.join(jd, "day261016.drw"))
	and not os.path.exists(os.path.join(jd, "day261014b.txt")), "notes and drawing go with it")
check(n.notes == "some notes" and "SIBI" in n.tags and not w.journal.needsocr(n), "keeps its notes and tags")
# keeping its date keeps its name; turning it into a week profile renames it
dl = capture.CaptureDialog(w.journal, w.journal.path(n), entry=n)
check(dl.name() == "day261016.png", "same date, same name")
dl.dateedit.setDate(dl.dateedit.date().addDays(2))
dl.weekbox.setChecked(True)
check(dl.name() == "day261018weekprof.png", "now a week profile")
dl.reject()
w.close()
print("ALL OK")
