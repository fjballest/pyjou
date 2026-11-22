#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_weekprof.py
# A chart like TradingView's is drawn with known swings, and its profile
# found; then the week profile's row draws it.
#
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

from PIL import Image, ImageDraw
import weekprof
import sandbox

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

W, H = 2400, 1000
DAY = 420	# pixels a day
X0 = 100	# Sunday 18:00, where the week starts
MON = X0 + DAY // 4

def chart(path, turns):
	"""a chart of the week through turns [(t in days from Monday, price 0..1)],
	with the lines, boxes and labels that get in the way"""
	random.seed(1)
	im = Image.new("RGB", (W, H), "white")
	d = ImageDraw.Draw(im)
	d.rectangle((300, 200, 1800, 300), fill=(255, 237, 239))	# zones
	d.rectangle((900, 600, 2300, 700), fill=(255, 240, 230))
	for y in (250, 420, 640, 810):	# levels across the chart
		d.line((0, y, W, y), fill=(252, 51, 72), width=2)
	for x in range(0, W, 6):	# a dotted level
		d.rectangle((x, 520, x + 1, 521), fill=(0, 0, 0))
	for y in range(40, 950, 14):	# the week's dashed line, and the days' dotted ones
		d.line((X0, y, X0, y + 9), fill=(41, 100, 249), width=2)
	last = turns[-1][0]
	for k in range(min(5, int(last) + 1)):
		for y in range(40, 950, 5):
			d.line((MON + k*DAY, y, MON + k*DAY, y + 1), fill=(41, 100, 249), width=2)
	d.text((1500, 150), "maximo en miercoles", fill=(30, 60, 220))
	def price(t):
		for (t0, p0), (t1, p1) in zip(turns, turns[1:]):
			if t0 <= t <= t1:
				return p0 + (p1 - p0) * (t - t0) / (t1 - t0)
		return turns[-1][1]
	y = lambda p: 900 - p * 750
	prev = price(turns[0][0])
	for x in range(X0 - 60, MON + int(min(last, 4.7) * DAY), 5):	# the Friday before too
		t = (x - MON) / DAY
		p = price(max(turns[0][0], t)) if x >= X0 else 0.5 + 0.02 * random.random()
		o, c = prev, p + 0.01 * random.uniform(-1, 1)
		hi, lo = max(o, c) + 0.01, min(o, c) - 0.01
		col = (51, 175, 88) if c >= o else (0, 0, 0)
		d.line((x + 1, y(hi), x + 1, y(lo)), fill=col)
		d.rectangle((x, y(max(o, c)), x + 2, y(min(o, c)) + 1), fill=col)
		prev = c
	for i, ty in enumerate((180, 330, 600)):	# labels at the right edge
		d.rectangle((W - 140, ty, W - 60, ty + 16), fill=(252, 51, 72))
	im.save(path)

d = tempfile.mkdtemp()
path = os.path.join(d, "day261018weekprof.png")
# up Monday, down Tuesday, the high Wednesday, the low Thursday
turns = [(-0.25, 0.2), (0.5, 0.85), (1.4, 0.35), (2.6, 1.0), (3.8, 0.0), (4.6, 0.15)]
chart(path, turns)
pr = weekprof.profile(path)
print(pr)
check(pr is not None and len(pr) == len(turns), "a swing for each turn, and none for the noise")
check(all(abs(a[0] - b[0]) < 0.15 for a, b in zip(pr, turns)), "the swings on their days")
check([i for i, (t, v) in enumerate(pr) if v == 1.0] == [3] and [i for i, (t, v) in enumerate(pr) if v == 0.0] == [4],
	"the high of the week on Wednesday and its low on Thursday")
check(pr[0][0] > -0.3, "it starts at the week's line, not on the Friday before")
check(weekprof.clean([(0, .5), (1, 1), (1.02, .2), (2, .9), (3, 0)]) == [(0, .5), (2, .9), (3, 0)],
	"a pair of turns an hour apart goes")

# the profiles are kept next to the captures, which are not changed
before = open(path, "rb").read()
ps = weekprof.Profiles(d)
check(ps.get("day261018weekprof.png") == pr, "Profiles finds it")
ps.save()
check(os.path.exists(os.path.join(d, weekprof.CACHE)), "and keeps it in the journal")
check(weekprof.Profiles(d).cache["day261018weekprof.png"]["points"] == [list(p) for p in pr], "where it is found again")
check(open(path, "rb").read() == before, "the capture is untouched")

# the row of the week profile draws it
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QDate
import journal
app = QApplication(sys.argv)
from mainwin import MainWindow
win = MainWindow()
win.openjournal(d)
win.resize(1100, 700)
win.show()
app.processEvents()
it = win.items.get("day261018weekprof.png")
check(it is not None, "the week profile has a row")
win.list.scrollToItem(it)
app.processEvents()
img = win.list.viewport().grab().toImage()
r = win.list.visualItemRect(it)
hl = win.list.palette().color(win.list.palette().ColorRole.Highlight)
drawn = 0
for x in range(r.right() - 80, r.right()):
	for y in range(r.top(), r.bottom()):
		c = img.pixelColor(x, y)
		if abs(c.red() - hl.red()) + abs(c.green() - hl.green()) + abs(c.blue() - hl.blue()) < 90:
			drawn += 1
check(drawn > 20, "the row draws the profile at its right")
img.save(os.path.join(d, "row.png"))
print("row image", os.path.join(d, "row.png"))

# a week in progress, matched with the full ones
check(not weekprof.partial(pr), "a whole week is not partial")
part = [(-0.25, 0.3), (0.5, 1.0), (1.2, 0.0)]	# up Monday, down Tuesday so far
check(weekprof.partial(part), "one that ends on Tuesday is")
check(abs(weekprof.at(part, 0.85) - 0.5) < 1e-9, "levels along the segments")
like = [(-0.25, 0.25), (0.5, 0.6), (1.2, 0.1), (3, 1), (4.7, 0)]	# the same shape, smaller, then more
unlike = [(-0.25, 1), (1.2, 0), (4.7, 0.5)]
check(weekprof.similarity(part, like) > 0.9, "a week that went the same way matches, whatever its size")
check(weekprof.similarity(part, unlike) < 0.7, "one that went the other way does not")
check(weekprof.similarity(part, [(-0.25, 0), (1.0, 1)]) is None, "one that ends before it can't be compared")
check([n for s, n in weekprof.matches(part, {"a": unlike, "b": like, "c": None})] == ["b", "a"], "the best first")

path2 = os.path.join(d, "day261025weekprof.png")	# the next week, so far: Monday up, Tuesday down
chart(path2, [(-0.25, 0.3), (0.5, 0.9), (1.2, 0.0)])
pr2 = weekprof.profile(path2)
check(pr2 is not None and weekprof.partial(pr2), "the capture of a week in progress gives a partial profile")
win.reload()
app.processEvents()
win.show_(win.journal.find("day261025weekprof.png"))
win.matchweek()
app.processEvents()
check(set(win.matching) == {"day261018weekprof.png"} and win.matching["day261018weekprof.png"] > 0.7,
	"Match Week scores the full weeks like it")
check(win.matchdlg is not None and win.matchdlg.lst.count() == 1, "and lists them")
win.matchdlg.lst.setCurrentRow(0)
app.processEvents()
check(win.current.name == "day261018weekprof.png", "picking one shows it")
win.matchdlg.close()
app.processEvents()
check(win.matchsrc is None and not win.matching, "closing the list ends the match")

# adjusting a week profile by hand on its capture
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
name = "day261018weekprof.png"
win.show_(win.journal.find(name))
app.processEvents()
before = win.profiles.geom(name)["px"]
win.adjustprofile()
ed = win.adjuster
check(ed is not None and len(ed.pts) == len(before), "Adjust Week Profile draws the profile on the capture")
vp = win.view.viewport()
at = lambda p: win.view.mapFromScene(p)
# drag the second point (Monday's high) up by 50 pixels of the image
p1 = ed.pts[1]
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(p1))
QTest.mouseMove(vp, at(QPointF(p1.x(), p1.y() - 50)))
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(QPointF(p1.x(), p1.y() - 50)))
check(abs(ed.pts[1].y() - (p1.y() - 50)) < 3, "a point is dragged")
# a click in the middle of the last segment adds a point there
a, b = ed.pts[-2], ed.pts[-1]
mid = (a + b) / 2
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(mid))
check(len(ed.pts) == len(before) + 1, "a click on a segment adds a point")
QTest.mouseClick(vp, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, at(ed.pts[-2]))
check(len(ed.pts) == len(before), "a right click removes one")
# Esc drops it all
QTest.keyClick(win.view, Qt.Key.Key_Escape)
check(win.adjuster is None and win.profiles.geom(name)["px"] == before, "Esc leaves the profile as it was")
# again, and a double click keeps it
win.adjustprofile()
ed = win.adjuster
p1 = ed.pts[1]
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(p1))
QTest.mouseMove(vp, at(QPointF(p1.x(), p1.y() - 150)))
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, at(QPointF(p1.x(), p1.y() - 150)))
QTest.mouseDClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(5, 5))
app.processEvents()
after = weekprof.Profiles(d).cache[name]
check(win.adjuster is None and after.get("adjusted") and abs(after["geom"]["px"][1][1] - (p1.y() - 150)) < 3,
	"a double click keeps it, saved in the journal")
check(after["points"][1][1] == 1.0, "Monday's high, now the highest, is the week's high")
