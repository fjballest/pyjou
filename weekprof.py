# the profile of a week, found in its capture: the swings that frame the
# week (Monday up, Tuesday down, Wednesday up...), as a segmented line.
#
# The capture is a TradingView chart of the week. Its candles are found by
# their shape, not their colours: short vertical runs of dark or saturated
# red or green pixels, with the horizontal lines, the dotted ones and the
# text taken out, kept only where they follow the candles next to them. The
# week starts at the dashed blue line (the session of the week) and the days
# at the dotted blue lines; without them the week is the whole chart.
#
# The profile is a list of points (t, v): t in days from Monday 00:00 (the
# Sunday evening is below 0, Friday is 4 to 5), and v from 0 (the low of the
# week) to 1 (its high).
import json, os
import numpy as np
from PIL import Image

SWING = 0.33	# the smallest swing kept, as a part of the week's range

def runs(col):
	"""the (start, end) of the runs of True in a 1-D bool array"""
	d = np.diff(np.concatenate(([0], col.astype(np.int8), [0])))
	return np.flatnonzero(d == 1), np.flatnonzero(d == -1)

def bluelines(im):
	"""the x of the dashed blue line that starts the week (None without it)
	and those of the dotted ones between days"""
	H = im.shape[0]
	r, g, b = im[..., 0], im[..., 1], im[..., 2]
	blue = (b > 180) & (b - r > 60) & (b - g > 30)
	y0, y1 = int(H*.05), int(H*.9)
	cover = blue[y0:y1].sum(0)
	week, days = [], []
	for x in np.flatnonzero(cover > (y1-y0)*.25):
		s, e = runs(blue[y0:y1, x])
		(week if np.median(e - s) >= 6 else days).append(int(x))
	def merge(xs):	# a line drawn 2 pixels wide is one line
		out = []
		for x in xs:
			if out and x - out[-1][-1] <= 2:
				out[-1].append(x)
			else:
				out.append([x])
		return [round(sum(l)/len(l)) for l in out]
	week, days = merge(week), merge(days)
	start = week[0] if week else None
	if start is not None:
		days = [d for d in days if d > start]
	return start, days

def candles(im, left, right):
	"""the columns with candles between left and right, and the top and
	bottom of each"""
	H, W, _ = im.shape
	mx, mn = im.max(2), im.min(2)
	hsv = np.asarray(Image.fromarray(im.astype(np.uint8)).convert("HSV")).astype(int)
	hue = hsv[..., 0] * 360 // 255
	sat = (mx - mn) > 90
	m = (mx < 80) | (sat & ((hue < 25) | (hue > 330) | ((hue > 90) & (hue < 165))))
	m[:int(H*.04)] = False
	m[int(H*.95):] = False
	m[:, :max(6, left)] = False
	m[:, min(W - 4, right):] = False
	for y in range(H):	# horizontal lines: runs of 12 pixels or more
		s, e = runs(m[y])
		for a, z in zip(s, e):
			if z - a >= 12:
				m[y, a:z] = False
	hi = np.full(W, -1)
	lo = np.full(W, -1)
	for x in np.flatnonzero(m.any(0)):	# a candle: vertical runs of 9 or more
		s, e = runs(m[:, x])
		ok = [(a, z) for a, z in zip(s, e) if 9 <= z - a < H*.5]
		if ok:
			hi[x], lo[x] = ok[0][0], ok[-1][1] - 1
	xs = np.flatnonzero(hi >= 0)
	# a candle has neighbours that reach about its high and about its low
	tol = H * .03
	keep = []
	for x in xs:
		nb = xs[(abs(xs - x) <= 12) & (xs != x)]
		if len(nb) >= 3 and (abs(hi[nb] - hi[x]) <= tol).any() and (abs(lo[nb] - lo[x]) <= tol).any():
			keep.append(x)
	xs = np.array(keep, dtype=int)
	return xs, hi, lo

def zigzag(xs, hi, lo, swing=SWING):
	"""the points (x, y) of the swings of at least swing times the range,
	from the first candle to the last"""
	top, bot = hi[xs].min(), lo[xs].max()
	t = swing * (bot - top)
	pts = []
	dirn = 0	# 1 going up, -1 going down
	hx, hy = xs[0], hi[xs[0]]
	lx, ly = xs[0], lo[xs[0]]
	for x in xs:
		if hi[x] < hy:
			hx, hy = x, hi[x]
		if lo[x] > ly:
			lx, ly = x, lo[x]
		if dirn != -1 and lo[x] - hy > t:	# fell t from the high: it was a swing
			if dirn == 0 and lx < hx:
				pts.append((lx, ly))
			pts.append((hx, hy))
			dirn = -1
			lx, ly = x, lo[x]
		elif dirn != 1 and ly - hi[x] > t:	# rose t from the low
			if dirn == 0 and hx < lx:
				pts.append((hx, hy))
			pts.append((lx, ly))
			dirn = 1
			hx, hy = x, hi[x]
	if dirn == 1:
		pts.append((hx, hy))
	elif dirn == -1:
		pts.append((lx, ly))
	first, last = xs[0], xs[-1]
	if not pts or pts[0][0] != first:	# from the open: the side away from the first swing
		up = pts and pts[0][1] < (hi[first] + lo[first]) / 2
		pts.insert(0, (first, lo[first] if up else hi[first]))
	if pts[-1][0] != last:
		pts.append((last, (hi[last] + lo[last]) / 2))
	return [(int(x), float(y)) for x, y in pts], top, bot

def detect(path, swing=SWING):
	"""the profile of the week in the capture at path, in the image: a
	dict with "px", its points [x, y] in pixels, and what places them in the
	week ("start", "days", "x0", "x1"); None when there are no candles"""
	im = np.asarray(Image.open(path).convert("RGB")).astype(int)
	H, W, _ = im.shape
	start, days = bluelines(im)
	left = start - 3 if start is not None else 0
	right = W
	if len(days) >= 2:	# Friday ends before its midnight
		right = int(days[-1] + (days[-1] - days[-2]) * .72)
	xs, hi, lo = candles(im, left, right)
	if len(xs) < 20:
		return None
	pts, top, bot = zigzag(xs, hi, lo, swing)
	geom = {"start": start, "days": days, "x0": int(xs[0]), "x1": int(xs[-1])}
	pts = clean([(day(geom, x), y, x) for x, y in pts])	# by time, keeping the pixels
	geom["px"] = [[x, round(y, 1)] for _, y, x in pts]
	return geom

def day(geom, x):
	"""image x in days from Monday 00:00, by the week's lines"""
	start, days = geom["start"], geom["days"]
	if len(days) == 1 and start is not None:	# Sunday evening is 6 of a day's 23 hours of candles
		return (x - days[0]) / ((days[0] - start) * 23 / 6)
	if len(days) < 2:
		return 5 * (x - geom["x0"]) / max(1, geom["x1"] - geom["x0"])
	i = max(0, min(len(days) - 2, int(np.searchsorted(days, x, "right")) - 1))
	return i + (x - days[i]) / (days[i+1] - days[i])

def points(geom):
	"""the profile [(t, v)] of a profile in the image: v from its lowest
	point (the low of the week, 0) to its highest (1)"""
	if not geom or not geom.get("px"):
		return None
	ys = [y for _, y in geom["px"]]
	top, bot = min(ys), max(ys)
	return [(round(float(day(geom, x)), 3), round(float((bot - y) / max(1, bot - top)), 3)) for x, y in geom["px"]]

def profile(path, swing=SWING):
	"""the profile of the week in the capture at path: [(t, v)], or None"""
	return points(detect(path, swing))

def clean(pts, dt=0.05):
	"""without the swings of less than dt days (an hour): labels and lines
	taken for candles, or a candle at the open next to the first swing"""
	pts = list(pts)
	i = 1
	while i < len(pts) - 2:	# a pair of turns that close: both go, the rest still alternates
		if pts[i+1][0] - pts[i][0] < dt:
			del pts[i:i+2]
			i = max(1, i - 1)
		else:
			i += 1
	if len(pts) > 2 and pts[1][0] - pts[0][0] < dt:
		del pts[0]
	if len(pts) > 2 and pts[-1][0] - pts[-2][0] < dt:
		del pts[-1]
	return pts

CACHE = ".pyjou-weekprof.json"

class Profiles:
	"""the profiles of the week captures of a journal, kept in a file in
	it so each capture is looked at once (and again when it changes)"""
	def __init__(self, dir):
		self.path = os.path.join(dir, CACHE)
		self.dir = dir
		self.dirty = False
		try:
			with open(self.path) as f:
				self.cache = json.load(f)
		except (OSError, ValueError):
			self.cache = {}

	def entry(self, name):
		"""the cache entry of capture name, made now if it is not there or
		its image changed (but not when it was adjusted by hand)"""
		p = os.path.join(self.dir, name)
		try:
			mt = os.path.getmtime(p)
		except OSError:
			return None
		c = self.cache.get(name)
		if c and "geom" in c and (c.get("mtime") == mt or c.get("adjusted")):
			return c
		try:
			geom = detect(p)
		except Exception:
			geom = None
		c = self.cache[name] = {"mtime": mt, "geom": geom, "points": points(geom)}
		self.dirty = True
		return c

	def get(self, name):
		"""the profile of capture name, found now if it is not known"""
		c = self.entry(name)
		return c["points"] if c else None

	def geom(self, name):
		"""the profile of capture name in its image (see detect)"""
		c = self.entry(name)
		return c["geom"] if c else None

	def adjust(self, name, px):
		"""the profile of capture name is now px, points [x, y] of its image"""
		c = self.entry(name)
		if c is None:
			return
		g = dict(c["geom"] or {"start": None, "days": [], "x0": 0, "x1": 1})
		px = sorted([[float(x), float(y)] for x, y in px])
		g["px"] = px
		if not c["geom"]:	# nothing found to place it: the week is its width
			g["x0"], g["x1"] = px[0][0], px[-1][0]
		c.update(geom=g, points=points(g), adjusted=True)
		self.dirty = True
		self.save()

	def save(self):
		"""keep the profiles found since the last time"""
		if not self.dirty:
			return
		self.dirty = False
		try:
			with open(self.path, "w") as f:
				json.dump(self.cache, f)
		except OSError:
			pass

FULL = 4.55	# a profile that ends before this (Friday afternoon) is a week in progress

def partial(pts):
	"""whether profile pts is of a week still going on"""
	return bool(pts) and pts[-1][0] < FULL

def at(pts, t):
	"""the level of profile pts at time t, along its segments"""
	if t <= pts[0][0]:
		return pts[0][1]
	for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
		if t <= t1:
			return v0 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
	return pts[-1][1]

def similarity(part, full):
	"""how much full looks like part over the time part covers, from 0 to 1;
	each is scaled to its own range in that time, so a week that went up
	and down the same way matches whatever its size. None when they share
	too little time"""
	t0, t1 = max(part[0][0], full[0][0]), part[-1][0]
	if t1 - t0 < 0.25 or full[-1][0] < t1 - 0.05:
		return None
	ts = set(np.linspace(t0, t1, 80).tolist())
	ts |= {t for t, _ in part + full if t0 <= t <= t1}	# the turns themselves
	ts = sorted(ts)
	def scaled(pts):
		v = np.array([at(pts, t) for t in ts])
		lo, hi = v.min(), v.max()
		return (v - lo) / (hi - lo) if hi > lo else v * 0 + .5
	d = scaled(part) - scaled(full)
	return float(1 - np.sqrt((d * d).mean()))

def matches(part, profiles):
	"""[(similarity, name)] of the profiles {name: pts} like part, best first"""
	out = []
	for name, pts in profiles.items():
		s = similarity(part, pts) if pts else None
		if s is not None:
			out.append((s, name))
	return sorted(out, reverse=True)
