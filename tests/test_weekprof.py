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
	for k in range(5):
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
	for x in range(X0 - 60, MON + 4*DAY + int(DAY*.7), 5):	# the Friday before too
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
