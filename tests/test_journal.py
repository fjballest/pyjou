#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_journal.py
# The OCR is faked, so easyocr isn't needed.
#
import os
import shutil
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()	# no real recent list or journals

from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import journal
import json
from search import Search
from tags import cleantags

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

# names
e = journal.parsename("day261014.png")
check(e and e.day == date(2026, 10, 14) and not e.week, "day name")
e = journal.parsename("day261011weekprof.png")
check(e and e.week and e.day == date(2026, 10, 11) and e.weekmonday() == date(2026, 10, 12), "a Sunday week profile is for the next week")
check(journal.parsename("day261014weekprof.png").weekmonday() == date(2026, 10, 12), "other week profiles are for their own week")
e = journal.parsename("day260916b.png")
check(e and e.extra == "b", "second snapshot name")
check(journal.parsename("day261399.png") is None and journal.parsename("x.png") is None, "not journal names")

# tags
raw = [("premarket trending (CPI 0830)", .9), ("PPI, vela dibujada en 1sec!!", .8),
	("toma liquidez en cuerpos en PMKT -0.5", .9), ("30.415,00", .99), ("m15", .7),
	("RTHOG ce 14 Oct", .9), ("xkcdq", .9), ("VENDER", .9), ("SMT M15 ES", .6), ("garbage", .1),
	("Toma", .9), ("judas tomando liquidez", .9)]
t = cleantags(raw)
print(t)
for w in ["premarket", "trending", "CPI", "PPI", "vela", "dibujada", "toma", "liquidez", "PMKT", "m15", "RTHOG", "SMT", "ES", "judas"]:
	check(w in t, f"tag {w}")
for w in ["en", "30.415,00", "0830", "Oct", "14", "xkcdq", "VENDER", "garbage", "Toma", "ce"]:
	check(w not in t, f"no tag {w}")

# a journal with fake images
d = tempfile.mkdtemp()
names = ["day261011weekprof.png", "day261012.png", "day261013.png", "day261014.png",
	"day261014b.png", "day261018weekprof.png", "day261019.png", "notes.txt", "other.png"]
for i, n in enumerate(names):
	if n.endswith(".png"):
		img = QImage(400, 300, QImage.Format.Format_RGB32)
		img.fill(QColor(30 * i, 100, 200))
		img.save(os.path.join(d, n))
	else:
		open(os.path.join(d, n), "w").write("x")
with open(os.path.join(d, "day261013.txt"), "w") as f:
	f.write("rebote limpio en el FVG")

fake = {
	"day261011weekprof.png": "weekly profile classic",
	"day261012.png": "judas swing EQLs",
	"day261013.png": "silver bullet",
	"day261014.png": "toma liquidez EQH",
	"day261014b.png": "second look",
	"day261018weekprof.png": "seek destroy",
	"day261019.png": "silver bullet EQL",
}
# a fake OCR process: answers with the texts in fake and logs what it read
fakedir = tempfile.mkdtemp()
fakejson = os.path.join(fakedir, "fake.json")
fakelog = os.path.join(fakedir, "calls")
fakeprog = os.path.join(fakedir, "fakeocr.py")
with open(fakeprog, "w") as f:
	f.write(f"""import json, os, sys
for line in sys.stdin:
	p = line.strip()
	fake = json.load(open({fakejson!r}))
	open({fakelog!r}, "a").write(os.path.basename(p) + "\\n")
	print(json.dumps({{"path": p, "raw": [[fake[os.path.basename(p)], 0.9]]}}), flush=True)
""")
def calls():
	return open(fakelog).read().split() if os.path.exists(fakelog) else []
def savefake():
	json.dump(fake, open(fakejson, "w"))
import ocrworker
ocrworker.ocrcommand = lambda: (sys.executable, [fakeprog])

savefake()
j = journal.Journal(d)
check([x.name for x in j.entries] == [n for n in names if n.startswith("day")], "entries in date order, week first")
check(j.find("day261013.png").notes.startswith("rebote"), "notes read")
check(j.weekof(j.find("day261014.png")).name == "day261011weekprof.png", "week of a day")
check([x.name for x in j.daysof(j.find("day261018weekprof.png"))] == ["day261019.png"], "days of a week")
check(j.nearest(date(2026, 10, 15)).name == "day261019.png", "nearest date after")
check(j.nearest(date(2026, 10, 30)).name == "day261019.png", "nearest date past the end")

# search
def found(expr):
	s = Search(expr)
	return [x.name[3:9] + ("w" if x.week else x.extra) for x in j.entries if s.match(x)]
for x in j.entries:
	j.settext(x, [(fake[x.name], .9)])
check(found("silver") == ["261013", "261019"], "search a tag")
check(found("eql") == ["261012", "261019"], "search ignores case and the final s")
check(found("EQ*") == ["261012", "261014", "261019"], "search with *")
check(found("silver !eql") == ["261013"], "search with not")
check(found("judas | seek") == ["261012", "261018w"], "search with or")
check(found("(silver bullet) | !(e*)") == ["261011w", "261013", "261014b", "261018w", "261019"], "search with groups")
check(found("rebote") == ["261013"], "search the notes")
check(found("") == [x.name[3:9] + ("w" if x.week else x.extra) for x in j.entries], "empty search")
for bad in ["(a", "a)", "|", "!", "a |"]:
	check(Search.error(bad) is not None, f"bad search {bad!r}")
j.savecache()
j2 = journal.Journal(d)
check(j2.find("day261019.png").tags == ["silver", "bullet", "EQL"] and not j2.needsocr(j2.find("day261019.png")),
	"tags cached")
os.utime(os.path.join(d, "day261019.png"), (1, 1))
check(j2.needsocr(j2.find("day261019.png")), "changed image read again")
os.remove(os.path.join(d, journal.TAGSFILE))

# the window
import mainwin
app = QApplication(sys.argv)
w = mainwin.MainWindow(d)
w.show()
def waitocr():
	for _ in range(200):
		QTest.qWait(30)
		if w.ocrworker is None:
			return
	raise AssertionError("ocr never ended")
waitocr()
check(sorted(calls()) == sorted(fake), "every image read once")
check(os.path.exists(os.path.join(d, journal.TAGSFILE)), "tags saved")
check(w.current.name == "day261019.png", "starts at the last image")
check("silver" in w.tagslabel.text(), "tags shown")
w.step(-1)
check(w.current.name == "day261018weekprof.png", "previous")
w.toggleweek()
check(w.current.name == "day261019.png", "week to its first day")
w.toggleweek()
check(w.current.name == "day261018weekprof.png", "day to its week")
w.jump(False)
check(w.current.name == "day261011weekprof.png", "first")
w.calendarclicked(mainwin.QDate(2026, 10, 13))
check(w.current.name == "day261013.png" and "rebote" in w.notes.toPlainText(), "calendar goes to a day with its notes")
w.calendarclicked(mainwin.QDate(2026, 10, 16))
check(w.current.name == "day261019.png", "calendar goes to the next day with an image")

# groups
def isopen(*key):
	return w.groups[key].isExpanded()
check(sorted(k[0] for k in w.groups) == ["m", "w", "w", "y"], "a year, a month and two weeks")
check(isopen("y", 2026) and isopen("m", 2026, 10) and isopen("w", 2026, 10, date(2026, 10, 19)), "last week open")
check(isopen("w", 2026, 10, date(2026, 10, 12)), "the week before open too, as the last has one day")
check(w.groups[("w", 2026, 10, date(2026, 10, 12))].childCount() == 5, "week profile and days in their week")
w.toggleall()
check(not any(g.isExpanded() for g in w.groups.values()) and w.allbtn.text() == "▸", "collapse all")
w.jump(False)
check(isopen("w", 2026, 10, date(2026, 10, 12)) and isopen("y", 2026) and w.list.currentItem() is w.items[w.current.name],
	"moving opens the group of the image")
w.toggleall()
check(w.allbtn.text() == "▸", "the triangle says some groups are still closed")
w.toggleall()
check(all(g.isExpanded() for g in w.groups.values()) and w.allbtn.text() == "▾", "expand all")
g = w.groups[("w", 2026, 10, date(2026, 10, 19))]
w.groupclicked(g, 0)
check(not g.isExpanded(), "clicking a group closes it")
w.applysearch()
check(not w.groups[("w", 2026, 10, date(2026, 10, 19))].isExpanded(), "groups stay as they were")
w.groupclicked(w.groups[("w", 2026, 10, date(2026, 10, 19))], 0)
w.jump(True)

# notes are saved
w.jump(False)
w.notes.setPlainText("a classic week")
QTest.qWait(mainwin.SAVEDELAY + 200)
p = os.path.join(d, "day261011weekprof.txt")
check(open(p).read() == "a classic week", "notes saved after typing")
w.notes.setPlainText("now changed")
w.step(1)	# leaving saves at once
check(open(p).read() == "now changed", "notes saved when leaving")
w.step(-1)
w.notes.setPlainText("")
w.step(1)
check(not os.path.exists(p), "empty notes remove the file")

# search box
w.searchbox.setText("silver")
QTest.qWait(400)
check([x.name for x in w.shown] == ["day261013.png", "day261019.png"] and len(w.items) == 2, "search filters the list")
check(w.current.name in ("day261013.png", "day261019.png"), "the image shown is one found")
w.searchbox.setText("(silver")
QTest.qWait(400)
check(len(w.shown) == 2 and "missing" in w.searchbox.toolTip(), "a bad search keeps the last one")
w.searchbox.setText("")
QTest.qWait(400)
w.weeksbox.setChecked(False)
check(all(not x.week for x in w.shown), "weeks hidden")
w.weeksbox.setChecked(True)
w.tagclicked("judas")
check([x.name for x in w.shown] == ["day261012.png"], "clicking a tag searches it")
w.searchbox.setText("")
QTest.qWait(400)

# a new image shows up
shutil.copy(os.path.join(d, "day261019.png"), os.path.join(d, "day261020.png"))
fake["day261020.png"] = "new one"
savefake()
w.reload()
waitocr()
check(w.journal.find("day261020.png").tags == ["new", "one"], "new image tagged")
w.jump(True)
w.retag()
waitocr()
check(calls().count("day261020.png") == 2, "read tags again")
w.grab().save(os.path.join(sys.argv[1] if len(sys.argv) > 1 else d, "pyjou.png"))
w.close()
print("ALL OK")
