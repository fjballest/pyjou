#
# queries on the candles of a journal: a small language to ask about
# periods (years, months, weeks, days, sessions, hours, windows of time),
# their conditions (trend, consolidation, reversal, retrace: what price did
# in them), their highs
# and lows and when they were made, and what price did after (took the
# Asia low, then its high). A query gives a table: counts, shares,
# distributions or averages, by a key if asked. No widgets here; the
# window is in querywin.py.
#
#	dist week.high.day where mon is uptrend
#	dist london.cond where asia is consolidation
#	dist day.cond by month in 2025
#	share day is consolidation by weekday
#	share day takes asia.low then asia.high tf 5
#	share day soups asia.high by weekday tf 5
#	dist (when day takes asia.low).session
#
# Times are New York's, as in m15.py: a trading day from 18:00 the day
# before to 17:00, a week from Sunday 18:00 to Friday 17:00.
#
import os
import re
import sys
from datetime import date, timedelta

import numpy as np

import m15

DAY = 86400
H = 3600
EPOCH = m15.EPOCH
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
# windows of the day, in hours from its midnight (before it, negative)
SESSIONS = {"asia": (-4.0, 0.0), "london": (2.0, 5.0), "nyam": (7.0, 11.5), "nypm": (13.5, 16.0)}
# what is counted when a query names only these
UNITS = ["year", "month", "week", "day"]
# the periods before used for the average range: consolidation is a range
# smaller than a part of it
HISTORY = {"year": 3, "month": 6, "week": 8, "day": 20, "window": 20}
SESSIONORDER = ["asia", "london", "nyam", "nypm"]
CONDS = ["uptrend", "downtrend", "upreversal", "downreversal", "upretrace", "downretrace", "consolidation", "mixed"]
GROUPS = {"trend": ("uptrend", "downtrend"), "reversal": ("upreversal", "downreversal"),
	"retrace": ("upretrace", "downretrace"), "up": ("up",), "down": ("down",),
	"inside": ("q1", "q2", "q3", "q4"), "upper": ("q3", "q4"), "lower": ("q1", "q2")}
# the thresholds of the conditions, which conditions.txt in the journal can change
DEFAULTS = {
	"flat": 0.25,		# consolidation: a close this near the open, as a part of the range
	"swing": 0.5,		# a swing inside the period goes at least this part of the range...
	"swings": 4,		# ...and with this many of them the period went back and forth: consolidation
	"reversal": 0.4,	# a reversal first goes this part of the range away from the open, one way
	"retrace": 0.4,		# a retrace gives back this part of the range from its extreme
	"trend": 0.6,		# a trend closes this part of the range away from the open
	"near": 0.02,		# a reject: coming this near a level, as a part of the average range of a day...
	"bounce": 0.1,		# ...and then going this far away from it, without a close past it
}
CONDFILE = "conditions.txt"
STATS = ["count", "share", "dist", "avg", "median", "min", "max", "sum", "list"]

class QueryError(Exception):
	"""a query that can't be read or run: pos is where in its text"""
	def __init__(self, msg, pos=None):
		super().__init__(msg)
		self.pos = pos

def thresholds(dir):
	"""DEFAULTS, with those set in the journal's conditions.txt (name = value)"""
	th = dict(DEFAULTS)
	try:
		with open(os.path.join(dir, CONDFILE), encoding="utf-8") as f:
			text = f.read()
	except OSError:
		return th
	if not re.search(r"^\s*flat\s*=", text, re.M):
		return th	# one of the first queries, whose conditions were others
	for line in text.splitlines():
		line = line.split("#")[0].strip()
		if "=" in line:
			k, v = (x.strip() for x in line.split("=", 1))
			if k in th:
				try:
					th[k] = float(v)
				except ValueError:
					pass
	return th

def writedefaults(dir):
	"""write conditions.txt with the defaults, explained, when there is none"""
	p = os.path.join(dir, CONDFILE)
	try:
		with open(p, encoding="utf-8") as f:
			if re.search(r"^\s*flat\s*=", f.read(), re.M):
				return p
	except OSError:
		pass	# none, or one of the first queries, with other conditions: written again
	with open(p, "w", encoding="utf-8") as f:
		f.write("# the thresholds of the conditions of queries (View ▸ Queries), as parts of\n"
			"# the range of the period (its high minus its low), from what price did in it:\n"
			"# flat: a close this near the open is a consolidation\n"
			"# swing, swings: as many swings of this size as swings, back and forth in the\n"
			"#	range, is a consolidation too, wherever it closes\n"
			"# reversal: first this far away from the open one way, then a close past the open\n"
			"#	the other way (by more than flat)\n"
			"# retrace: a move one way that gives back this much from its extreme, closing\n"
			"#	still on its side of the open\n"
			"# trend: a close this far from the open\n"
			"# near, bounce: a level is rejected when price comes this near it (or wicks\n"
			"#	past it), closes back on its side and goes bounce away before any close\n"
			"#	past it; both as parts of the average range of the days before\n")
		for k, v in DEFAULTS.items():
			f.write(f"{k} = {v:g}\n")
	return p

def zigzag(h, l, t):
	"""the turns of the zigzag of candles h, l whose moves are at least t
	(as in patterns.py): [(index, +1 a high / -1 a low)]"""
	out = []
	if not len(h):
		return out
	d = 0
	hi, hix, lo, lox = h[0], 0, l[0], 0
	for i in range(1, len(h)):
		if d >= 0 and h[i] > hi:
			hi, hix = h[i], i
		if d <= 0 and l[i] < lo:
			lo, lox = l[i], i
		if d >= 0 and hi - l[i] >= t and (d == 1 or hix < i):
			out.append((hix, 1))
			d, lo, lox = -1, l[i], i
		elif d <= 0 and h[i] - lo >= t and (d == -1 or lox < i):
			out.append((lox, -1))
			d, hi, hix = 1, h[i], i
	return out

# --- the candles ---

class Candles:
	"""the candles of time frame tf of a journal: arrays t (UTC), wall (New
	York's clock), o, h, l, c, and dayno, each candle's trading day"""
	def __init__(self, dir, tf=15):
		self.tf = tf
		base = basetf(dir, tf)
		d = m15.Data(dir, base)
		rows = d.rows()
		if tf != base and len(rows):
			rows = m15.resample(rows, tf)
		self.symbol = d.symbol
		self.set(rows)

	def set(self, rows):
		a = np.asarray(rows, dtype=float).reshape(-1, 5)
		self.t = a[:, 0].astype(np.int64)
		self.o, self.h, self.l, self.c = a[:, 1], a[:, 2], a[:, 3], a[:, 4]
		self.wall = self.t + m15.nyoffsets(self.t) if len(self.t) else self.t
		self.dayno = (self.wall - m15.DAYSTART * H) // DAY
		ns = np.unique(self.dayno)
		self.days = [int(n) for n in ns if (int(n) + 3) % 7 < 5]	# Monday to Friday
		self.dayindex = {n: k for k, n in enumerate(self.days)}

	@classmethod
	def fromrows(cls, rows, tf=15):
		c = cls.__new__(cls)
		c.tf, c.symbol = tf, None
		c.set(rows)
		return c

def basetf(dir, tf):
	"""the time frame kept in the journal that makes candles of tf"""
	have = sorted(set(m15.lowtfs(dir)) | {15})
	ok = [x for x in have if x <= tf and tf % x == 0]
	if not ok:
		raise QueryError(f"no data to make {m15.tfname(tf)} candles: there is {', '.join(m15.tfname(x) for x in have)}")
	return max(ok)

def daydate(n):
	return EPOCH + timedelta(days=int(n))

def dayn(d):
	return (d - EPOCH).days

# --- periods and values ---

class Period:
	"""a span of time: kind (year, month, week, day or window), key (the
	year, (year, month), Monday's or the day's number, or (day, name, a, b)
	for a window of hours a to b of a day), its wall times [s, e)"""
	def __init__(self, model, kind, key, s, e, name):
		self.m, self.kind, self.key, self.s, self.e, self.name = model, kind, key, s, e, name
		c = model.c
		self.i, self.j = (int(x) for x in np.searchsorted(c.wall, [s, e]))

	def __repr__(self):
		return self.label()

	def __eq__(self, o):
		return isinstance(o, Period) and (self.kind, self.key) == (o.kind, o.key)

	def __hash__(self):
		return hash((self.kind, self.key))

	def empty(self):
		return self.j <= self.i

	def firstday(self):
		return daydate((self.s - m15.DAYSTART * H) // DAY)

	def label(self):
		d = self.firstday()
		if self.kind == "year":
			return str(self.key)
		if self.kind == "month":
			return f"{self.key[0]}-{self.key[1]:02d}"
		if self.kind == "week":
			return f"week {daydate(self.key):%y-%m-%d}"
		if self.kind == "day":
			return f"{daydate(self.key):%a %y-%m-%d}"
		return f"{self.name} {daydate(self.key[0]):%a %y-%m-%d}"

	def date(self):
		"""the trading day it is, or starts with"""
		return daydate(self.key) if self.kind in ("day", "week") else (
			daydate(self.key[0]) if self.kind in ("window", "session") else self.firstday())

	# what it is made of
	def open(self):
		return None if self.empty() else float(self.m.c.o[self.i])

	def close(self):
		return None if self.empty() else float(self.m.c.c[self.j - 1])

	def high(self):
		if self.empty():
			return None
		k = self.i + int(self.m.c.h[self.i:self.j].argmax())
		return Extreme(float(self.m.c.h[k]), k, self.m)

	def low(self):
		if self.empty():
			return None
		k = self.i + int(self.m.c.l[self.i:self.j].argmin())
		return Extreme(float(self.m.c.l[k]), k, self.m)

	def range(self):
		if self.empty():
			return None
		return float(self.m.c.h[self.i:self.j].max() - self.m.c.l[self.i:self.j].min())

	def quarter(self, f):
		if self.empty():
			return None
		lo, hi = float(self.m.c.l[self.i:self.j].min()), float(self.m.c.h[self.i:self.j].max())
		return lo + f * (hi - lo)

	def mid(self):
		if self.empty():
			return None
		return float(self.m.c.h[self.i:self.j].max() + self.m.c.l[self.i:self.j].min()) / 2

	def dir(self):
		if self.empty():
			return None
		return "up" if self.close() >= self.open() else "down"

	def cond(self):
		return self.m.cond(self)

	def swings(self):
		return self.m.swings(self)

	def rel(self):
		"""its range as a part of the average range of the periods of its kind before"""
		a = self.m.avgrange(self)
		r = self.m.rangeof(self)
		return r / a if a and r is not None else None

	def move(self):
		"""close minus open"""
		return None if self.empty() else self.close() - self.open()

	def time(self):
		return Time(self.i, self.m) if not self.empty() else None

ATTRS = {"open": Period.open, "close": Period.close, "high": Period.high, "low": Period.low,
	"range": Period.range, "mid": Period.mid, "dir": Period.dir, "cond": Period.cond, "move": Period.move, "ce": Period.mid,
	"dq": lambda p: p.quarter(0.25), "uq": lambda p: p.quarter(0.75),
	"swings": Period.swings, "rel": Period.rel, "start": Period.time}

class Hour(int):
	"""an hour of the day, in the order of the trading day (18 first)"""
	def order(self):
		return (self - 18) % 24

class Clock(str):
	"""a time of the day, HH:MM, in the order of the trading day"""
	def order(self):
		h, m = self.split(":")
		return ((int(h) - 18) % 24) * 60 + int(m)

class Time:
	"""when something happened: the candle k"""
	def __init__(self, k, model):
		self.k, self.m = k, model

	def wall(self):
		return int(self.m.c.wall[self.k])

	def dayno(self):
		return int(self.m.c.dayno[self.k])

	def hours(self):
		"""hours from the midnight of its trading day: -6 is 18:00 the day before"""
		return (self.wall() - self.dayno() * DAY) / H

	def attr(self, name):
		w = self.wall()
		if name == "hour":
			return Hour((w % DAY) // H)
		if name == "time":
			return Clock(f"{(w % DAY) // H:02d}:{(w % H) // 60:02d}")
		if name == "day":
			return WEEKDAYS[(self.dayno() + 3) % 7] if (self.dayno() + 3) % 7 < 5 else "sun"
		if name == "session":
			h = self.hours()
			return next((s for s, (a, b) in SESSIONS.items() if a <= h < b), "other")
		if name == "date":
			return f"{daydate(self.dayno()):%y-%m-%d}"
		if name == "minute":
			return (w % H) // 60
		raise QueryError(f"a time has no {name}: it has hour, time, day, session, date")

	def __repr__(self):
		return f"{self.attr('date')} {self.attr('time')}"

class Extreme(Time):
	"""a high or a low: its price, and when it was made"""
	def __init__(self, price, k, model):
		super().__init__(k, model)
		self.price = price

	def __repr__(self):
		return m15.price(self.price)

def num(v):
	"""v as a number, or None"""
	if isinstance(v, Extreme):
		return v.price
	if isinstance(v, bool):
		return float(v)
	if isinstance(v, (int, float, np.integer, np.floating)):
		return float(v)
	return None

def show(v):
	"""v as a table writes it"""
	if v is None:
		return "none"
	if isinstance(v, Extreme):
		return m15.price(v.price)
	if isinstance(v, Zone):
		return repr(v)
	if isinstance(v, float):
		return m15.price(round(v, 2))
	return str(v)

class Zone:
	"""a range of prices: an opening gap (rthog, ndog, nwog), an FVG, or a
	quadrant of one; s and e, the wall times it is from (e, when it was
	made: what takes it is looked for after)"""
	def __init__(self, kind, low, high, s, e, model, **more):
		self.kind, self.low, self.high, self.s, self.e, self.m = kind, float(low), float(high), s, e, model
		self.more = more

	def __repr__(self):
		return f"{m15.price(self.low)}–{m15.price(self.high)}"

	def at(self, f):
		return self.low + f * (self.high - self.low)

	def quadrant(self, k):
		a, b = self.at((k - 1) / 4), self.at(k / 4)
		return Zone(f"{self.kind} q{k}", a, b, self.s, self.e, self.m)

	def where(self, x):
		"""where price x is: above, q4 (the top quarter)…q1, or below"""
		if x is None:
			return None
		if x > self.high:
			return "above"
		if x < self.low:
			return "below"
		if self.high <= self.low:
			return "q2"
		return f"q{min(4, int((x - self.low) / (self.high - self.low) * 4) + 1)}"

	def attr(self, a):
		if a == "high":
			return self.high
		if a == "low":
			return self.low
		if a in ("ce", "mid"):
			return self.at(0.5)
		if a == "dq":
			return self.at(0.25)
		if a == "uq":
			return self.at(0.75)
		if a in ("size", "range"):
			return self.high - self.low
		if a in ("q1", "q2", "q3", "q4"):
			return self.quadrant(int(a[1]))
		if a in self.more:
			return self.more[a]
		if a == "start":
			k = int(np.searchsorted(self.m.c.wall, self.e)) - 1
			return Time(max(0, k), self.m)
		raise QueryError(f"a {self.kind} has no {a}: it has high, low, ce, dq, uq, q1…q4, size, start"
			+ "".join(", " + k for k in self.more))

GAPS = ("rthog", "ndog", "nwog")
RTHCLOSE, RTHOPEN = 16.25, 9.5	# the settlement and the open of the regular session, hours of the day
FVGRE = re.compile(r"(last)?(bull|bear)?fvg(s)?(?:_?(m?\d+|h\d+))?$")

def fvgname(a):
	"""(last, kind, count, tf) of an fvg attribute, or None: fvg, bullfvg,
	lastbearfvg, fvg5, fvgh1, fvgs15 (how many)"""
	m = FVGRE.match(a)
	if not m:
		return None
	tf = m.group(4)
	if tf:
		tf = int(tf[1:]) * 60 if tf[0] == "h" else int(tf.lstrip("m"))
	return bool(m.group(1)), m.group(2), bool(m.group(3)), tf

# --- the model: periods of the candles and their conditions ---

class Model:
	def __init__(self, candles, th=None, loader=None):
		self.c = candles
		self.th = th or dict(DEFAULTS)
		self.conds = {}
		self.lists = {}
		self.ranges = {}
		self.gaps = {}
		self.fvgs = {}
		self.loader = loader	# the candles of another time frame: loader(tf)

	def candles(self, tf):
		if tf is None or tf == self.c.tf:
			return self.c
		if self.loader is None:
			raise QueryError(f"no {m15.tfname(tf)} candles here")
		return self.loader(tf)

	def fine(self):
		"""candles of 15 minutes or less, where the opening gaps are found"""
		return self.c if self.c.tf <= 15 else self.candles(15)

	# opening gaps, as ICTlevels finds them
	def gap(self, kind, n):
		"""the opening gap kind of trading day n (of the week of n, for
		nwog), or None: rthog from the close at 16:15 of the day before to
		the open at 09:30; ndog from the close before 17:00 the day before to
		the open at 18:00 (none on Mondays: that is the nwog); nwog from
		Friday's close to the open of the week"""
		if kind == "nwog":
			n = n - (n + 3) % 7
		key = (kind, n)
		if key not in self.gaps:
			self.gaps[key] = self.findgap(kind, n)
		return self.gaps[key]

	def findgap(self, kind, n):
		c = self.fine()
		i = c.dayindex.get(n)
		if kind == "nwog" and i is None:	# the week's first day with candles
			i = next((c.dayindex[x] for x in range(n, n + 5) if x in c.dayindex), None)
			if i is None:
				return None
			n = c.days[i]
		if i is None or i == 0:
			return None
		prev = c.days[i - 1]
		monday = (n + 3) % 7 == 0 or n - prev > 1
		if kind == "ndog" and monday:
			return None
		if kind == "nwog" and not monday:
			return None
		if kind == "rthog":
			end, start = prev * DAY + RTHCLOSE * H, n * DAY + RTHOPEN * H
		else:
			end, start = prev * DAY + m15.DAYEND * H, n * DAY + m15.DAYSTART * H
		k = int(np.searchsorted(c.wall, end)) - 1	# the last candle before the close
		o = int(np.searchsorted(c.wall, start))	# the first after the open
		if k < 0 or o >= len(c.wall) or c.dayno[k] != prev or c.dayno[o] != n:
			return None
		settle, op = float(c.c[k]), float(c.o[o])
		e = int(c.wall[o])
		return Zone(kind, min(settle, op), max(settle, op), int(c.wall[k]), e, self,
			settle=settle, open=op, dir="up" if op >= settle else "down")

	# fair value gaps
	def fvglist(self, p, tf, kind=None):
		"""the FVGs made in period p on candles of tf: [Zone], in order; a
		bullish one is a third candle whose low is above the high of the
		first, a bearish one the other way"""
		c = self.candles(tf)
		key = (p.kind, p.key, c.tf)
		if key not in self.fvgs:
			i, j = (int(x) for x in np.searchsorted(c.wall, [p.s, p.e]))
			out = []
			if j - i >= 3:
				h, l = c.h[i:j], c.l[i:j]
				up = np.flatnonzero(l[2:] > h[:-2])
				dn = np.flatnonzero(h[2:] < l[:-2])
				for k, bull in sorted([(k, True) for k in up] + [(k, False) for k in dn]):
					k3 = i + k + 2
					e = int(c.wall[k3]) + c.tf * 60
					if bull:
						out.append(Zone("fvg", h[k], l[k + 2], int(c.wall[i + k]), e, self, dir="bull"))
					else:
						out.append(Zone("fvg", h[k + 2], l[k], int(c.wall[i + k]), e, self, dir="bear"))
			self.fvgs[key] = out
		lst = self.fvgs[key]
		return [z for z in lst if kind is None or z.more["dir"] == kind]

	# the periods
	def day(self, n):
		return Period(self, "day", n, n * DAY + m15.DAYSTART * H, n * DAY + m15.DAYEND * H, "day")

	def week(self, monday):
		return Period(self, "week", monday, monday * DAY + m15.DAYSTART * H, (monday + 4) * DAY + m15.DAYEND * H, "week")

	def month(self, y, mo):
		first = dayn(date(y, mo, 1))
		last = dayn(date(y + mo // 12, mo % 12 + 1, 1)) - 1
		return Period(self, "month", (y, mo), first * DAY + m15.DAYSTART * H, last * DAY + m15.DAYEND * H, "month")

	def year(self, y):
		first, last = dayn(date(y, 1, 1)), dayn(date(y, 12, 31))
		return Period(self, "year", y, first * DAY + m15.DAYSTART * H, last * DAY + m15.DAYEND * H, "year")

	def window(self, n, name, a, b, kind="window"):
		return Period(self, kind, (n, name, a, b), int(n * DAY + a * H), int(n * DAY + b * H), name)

	def session(self, n, name):
		"""the session name of day n, as one of the sessions in a row (prev
		session is the one before it, whatever its name)"""
		a, b = SESSIONS[name]
		return self.window(n, name, a, b, "session")

	def periods(self, kind):
		"""every period of kind (year, month, week, day, session) with candles, in order"""
		if kind not in self.lists:
			days = self.c.days
			if kind == "day":
				out = [self.day(n) for n in days]
			elif kind == "week":
				out = [self.week(n) for n in sorted({n - (n + 3) % 7 for n in days})]
			elif kind == "month":
				out = [self.month(*k) for k in sorted({(daydate(n).year, daydate(n).month) for n in days})]
			elif kind == "year":
				out = [self.year(y) for y in sorted({daydate(n).year for n in days})]
			elif kind == "session":
				out = [self.session(n, s) for n in days for s in SESSIONORDER]
			else:
				raise QueryError(f"no periods {kind}")
			self.lists[kind] = out
		return self.lists[kind]

	def shift(self, p, k):
		"""the period k after p (before, when k < 0), or None"""
		if p.kind == "window":
			n, name, a, b = p.key
			i = self.c.dayindex.get(n)
			if i is None or not 0 <= i + k < len(self.c.days):
				return None
			return self.window(self.c.days[i + k], name, a, b)
		lst = self.periods(p.kind)
		idx = self.index(p)
		if idx is None or not 0 <= idx + k < len(lst):
			return None
		return lst[idx + k]

	def index(self, p):
		key = ("index", p.kind)
		if key not in self.lists:
			self.lists[key] = {q.key: i for i, q in enumerate(self.periods(p.kind))}
		return self.lists[key].get(p.key)

	def containing(self, p, kind):
		"""the period of kind holding p"""
		d = p.date()
		if kind == "day":
			return self.day(dayn(d))
		if kind == "week":
			n = dayn(d)
			return self.week(n - (n + 3) % 7)
		if kind == "month":
			return self.month(d.year, d.month)
		if kind == "year":
			return self.year(d.year)
		raise QueryError(f"no {kind} holds a {p.kind}")

	# conditions
	def avgrange(self, p):
		"""the average range of the periods of p's kind before it"""
		n = HISTORY.get(p.kind, 20)
		rs = []
		q = self.window(*p.key) if p.kind == "session" else p	# the same session, the days before
		for _ in range(n * 2):
			q = self.shift(q, -1)
			if q is None:
				break
			r = self.rangeof(q)
			if r:
				rs.append(r)
			if len(rs) == n:
				break
		return sum(rs) / len(rs) if len(rs) >= max(2, n // 2) else None

	def rangeof(self, p):
		k = (p.kind, p.key)
		if k not in self.ranges:
			self.ranges[k] = p.range()
		return self.ranges[k]

	def cond(self, p):
		"""the condition of period p, from what price did in it (see
		findcond), or None without candles"""
		k = (p.kind, p.key)
		if k not in self.conds:
			self.conds[k] = self.findcond(p)
		return self.conds[k]

	def swings(self, p):
		"""how many swings of at least th["swing"] of the range price made in p"""
		r = self.rangeof(p)
		if not r:
			return 0 if r is not None else None
		c = self.c
		return len(zigzag(c.h[p.i:p.j], c.l[p.i:p.j], self.th["swing"] * r))

	def findcond(self, p):
		"""in this order, with r the range and the thresholds th:
		consolidation: closes within flat x r of the open, or made swings
			swings of swing x r, back and forth;
		upreversal: went down first, at least reversal x r below the open,
			then closed above it (by more than flat x r); downreversal the
			other way;
		upretrace: went up, then gave back at least retrace x r from the
			high, closing above the open; downretrace the other way;
		uptrend: closed at least trend x r above the open; downtrend below;
		mixed: none of those"""
		th = self.th
		r = self.rangeof(p)
		if r is None:
			return None
		if r <= 0:
			return "consolidation"
		o, c = p.open(), p.close()
		hi, lo = p.high(), p.low()
		e = (c - o) / r
		if abs(e) <= th["flat"] or self.swings(p) >= th["swings"]:
			return "consolidation"
		rv = th["reversal"]
		if e > 0 and lo.k < hi.k and (o - lo.price) >= rv * r:
			return "upreversal"
		if e < 0 and hi.k < lo.k and (hi.price - o) >= rv * r:
			return "downreversal"
		if e > 0 and (hi.price - c) >= th["retrace"] * r:
			return "upretrace"
		if e < 0 and (c - lo.price) >= th["retrace"] * r:
			return "downretrace"
		if e >= th["trend"]:
			return "uptrend"
		if e <= -th["trend"]:
			return "downtrend"
		return "mixed"

	def soup(self, i, j, side, level):
		"""a turtle soup of level in [i, j): price takes it (above, side 1,
		or below, -1), a candle then closes back on the other side, and
		price does not go past the extreme of that take again before j.
		The candle that closed back, or None"""
		k = self.first(i, j, side, level)
		if k is None:
			return None
		c = self.c
		back = self.first(k, j, -side, level, close=True)	# the close back, maybe on the candle that took it
		if back is None:
			return None
		if side > 0:
			ext = c.h[k:back + 1].max()
			ok = back + 1 >= j or c.h[back + 1:j].max() <= ext
		else:
			ext = c.l[k:back + 1].min()
			ok = back + 1 >= j or c.l[back + 1:j].min() >= ext
		return back if ok else None

	def reject(self, i, j, level, near, bounce):
		"""price comes to level in [i, j) from the side it is on at i,
		within near of it or wicking past, with no close past it, and then
		goes bounce away from it before any close past it: the candle that
		came to it, or None"""
		if j <= i or level is None:
			return None
		c = self.c
		ref = c.c[i - 1] if i > 0 else c.o[i]
		if ref == level:
			ref = c.o[i]
		side = 1 if ref > level else -1	# above it: a support tested from above
		if side > 0:
			at = np.flatnonzero(c.l[i:j] <= level + near)
			past = np.flatnonzero(c.c[i:j] < level)
			away = c.h[i:j] >= level + bounce
		else:
			at = np.flatnonzero(c.h[i:j] >= level - near)
			past = np.flatnonzero(c.c[i:j] > level)
			away = c.l[i:j] <= level - bounce
		if not len(at):
			return None
		k = int(at[0])
		end = int(past[0]) if len(past) else j - i	# the first close past it ends the reject
		if end <= k:
			return None
		go = np.flatnonzero(away[k + 1:end])
		return i + k if len(go) else None

	def dayrange(self, p):
		"""the average range of the days before p's"""
		if p.kind == "day":
			d = p
		elif p.j > p.i:
			d = self.day(int(self.c.dayno[p.i]))
		else:
			return None
		return self.avgrange(d) or self.rangeof(d)

	def first(self, i, j, side, level, close=False):
		"""the first candle in [i, j) going above (side 1) or below (-1)
		level (closing past it, with close), or trading at it (side 0), or None"""
		if j <= i or level is None:
			return None
		c = self.c
		if side == 0:
			a = (c.l[i:j] <= level) & (c.h[i:j] >= level)
		elif close:
			a = c.c[i:j] > level if side > 0 else c.c[i:j] < level
		else:
			a = c.h[i:j] > level if side > 0 else c.l[i:j] < level
		k = np.flatnonzero(a)
		return i + int(k[0]) if len(k) else None

# --- the language ---

TOKEN = re.compile(r"""
	(?P<ws>\s+)
	|(?P<window>\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2})
	|(?P<date>\d{4}-\d{2}(-\d{2})?)
	|(?P<num>\d+(\.\d+)?)
	|(?P<op>\.\.|>=|<=|!=|==|[<>=().,+\-*/%])
	|(?P<word>[A-Za-z_][A-Za-z0-9_]*)
	""", re.X)

def tokens(text):
	out = []
	pos = 0
	while pos < len(text):
		m = TOKEN.match(text, pos)
		if not m:
			raise QueryError(f"what is “{text[pos]}”?", pos)
		kind = m.lastgroup
		if kind != "ws":
			v = m.group()
			out.append((kind, v.lower() if kind == "word" else v, pos))
		pos = m.end()
	out.append(("end", "", len(text)))
	return out

KEYWORDS = {"by", "where", "in", "tf", "on", "and", "or", "not", "is", "then", "when", "takes", "above",
	"below", "closes", "among", "last", "soups", "touches", "inside", "rejects", "fills"}
VERBS = {"takes", "above", "below", "closes", "soups", "touches", "rejects", "fills"}

# the tree: tuples
#	("num", x)  ("name", word)  ("path", base, [attrs])  base: ("unit", kind) ("rel", k, base) ("window", name, a, b)
#	("bin", op, a, b)  ("cmp", op, a, b)  ("is", a, value, neg)  ("and", a, b) ("or", a, b) ("not", a)
#	("seq", [(scope, verb, target, close)])  ("when", seq, [attrs])

class Parser:
	def __init__(self, text):
		self.text = text
		self.toks = tokens(text)
		self.k = 0

	def peek(self, off=0):
		return self.toks[min(self.k + off, len(self.toks) - 1)]

	def at(self, *values):
		kind, v, _ = self.peek()
		return v in values and kind in ("word", "op")

	def take(self, *values):
		if self.at(*values):
			self.k += 1
			return True
		return False

	def need(self, value, what=None):
		if not self.take(value):
			self.fail(f"expected {what or '“' + value + '”'}")

	def fail(self, msg):
		kind, v, pos = self.peek()
		raise QueryError(f"{msg}, not {('“' + v + '”') if v else 'the end'}", pos)

	def query(self):
		q = {"by": [], "where": None, "in": None, "tf": None, "among": None}
		kind, v, _ = self.peek()
		if v not in STATS:
			self.fail("a query starts with " + ", ".join(STATS))
		self.k += 1
		q["stat"] = v
		if v == "share":
			q["what"] = self.cond()
		elif v in ("count", "list"):
			q["what"] = self.path() if not self.at("where", "by", "in", "tf", "on", "") else None
		else:
			q["what"] = self.expr()
		while self.peek()[0] != "end":
			if self.take("by"):
				q["by"].append(self.key())
				while self.take(","):
					q["by"].append(self.key())
			elif self.take("where"):
				c = self.cond()
				q["where"] = c if q["where"] is None else ("and", q["where"], c)
			elif self.take("among"):
				q["among"] = self.path()
			elif self.take("in"):
				q["in"] = self.span()
			elif self.take("tf", "on"):
				q["tf"] = self.tf()
			else:
				self.fail("expected by, where, in or tf")
		if len(q["by"]) > 2:
			raise QueryError("at most two keys after by")
		return q

	def key(self):
		kind, v, _ = self.peek()
		if v in ("weekday", "month", "monthname", "year", "quarter", "hour", "session") and self.peek(1)[1] not in (".",):
			self.k += 1
			return ("key", v)
		return self.expr()

	def tf(self):
		kind, v, pos = self.peek()
		self.k += 1
		if kind == "num":
			return int(float(v))
		m = re.fullmatch(r"([mh])(\d+)|(\d+)([mh])", v) if kind == "word" else None
		if not m:
			raise QueryError("a time frame is m1, m5, h1 or a number of minutes", pos)
		unit, n = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
		return int(n) * (60 if unit == "h" else 1)

	def span(self):
		"""in 2025, in 2025-03, in 2024-03..2025-06, in last 6 months"""
		kind, v, pos = self.peek()
		if self.take("last"):
			kind, v, pos = self.peek()
			n = 1
			if kind == "num":
				n = int(float(v))
				self.k += 1
			kind, u, pos = self.peek()
			self.k += 1
			u = u.rstrip("s")
			if u not in ("day", "week", "month", "year"):
				raise QueryError("last how many days, weeks, months or years?", pos)
			return ("last", n, u)
		a = self.datelit()
		b = a
		if self.take(".."):
			b = self.datelit()
		return ("span", a[0], b[1])

	def datelit(self):
		kind, v, pos = self.peek()
		self.k += 1
		if kind == "num" and re.fullmatch(r"\d{4}", v):
			y = int(v)
			return date(y, 1, 1), date(y, 12, 31)
		if kind == "date":
			p = [int(x) for x in v.split("-")]
			if len(p) == 3:
				d = date(*p)
				return d, d
			y, mo = p
			return date(y, mo, 1), date(y + mo // 12, mo % 12 + 1, 1) - timedelta(days=1)
		raise QueryError("a date is 2025, 2025-03 or 2025-03-14", pos)

	# conditions
	def cond(self):
		a = self.andc()
		while self.take("or"):
			a = ("or", a, self.andc())
		return a

	def andc(self):
		a = self.notc()
		while self.take("and"):
			a = ("and", a, self.notc())
		return a

	def notc(self):
		if self.take("not"):
			return ("not", self.notc())
		return self.atom()

	def atom(self):
		if self.at("(") and not self.peek(1)[1] == "when":
			save = self.k
			self.k += 1
			try:
				c = self.cond()
				self.need(")")
				if not self.at("is", ">", "<", ">=", "<=", "=", "==", "!=", "+", "-", "*", "/", ".", "inside", *VERBS):
					return c
			except QueryError:
				pass
			self.k = save
		a = self.expr()
		if self.take("is"):
			neg = self.take("not")
			kind, v, pos = self.peek()
			if kind not in ("word", "num"):
				self.fail("expected what it is")
			self.k += 1
			return ("is", a, v, neg)
		for op in (">=", "<=", "!=", "==", "=", ">", "<"):
			if self.take(op):
				return ("cmp", "==" if op == "=" else op, a, self.expr())
		if self.take("inside"):
			return ("inside", a, self.expr())
		if self.at(*VERBS):
			return self.seq(a)
		if self.at("then"):
			return self.seq(None, a)
		return ("true", a)

	def verb(self):
		"""takes, soups, touches, above, below, closes above, closes below: (verb, close)"""
		if self.take("closes"):
			if self.take("above"):
				return "above", True
			if self.take("below"):
				return "below", True
			self.fail("closes above or below")
		for v in ("takes", "soups", "touches", "rejects", "fills", "above", "below"):
			if self.take(v):
				return v, False
		self.fail("expected takes, soups, touches, rejects, fills, above or below")

	def seq(self, scope, target=None):
		"""scope takes x then y then scope2 above z: events, one after the other"""
		steps = []
		if target is not None:	# a bare “x then y”: takes, in the unit
			steps.append((None, "takes", target, False))
		else:
			v, close = self.verb()
			steps.append((scope, v, self.expr(), close))
		while self.take("then"):
			if self.at(*VERBS):
				v, close = self.verb()
				steps.append((steps[-1][0], v, self.expr(), close))
				continue
			x = self.expr()
			if self.at(*VERBS):
				v, close = self.verb()
				steps.append((x, v, self.expr(), close))
			else:
				s = steps[-1]
				steps.append((s[0], s[1], x, s[3]))
		return ("seq", steps)

	# expressions
	def expr(self):
		a = self.term()
		while self.at("+", "-"):
			op = self.peek()[1]
			self.k += 1
			a = ("bin", op, a, self.term())
		return a

	def term(self):
		a = self.factor()
		while self.at("*", "/"):
			op = self.peek()[1]
			self.k += 1
			a = ("bin", op, a, self.factor())
		return a

	def factor(self):
		kind, v, pos = self.peek()
		if kind == "num":
			self.k += 1
			return ("num", float(v))
		if self.take("-"):
			return ("bin", "-", ("num", 0.0), self.factor())
		if self.at("(") and self.peek(1)[1] == "when":
			self.k += 2
			s = self.cond()
			if s[0] != "seq":
				raise QueryError("when takes what happened: (when day takes asia.low)", pos)
			self.need(")")
			return ("when", s, self.attrs())
		if self.take("("):
			e = self.expr()
			self.need(")")
			return e
		return self.path()

	def attrs(self):
		out = []
		while self.take("."):
			kind, v, pos = self.peek()
			if kind != "word":
				self.fail("expected a name after the dot")
			self.k += 1
			out.append(v)
		return out

	def path(self):
		kind, v, pos = self.peek()
		if kind == "window":
			self.k += 1
			a, b = (parsehour(x.strip()) for x in v.split("-"))
			if a > b:
				a -= 24
			if a < -6 or b > 18:
				raise QueryError("a window of the day goes from 18:00 to 17:00", pos)
			base = ("window", v.replace(" ", ""), a, b)
		elif v in ("prev", "next"):
			self.k += 1
			k = 1 if v == "next" else -1
			if self.peek()[0] == "num":
				k *= int(float(self.peek()[1]))
				self.k += 1
			kind, w, pos = self.peek()
			if kind not in ("word", "window") or w in KEYWORDS:
				self.fail(f"expected a period after {v}")
			sub = self.path()	# prev day.high: the day before, then its high
			return ("path", ("rel", k, sub[1]), sub[2])
		elif kind == "word" and v not in KEYWORDS:
			self.k += 1
			base = ("name", v)
		else:
			self.fail("expected a period, like day, week, asia or mon")
		return ("path", base, self.attrs())

def parsehour(s):
	h, m = s.split(":")
	return int(h) + int(m) / 60

def parse(text):
	p = Parser(text)
	return p.query()

# --- running a query ---

def wordsof(node, out=None):
	"""the period names in a tree"""
	out = set() if out is None else out
	if isinstance(node, tuple):
		if node[0] == "name":
			out.add(node[1])
		if node[0] == "window":
			out.add("window")
		for x in (node[1:] if isinstance(node[0], str) else node):	# a step of a then starts with its period
			wordsof(x, out)
	elif isinstance(node, list):
		for x in node:
			wordsof(x, out)
	return out

def unitof(q):
	"""what the query counts: year, month, week or day, from the periods it
	names: the smallest of them, a day for sessions, a week for weekdays"""
	words = wordsof([q["what"], q["where"], q["among"]] + q["by"])
	if q["stat"] in ("count", "list") and q["what"] is not None and q["what"][1][0] == "name" \
			and q["what"][1][1] in UNITS and not q["what"][2]:
		return q["what"][1][1]
	if q["among"] is not None and q["among"][1][0] == "name" and q["among"][1][1] in UNITS:
		return q["among"][1][1]
	if "session" in words:
		return "session"
	if "nwog" in words and not words & ({"day", "rthog", "ndog", "window", "hour"} | set(SESSIONS)):
		return "week" if not words & {"month", "year"} else ("month" if "month" in words else "year")
	if words & (set(SESSIONS) | {"window", "hour", "rthog", "ndog"}):
		# a session named as mon.asia keeps to the week
		if "day" in words or not words & set(WEEKDAYS):
			return "day"
	for u in ("day", "week", "month", "year"):
		if u in words or (u == "week" and words & set(WEEKDAYS)):
			if u == "day" and words & set(WEEKDAYS) and "week" in words:
				return "week"
			return u
	return "day"

class Run:
	"""a query run on a Model; only, (day numbers, Monday day numbers) of
	the days and weeks to count, as a search in the list leaves them"""
	def __init__(self, model, q, only=None):
		self.m = model
		self.q = q
		self.only = only
		self.unit = unitof(q)

	def kept(self, p):
		if self.only is None:
			return True
		days, weeks = self.only
		if p.kind == "week":
			return p.key in weeks
		if p.kind in ("day", "window", "session"):
			return p.date() and dayn(p.date()) in days
		a, b = (p.s - m15.DAYSTART * H) // DAY, (p.e - m15.DAYSTART * H) // DAY
		return any(a <= n <= b for n in days)

	def units(self):
		ps = self.m.periods(self.unit)
		span = self.q["in"]
		if span is None:
			return ps
		if span[0] == "last":
			_, n, u = span
			end = daydate(self.m.c.days[-1]) if self.m.c.days else date.today()
			days = {"day": n, "week": 7 * n, "month": 31 * n, "year": 366 * n}[u]
			if u == "day":	# trading days
				return ps[-n:] if self.unit == "day" else [p for p in ps if p.date() > end - timedelta(days=n * 7 // 5 + 2)]
			start = end - timedelta(days=days)
			return [p for p in ps if p.date() > start]
		_, a, b = span
		return [p for p in ps if a <= p.date() <= b]

	# periods
	def period(self, base, u):
		"""the period base names for the unit u, or None"""
		m = self.m
		if base[0] == "rel":
			p = self.period(base[2], u)
			return m.shift(p, base[1]) if p is not None else None
		if base[0] == "window":
			_, name, a, b = base
			d = self.dayof(u, name)
			return m.window(d, name, a, b) if d is not None else None
		name = base[1]
		if name in GAPS:
			if name == "nwog" and u.kind in ("week", "month", "year"):
				return m.gap(name, (u if u.kind == "week" else m.containing(u, "week")).key)
			return m.gap(name, self.dayof(u, name))
		if name == "session":
			if u.kind == "session":
				return u
			raise QueryError("which session? Name it (asia, london, nyam, nypm), or count sessions")
		if name in UNITS:
			if name == u.kind:
				return u
			if u.kind in ("window", "session") or UNITS.index(name) < UNITS.index(u.kind):
				return m.containing(u, name)
			raise QueryError(f"which {name} of the {u.kind}? Name it, as mon or asia, or count {name}s")
		if name in WEEKDAYS:
			wk = u if u.kind == "week" else m.containing(u, "week")
			return m.day(wk.key + WEEKDAYS.index(name))
		if name in SESSIONS:
			d = self.dayof(u, name)
			a, b = SESSIONS[name]
			return m.window(d, name, a, b) if d is not None else None
		if name in MONTHS:
			y = u.date().year
			return m.month(y, MONTHS.index(name) + 1)
		m_ = re.fullmatch(r"h(\d{1,2})", name)
		if m_:
			h = int(m_.group(1))
			a = h - 24 if h >= 18 else h
			return m.window(self.dayof(u, name), name, a, a + 1)
		raise QueryError(f"what is {name}? A period is year, month, week, day, session, mon…fri, asia, london, nyam, nypm, "
			"h9 (an hour) or 08:30-10:00")

	def dayof(self, u, name):
		if u.kind == "day":
			return u.key
		if u.kind in ("window", "session"):
			return u.key[0]
		if u.kind == "week" and name == "nwog":
			return u.key
		raise QueryError(f"{name} of which day? Count days, or say mon.{name}")

	def node(self, n, u, scope=None):
		"""the value of expression n for unit u"""
		t = n[0]
		if t == "num":
			return n[1]
		if t == "bin":
			a, b = num(self.node(n[2], u)), num(self.node(n[3], u))
			if a is None or b is None:
				return None
			op = n[1]
			if op == "/" and b == 0:
				return None
			return {"+": a + b, "-": a - b, "*": a * b, "/": a / b if b else None}[op]
		if t == "path":
			return self.path(n, u)
		if t == "when":
			tm = self.seq(n[1], u)
			return self.attrs(tm, n[2], u) if tm is not None else None
		raise QueryError("a value was expected")

	def path(self, n, u, periodok=True):
		_, base, attrs = n
		if base[0] == "name" and base[1] not in UNITS + ["session"] + WEEKDAYS + list(SESSIONS) + MONTHS + list(GAPS) \
				and not re.fullmatch(r"h\d{1,2}", base[1]):
			raise QueryError(f"what is {base[1]}? A period is year, month, week, day, session, mon…fri, asia, london, nyam, nypm, "
				"h9 (an hour) or 08:30-10:00")
		v = self.period(base, u)
		rest = list(attrs)
		# a.b.c: periods inside periods, then what they are
		while v is not None and rest and isinstance(v, Period) and rest[0] not in ATTRS and not fvgname(rest[0]):
			v = self.period(("name", rest.pop(0)), v)
		if v is None:
			return None
		return self.attrs(v, rest, u)

	def attrs(self, v, names, u=None):
		for a in names:
			if v is None:
				return None
			if a in GAPS and not isinstance(v, (Period, Zone)) and num(v) is not None:
				g = self.m.gap(a, self.dayof(u, a)) if u is not None else None	# where the price is, in the gap
				v = g.where(num(v)) if g is not None else None
				continue
			if isinstance(v, Zone):
				v = v.attr(a)
				continue
			if isinstance(v, Period) and fvgname(a):
				last, kind, count, tf = fvgname(a)
				lst = self.m.fvglist(v, tf, kind)
				v = len(lst) if count else ((lst[-1] if last else lst[0]) if lst else None)
				continue
			if isinstance(v, Period):
				if a not in ATTRS:
					raise QueryError(f"a period has no {a}: it has {', '.join(ATTRS)}")
				v = ATTRS[a](v)
			elif isinstance(v, Time):
				if a == "price" and isinstance(v, Extreme):
					v = v.price
				else:
					v = v.attr(a)
			else:
				raise QueryError(f"{show(v)} has no {a}")
		return v

	# conditions
	def cond(self, n, u):
		t = n[0]
		if t == "and":
			return self.cond(n[1], u) and self.cond(n[2], u)
		if t == "or":
			return self.cond(n[1], u) or self.cond(n[2], u)
		if t == "not":
			return not self.cond(n[1], u)
		if t == "is":
			_, a, val, neg = n
			v = self.node(a, u)
			if isinstance(v, Period):
				v = v.dir() if val in ("up", "down") else v.cond()
			if v is None:
				return False
			ok = self.matches(v, val)
			return ok != neg
		if t == "cmp":
			_, op, a, b = n
			x, y = self.node(a, u), self.node(b, u)
			if num(x) is not None and num(y) is not None:
				x, y = num(x), num(y)
			elif isinstance(x, Time) and isinstance(y, Time):
				x, y = x.k, y.k
			if x is None or y is None:
				return False
			try:
				return {">": x > y, "<": x < y, ">=": x >= y, "<=": x <= y, "==": x == y, "!=": x != y}[op]
			except TypeError:
				raise QueryError(f"can't compare {show(x)} and {show(y)}")
		if t == "seq":
			return self.seq(n, u) is not None
		if t == "inside":
			x, z = num(self.node(n[1], u)), self.node(n[2], u)
			if isinstance(z, Period):
				r = z.high(), z.low()
				z = None if r[0] is None else Zone(z.name, r[1].price, r[0].price, z.s, z.e, self.m)
			if x is None or z is None:
				return False
			if not isinstance(z, Zone):
				raise QueryError("inside what? a period, a gap, an FVG or a quadrant: inside rthog.q4")
			return z.low <= x <= z.high
		if t == "true":
			v = self.node(n[1], u)
			if isinstance(v, Period):
				return not v.empty()
			return bool(v) and v is not None
		raise QueryError("a condition was expected")

	@staticmethod
	def matches(v, val):
		s = str(v).lower()
		if val in GROUPS:
			return s in GROUPS[val]
		if isinstance(v, (int, float)) and re.fullmatch(r"\d+(\.\d+)?", val):
			return float(v) == float(val)
		return s == val

	def seq(self, n, u):
		"""the time of the last of the events of n, each after the one
		before, or None if one of them did not happen"""
		after = None
		for scope, verb, target, close in n[1]:
			p = self.path(scope, u) if scope is not None else u
			if not isinstance(p, Period):
				raise QueryError("what takes a level is a period: day takes asia.low")
			lv = self.node(target, u)
			if verb == "fills":
				k = self.fill(p, lv, after)
				if k is None:
					return None
				after = k
				continue
			level = num(lv)
			if level is None:
				return None
			side = 0
			if verb in ("takes", "soups"):
				last = target[2][-1] if target[0] == "path" and target[2] else None
				if last not in ("high", "low"):
					raise QueryError(f"{verb} is for a high or a low (day {verb} asia.low); "
						"for other levels say above or below")
				side = 1 if last == "high" else -1
			elif verb in ("touches", "rejects"):
				side = 0
			else:
				side = 1 if verb == "above" else -1
			i = p.i
			src = self.source(target, u)	# what is taken is looked for after the period it comes from
			if src is not None and src.e > p.s:
				i = max(i, int(np.searchsorted(self.m.c.wall, src.e)))
			if after is not None:
				i = max(i, after + 1)
			if verb == "soups":
				k = self.m.soup(i, p.j, side, level)
			elif verb == "rejects":
				r = self.m.dayrange(p)
				if not r:
					return None
				th = self.m.th
				k = self.m.reject(i, p.j, level, th["near"] * r, th["bounce"] * r)
			else:
				k = self.m.first(i, p.j, side, level, close)
			if k is None:
				return None
			after = k
		return Time(after, self.m)

	def fill(self, p, z, after):
		"""the candle of p that fills zone z (after candle after): trades
		to its far side, the low of a gap up or a bullish FVG, the high of a
		gap down or a bearish one; a quadrant from the side price is on"""
		if z is None:
			return None
		if not isinstance(z, Zone):
			raise QueryError("fills is for a gap or an FVG, or a quarter of one: nyam fills rthog, day fills nyam.fvg5")
		c = self.m.c
		i = max(p.i, int(np.searchsorted(c.wall, z.e)))
		if after is not None:
			i = max(i, after + 1)
		if i >= p.j:
			return None
		d = z.more.get("dir")
		if d is None:	# a quarter: from where price is
			ref = c.c[i - 1] if i > 0 else c.o[i]
			d = "up" if ref >= z.attr("ce") else "down"
		if d in ("up", "bull"):
			return self.m.first(i, p.j, -1, z.low + 1e-9) if c.l[i:p.j].min() <= z.low else None
		return self.m.first(i, p.j, 1, z.high - 1e-9) if c.h[i:p.j].max() >= z.high else None

	def source(self, n, u):
		"""the period a level comes from (asia for asia.low), or None"""
		if n[0] != "path":
			return None
		if n[2] and n[2][-1] in ("high", "low", "ce", "mid", "dq", "uq", "open", "close", "settle"):
			v = self.path(("path", n[1], n[2][:-1]), u)	# what the level is of
			return v if isinstance(v, (Period, Zone)) else None
		return None

	def keyof(self, k, u):
		if k[0] == "key":
			d = u.date()
			name = k[1]
			if name == "weekday":
				return d.strftime("%a") if u.kind in ("day", "window", "session") else None
			if name == "session":
				return u.name if u.kind in ("window", "session") else None
			if name == "month":
				return f"{d:%Y-%m}"
			if name == "monthname":
				return d.strftime("%b")
			if name == "year":
				return str(d.year)
			if name == "quarter":
				return f"{d.year} Q{(d.month - 1) // 3 + 1}"
			if name == "hour":
				raise QueryError("by hour of what? say by day.high.hour, or (when …).hour")
		v = self.node(k, u)
		if isinstance(v, Period):
			v = v.cond()
		return v if isinstance(v, Clock) or (isinstance(v, (int, float)) and not isinstance(v, bool)) else show(v)

	def run(self):
		q = self.q
		stat = q["stat"]
		rows = []	# (unit, keys, value)
		for u in self.units():
			if u.empty() or not self.kept(u):
				continue
			if q["among"] is not None:
				a = self.path(q["among"], u)
				if not isinstance(a, Period) or a.empty():
					continue
			if q["where"] is not None and not self.cond(q["where"], u):
				continue
			keys = tuple(self.keyof(k, u) for k in q["by"])
			if any(k is None for k in keys):
				continue
			if stat == "share":
				v = self.cond(q["what"], u)
			elif stat in ("count", "list"):
				v = u
				if q["what"] is not None:
					v = self.path(q["what"], u)
					if not isinstance(v, Period) or v.empty():
						continue
			else:
				v = self.node(q["what"], u)
				if isinstance(v, Period):
					v = v.cond() if stat == "dist" else v.range()
			rows.append((u, keys, v))
		return Result(self, rows)

class Result:
	"""what a query gives: a table (headers, rows) and what its chart is"""
	def __init__(self, run, rows):
		self.run = run
		self.q = run.q
		self.unit = run.unit
		self.items = rows
		self.n = len(rows)
		self.periods = [u for u, _, _ in rows]
		self.pct = self.q["stat"] in ("dist", "share")	# the chart's values are percents
		self.make()

	def make(self):
		q, rows = self.q, self.items
		stat = q["stat"]
		nk = len(q["by"])
		self.chart = "bars"
		if stat == "list":
			self.headers = [self.unit] + [label(k) for k in q["by"]]
			self.rows = [[u.label()] + [show(k) for k in keys] for u, keys, _ in rows]
			self.chart = None
			return
		groups = {}
		for u, keys, v in rows:
			groups.setdefault(keys, []).append(v)
		order = sorted(groups, key=sortkey)
		if stat == "dist":
			vals = [v for _, _, v in rows]
			numeric = all(isinstance(v, (int, float, np.integer)) and not isinstance(v, bool) for v in vals if v is not None)
			isfloat = numeric and any(isinstance(v, float) and v != int(v) for v in vals if v is not None)
			if isfloat:
				edges = bins([v for v in vals if v is not None])
				binof = lambda v: None if v is None else binlabel(edges, v)
				cats = [binlabel(edges, e) for e in edges[:-1]]
			else:
				binof = lambda v: None if v is None else (v if numeric or isinstance(v, Clock) else show(v))
				cats = sorted({binof(v) for v in vals if v is not None}, key=catkey)
			if any(v is None for v in vals):
				cats.append("none")
			self.cats = [show(c) for c in cats]
			if nk == 0:
				counts = countof([binof(v) for v in vals], cats)
				tot = sum(counts)
				self.headers = [label(q["what"]), self.unit + "s", "%"]
				self.rows = [[show(c), n, pct(n, tot)] for c, n in zip(cats, counts)]
				self.series = {"": [100 * n / tot if tot else 0 for n in counts]}
			else:	# a row a key, a column a value: shares in the row
				self.headers = [" / ".join(label(k) for k in q["by"])] + self.cats + [self.unit + "s"]
				self.rows, self.series = [], {}
				for k in order:
					counts = countof([binof(v) for v in groups[k]], cats)
					tot = sum(counts)
					self.rows.append([" ".join(show(x) for x in k)] + [pct(n, tot) for n in counts] + [tot])
					self.series[" ".join(show(x) for x in k)] = [100 * n / tot if tot else 0 for n in counts]
				self.chart = "grid"
			return
		if stat in ("count", "share") or stat in ("avg", "median", "min", "max", "sum"):
			if stat == "share":
				f = lambda vs: (100 * sum(1 for v in vs if v) / len(vs)) if vs else None
				name = "% " + label(q["what"])
			elif stat == "count":
				f = len
				name = self.unit + "s"
			else:
				fn = {"avg": np.mean, "median": np.median, "min": np.min, "max": np.max, "sum": np.sum}[stat]
				def f(vs):
					xs = [num(v) if not isinstance(v, Time) or isinstance(v, Extreme) else v.hours() for v in vs]
					xs = [x for x in xs if x is not None]
					return float(fn(xs)) if xs else None
				name = f"{stat} {label(q['what'])}"
			if nk == 0:
				v = f(groups.get((), []))
				self.headers = [name] if stat == "count" else [name, self.unit + "s"]
				self.rows = [[fmt(stat, v)] + ([] if stat == "count" else [self.n])]
				self.series = {"": [v or 0]}
				self.cats = [name]
				self.chart = None
			else:
				k1 = sorted({k[0] for k in order}, key=sortkey)
				k2 = sorted({k[1] for k in order}, key=sortkey) if nk == 2 else [None]
				self.cats = [show(x) for x in k1]
				self.headers = [label(q["by"][0])] + ([name, self.unit + "s"] if nk == 1 else [show(x) for x in k2])
				self.rows, self.series = [], {}
				if nk == 1:
					vals = [f(groups[(a,)]) for a in k1]
					self.rows = [[show(a), fmt(stat, v), len(groups[(a,)])]
						for a, v in zip(k1, vals)]
					self.series = {"": [v or 0 for v in vals]}
				else:
					for a in k1:
						vals = [f(groups[(a, b)]) if (a, b) in groups else None for b in k2]
						self.rows.append([show(a)] + [fmt(stat, v) for v in vals])
					self.series = {show(b): [f(groups[(a, b)]) or 0 if (a, b) in groups else 0 for a in k1] for b in k2}
					self.chart = "grid"
			return
		raise QueryError(f"no {stat}")

	def text(self):
		"""the table as text, for a terminal"""
		rows = [[str(x) for x in r] for r in [self.headers] + self.rows]
		w = [max(len(r[i]) for r in rows) for i in range(len(self.headers))]
		out = ["  ".join(c.rjust(w[i]) if i else c.ljust(w[i]) for i, c in enumerate(r)) for r in rows]
		out.insert(1, "  ".join("-" * x for x in w))
		return "\n".join(out) + f"\n\n{self.summary()}"

	def summary(self):
		c = self.run.m.c
		tf = m15.tfname(c.tf)
		if not self.periods:
			return f"no {self.unit}s ({tf})"
		return f"on {self.n} {self.unit}{'s' if self.n != 1 else ''}, {self.periods[0].date():%y-%m-%d} to " \
			f"{self.periods[-1].date():%y-%m-%d} ({tf})"

def fmt(stat, v):
	if v is None:
		return "–"
	if stat == "share":
		return f"{v:.0f}%"
	return show(round(v, 2) if isinstance(v, float) else v)

def countof(xs, cats):
	out = [0] * len(cats)
	idx = {c: i for i, c in enumerate(cats)}
	for x in xs:
		x = "none" if x is None else x
		if x in idx:
			out[idx[x]] += 1
	return out

def pct(n, tot):
	return f"{100 * n / tot:.0f}%" if tot else "–"

ORDER = {w: i for i, w in enumerate(WEEKDAYS + ["sun"])}
ORDER.update({c: 10 + i for i, c in enumerate(CONDS)})
ORDER.update({s: 30 + i for i, s in enumerate(list(SESSIONS) + ["other"])})
ORDER.update({d.lower(): 40 + i for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"])})
ORDER.update({m: 50 + i for i, m in enumerate(MONTHS)})
ORDER.update({"up": 70, "down": 71, "none": 99})

def catkey(c):
	if isinstance(c, (Hour, Clock)):
		return (0, c.order(), "")
	if isinstance(c, (int, float)):
		return (0, c, "")
	s = str(c).lower()
	return (1, ORDER.get(s, 80), s)

def sortkey(k):
	return tuple(catkey(x) for x in k) if isinstance(k, tuple) else catkey(k)

def bins(xs, n=10):
	lo, hi = min(xs), max(xs)
	if hi <= lo:
		return [lo, lo + 1]
	step = niceround((hi - lo) / n)
	a = np.floor(lo / step) * step
	edges = [a]
	while edges[-1] <= hi:
		edges.append(edges[-1] + step)
	return edges

def niceround(x):
	e = 10 ** np.floor(np.log10(x))
	for f in (1, 2, 2.5, 5, 10):
		if x <= f * e:
			return f * e
	return 10 * e

def binlabel(edges, v):
	k = max(0, min(len(edges) - 2, int(np.searchsorted(edges, v, "right")) - 1))
	return f"{m15.price(edges[k])}–{m15.price(edges[k + 1])}"

def label(n):
	"""an expression as the query wrote it, roughly"""
	if n is None:
		return ""
	t = n[0]
	if t == "key":
		return n[1]
	if t == "num":
		return show(n[1])
	if t == "path":
		return ".".join([baselabel(n[1])] + n[2])
	if t == "when":
		return "when"
	if t == "bin":
		return f"{label(n[2])} {n[1]} {label(n[3])}"
	if t == "is":
		return f"{label(n[1])} is {'not ' if n[3] else ''}{n[2]}"
	if t == "cmp":
		return f"{label(n[2])} {n[1]} {label(n[3])}"
	if t == "seq":
		return " then ".join(f"{verbs(s)} {label(x)}" for s in [n[1]] for (_, v, x, c) in s for verbs in
			[lambda s, v=v, c=c: ("closes " if c else "") + v])
	if t in ("and", "or"):
		return f"{label(n[1])} {t} {label(n[2])}"
	if t == "not":
		return "not " + label(n[1])
	if t == "true":
		return label(n[1])
	return t

def baselabel(b):
	if b[0] == "name":
		return b[1]
	if b[0] == "window":
		return b[1]
	if b[0] == "rel":
		return ("prev " if b[1] < 0 else "next ") + baselabel(b[2])
	return "?"

# --- the whole thing ---

class Journal:
	"""the models of a journal's candles, by time frame, made once"""
	def __init__(self, dir):
		self.dir = dir
		self.models = {}

	def model(self, tf):
		th = thresholds(self.dir)
		m = self.models.get(tf)
		if m is None or m.th != th:
			c = m.c if m is not None else Candles(self.dir, tf)
			if not len(c.t):
				raise QueryError(f"no {m15.tfname(tf)} data in the journal")
			m = self.models[tf] = Model(c, th, self.candles)
		return m

	def candles(self, tf):
		"""the candles of tf, made once"""
		m = self.models.get(tf)
		if m is not None:
			return m.c
		c = Candles(self.dir, tf)
		self.models[tf] = Model(c, thresholds(self.dir), self.candles)
		return c

	def run(self, text, tf=15, only=None):
		q = parse(text)
		m = self.model(q["tf"] or tf)
		return Run(m, q, only).run()

def main(argv):
	import argparse
	ap = argparse.ArgumentParser(description="ask the m15 data of a journal: python3 query.py journal 'query'")
	ap.add_argument("journal")
	ap.add_argument("query", nargs="+")
	a = ap.parse_args(argv)
	j = Journal(a.journal)
	for text in a.query:
		print(f"> {text}")
		try:
			print(j.run(text).text())
		except QueryError as e:
			if e.pos is not None:
				print(" " * (e.pos + 2) + "^")
			print("error:", e)
		print()

if __name__ == "__main__":
	main(sys.argv[1:])
