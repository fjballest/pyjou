"""What the compiled scripts run on: na, series history, call site state,
the bars of each time frame, and the built-in variables and functions.

Times are milliseconds since 1970 (UTC) as in Pine; colors are tuples
(r, g, b, transparency 0-100); na is a float nan (so arithmetic on it
gives na and comparisons with it are false)."""

import math
import re
from bisect import bisect_left, bisect_right
from collections import deque
from datetime import datetime, timedelta, timezone

import numpy as np

try:
	from zoneinfo import ZoneInfo
except Exception:	# pragma: no cover
	ZoneInfo = None

na = float("nan")
UNSET = object()

class PineRuntimeError(Exception):
	pass

def isna(x):
	return x is None or (x.__class__ is float and x != x)

def nz(x, y=0):
	return y if isna(x) else x

def div(a, b):
	try:
		return a / b
	except ZeroDivisionError:
		return na
	except TypeError:
		if isna(a) or isna(b):
			return na
		raise

def mod(a, b):
	try:
		return math.fmod(a, b) if (a.__class__ is float or b.__class__ is float) else (a - b * int(a / b))
	except (ZeroDivisionError, ValueError):
		return na

def toint(x):
	if isna(x):
		return na
	return int(x)

def tofloat(x):
	return na if isna(x) else float(x)

def ident(x=na, *_a, **_k):
	return x

def frange(a, b, step=None):
	"""the values of for i = a to b [by step]: down when b < a"""
	if isna(a) or isna(b):
		return ()
	s = 1 if step is None or isna(step) else abs(step)
	if s == 0:
		s = 1
	if a.__class__ is int and b.__class__ is int and s.__class__ is int:
		return range(a, b + 1, s) if a <= b else range(a, b - 1, -s)
	out = []
	if a <= b:
		x = a
		while x <= b:
			out.append(x)
			x += s
	else:
		x = a
		while x >= b:
			out.append(x)
			x -= s
	return out

def iterof(x):
	if isna(x):
		return ()
	if isinstance(x, PMap):
		return list(x.items())
	return list(x)

def enumof(x):
	if isna(x):
		return ()
	if isinstance(x, PMap):
		return list(x.items())
	return list(enumerate(x))

def noop(*_a, **_k):
	return na

def nsm(obj, name):
	"""array.get(a, i), line.delete(l)...: obj's method name, nothing for na"""
	if isna(obj):
		return noop
	return getattr(obj, name)

# ---------------------------------------------------------------- state

class Hist:
	"""the values of a series by bar, for x[n]"""
	__slots__ = ("b", "v")
	def __init__(self):
		self.b = []
		self.v = []

	def set(self, x):
		bar = RT.bar
		b = self.b
		if b and b[-1] == bar:
			self.v[-1] = x
		else:
			if b and b[-1] > bar:	# a context that started again
				del b[:], self.v[:]
			b.append(bar)
			self.v.append(x)
			if len(b) > 12000:
				del b[:6000], self.v[:6000]
		return x

	def get(self, n):
		if isna(n):
			return na
		b = self.b
		if not b:
			return na
		want = RT.bar - int(n)
		k = len(b) - 1 - (b[-1] - want)
		if 0 <= k < len(b) and b[k] == want:
			return self.v[k]
		k = bisect_right(b, want) - 1
		return self.v[k] if k >= 0 else na

class Ctx:
	"""the state of a call site: those it calls, its ta state, var values
	and series history"""
	__slots__ = ("kids", "st", "v", "hs")
	def __init__(self):
		self.kids = {}
		self.st = {}
		self.v = {}
		self.hs = {}

	def sub(self, site):
		c = self.kids.get(site)
		if c is None:
			c = self.kids[site] = Ctx()
		return c

	def h(self, name):
		x = self.hs.get(name)
		if x is None:
			x = self.hs[name] = Hist()
		return x

def hx(c, site, value, n):
	"""(expr)[n]: value recorded at this site, and the one n bars ago"""
	h = c.hs.get(site)
	if h is None:
		h = c.hs[site] = Hist()
	h.set(value)
	return h.get(n)

# ---------------------------------------------------------------- time

_ZONES = {}
def zone(tz):
	"""a tzinfo for tz: an IANA name, UTC, GMT+1, UTC-05:00"""
	z = _ZONES.get(tz)
	if z is None:
		s = (tz or "").strip()
		m = re.fullmatch(r"(?:UTC|GMT|Etc/UTC|Etc/GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?", s)
		if s in ("", "UTC", "GMT", "Etc/UTC", "Etc/GMT", "Z"):
			z = timezone.utc
		elif m and (s.startswith("UTC") or s.startswith("GMT") or s[0] in "+-"):
			off = (int(m.group(2)) * 60 + int(m.group(3) or 0)) * (1 if m.group(1) == "+" else -1)
			z = timezone(timedelta(minutes=off))
		else:
			try:
				z = ZoneInfo(s)
			except Exception:
				z = timezone.utc
		_ZONES[tz] = z
	return z

_OFFS = {}
def tzoff(tz, ms):
	"""the offset of time zone tz at time ms, in ms"""
	k = (tz, int(ms) // 1800000)
	o = _OFFS.get(k)
	if o is None:
		z = zone(tz)
		o = int(datetime.fromtimestamp(int(ms) // 1000, z).utcoffset().total_seconds()) * 1000
		if len(_OFFS) > 200000:
			_OFFS.clear()
		_OFFS[k] = o
	return o

def tzoffs(tz, ms):
	"""tzoff of each time of array ms"""
	ms = np.asarray(ms, dtype=np.int64)
	if not len(ms):
		return ms
	k, inv = np.unique(ms // 1800000, return_inverse=True)
	return np.array([tzoff(tz, int(x) * 1800000) for x in k], dtype=np.int64)[inv]

_FIELDS = {}
def fields(ms, tz):
	"""(year, month, day, hour, minute, second, dayofweek 1=Sunday) of time ms in tz"""
	if isna(ms):
		return None
	if tz is None:
		tz = RT.tz
	k = (int(ms), tz)
	f = _FIELDS.get(k)
	if f is None:
		w = int(ms) + tzoff(tz, ms)
		d = datetime(1970, 1, 1) + timedelta(milliseconds=w)
		f = (d.year, d.month, d.day, d.hour, d.minute, d.second, (d.isoweekday() % 7) + 1)
		if len(_FIELDS) > 300000:
			_FIELDS.clear()
		_FIELDS[k] = f
	return f

def _tfield(i):
	def f(t=None, tz=None):
		if t is None:
			t = RT.S.t[RT.bar]
		x = fields(t, tz)
		return na if x is None else x[i]
	return f

def weekofyear(t=None, tz=None):
	if t is None:
		t = RT.S.t[RT.bar]
	if isna(t):
		return na
	if tz is None:
		tz = RT.tz
	w = int(t) + tzoff(tz, t)
	d = datetime(1970, 1, 1) + timedelta(milliseconds=w)
	return d.isocalendar()[1]

def timestamp(*a, **k):
	"""timestamp(datestring), timestamp(year, month, day, h, m, s) or
	timestamp(tz, year, month, day, h, m, s)"""
	a = list(a)
	if a and isinstance(a[0], str) and len(a) == 1 and not k:
		return parsedate(a[0])
	tz = RT.tz
	if a and isinstance(a[0], str):
		tz = a.pop(0)
	if "timezone" in k:
		tz = k.pop("timezone")
	names = ["year", "month", "day", "hour", "minute", "second"]
	vals = a + [k.get(n, 0) for n in names[len(a):]]
	vals = (vals + [0] * 6)[:6]
	if any(isna(v) for v in vals):
		return na
	y, mo, d, h, mi, s = [int(v) for v in vals]
	base = datetime(y, 1, 1) + timedelta(days=0)
	# month and day may run over, as in Pine
	y += (mo - 1) // 12
	mo = (mo - 1) % 12 + 1
	base = datetime(y, mo, 1) + timedelta(days=d - 1, hours=h, minutes=mi, seconds=s)
	wall = int((base - datetime(1970, 1, 1)).total_seconds() * 1000)
	off = tzoff(tz, wall - tzoff(tz, wall))
	return wall - off

def parsedate(s):
	s = s.strip()
	for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d %b %Y %H:%M", "%d %b %Y"):
		try:
			d = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
			return int(d.timestamp() * 1000)
		except ValueError:
			pass
	m = re.fullmatch(r"(.*?)\s*([+-]\d{2}:?\d{2}|Z|GMT[+-]?\d*|UTC)$", s)
	if m:
		base = parsedate(m.group(1))
		z = m.group(2).replace("GMT", "").replace("UTC", "") or "+0000"
		if z == "Z":
			z = "+0000"
		z = z.replace(":", "")
		if len(z) <= 3:
			z = (z if z[0] in "+-" else "+" + z).ljust(3, "0") + "00"
		off = (int(z[1:3]) * 60 + int(z[3:5] or 0)) * (1 if z[0] == "+" else -1)
		return base - off * 60000
	try:
		d = datetime.fromisoformat(s)
		if d.tzinfo is None:
			d = d.replace(tzinfo=timezone.utc)
		return int(d.timestamp() * 1000)
	except ValueError:
		return na

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TIMEPAT = re.compile(r"'[^']*'|y+|M+|d+|E+|H+|h+|m+|s+|S+|a|Z+|z+|X+|[^'yMdEHhmsSaZzX]+")

def format_time(t, fmt="yyyy-MM-dd'T'HH:mm:ssZ", tz=None):
	if isna(t):
		return ""
	if tz is None:
		tz = RT.tz
	off = tzoff(tz, t)
	d = datetime(1970, 1, 1) + timedelta(milliseconds=int(t) + off)
	out = []
	for p in TIMEPAT.findall(fmt):
		c, n = p[0], len(p)
		if c == "'":
			out.append(p[1:-1] if n > 2 else "'")
		elif c == "y":
			out.append(f"{d.year % 100:02d}" if n == 2 else f"{d.year:04d}")
		elif c == "M":
			out.append(MONTHS[d.month - 1] if n >= 4 else MONTHS[d.month - 1][:3] if n == 3 else f"{d.month:0{n}d}")
		elif c == "d":
			out.append(f"{d.day:0{n}d}")
		elif c == "E":
			out.append(DAYS[d.weekday()] if n >= 4 else DAYS[d.weekday()][:3])
		elif c == "H":
			out.append(f"{d.hour:0{n}d}")
		elif c == "h":
			out.append(f"{(d.hour % 12) or 12:0{n}d}")
		elif c == "m":
			out.append(f"{d.minute:0{n}d}")
		elif c == "s":
			out.append(f"{d.second:0{n}d}")
		elif c == "S":
			out.append(f"{d.microsecond // 1000:03d}"[:n])
		elif c == "a":
			out.append("AM" if d.hour < 12 else "PM")
		elif c in "ZXz":
			o = off // 60000
			out.append(f"{'+' if o >= 0 else '-'}{abs(o) // 60:02d}{abs(o) % 60:02d}")
		else:
			out.append(p)
	return "".join(out)

def tfsecs(tf=None):
	"""the seconds of time frame string tf ("" is the chart's)"""
	if tf is None or isna(tf) or tf == "":
		tf = RT.tfp
	tf = str(tf).strip().upper()
	m = re.fullmatch(r"(\d*)([SDWM]?)", tf)
	if not m:
		raise PineRuntimeError(f"bad timeframe {tf!r}")
	n = int(m.group(1) or 1)
	u = m.group(2)
	if u == "S":
		return n
	if u == "D":
		return n * 86400
	if u == "W":
		return n * 604800
	if u == "M":
		return n * 2628003
	return n * 60

def tfkind(tf):
	"""("m", minutes) or ("D"|"W"|"M", n) or ("S", seconds)"""
	if tf is None or isna(tf) or tf == "":
		tf = RT.tfp
	tf = str(tf).strip().upper()
	m = re.fullmatch(r"(\d*)([SDWM]?)", tf)
	n = int(m.group(1) or 1)
	return (m.group(2) or "m", n)

def tfstring(kind, n):
	if kind == "m":
		return str(n)
	return (str(n) if n != 1 else "") + kind

def from_seconds(s):
	s = int(s)
	if s % 2628003 == 0 or s >= 2628003:
		return tfstring("M", max(1, s // 2628003))
	if s % 604800 == 0:
		return tfstring("W", s // 604800)
	if s % 86400 == 0:
		return tfstring("D", s // 86400)
	if s % 60 == 0:
		return str(s // 60)
	return f"{s}S"

# ---------------------------------------------------------------- sessions

_SESS = {}
def session(spec):
	"""[(start min, end min, days)] of session spec "0930-1600:23456" """
	s = _SESS.get(spec)
	if s is None:
		s = []
		for part in str(spec).split(","):
			part = part.strip()
			if not part:
				continue
			days = set(range(1, 8))
			if ":" in part:
				part, d = part.split(":", 1)
				days = {int(c) for c in d if c.isdigit()}
			if "-" not in part:
				continue
			a, b = part.split("-", 1)
			s.append((int(a[:2]) * 60 + int(a[2:4]), int(b[:2]) * 60 + int(b[2:4]), days))
		_SESS[spec] = s
	return s

def insession(ms, spec, tz):
	"""whether time ms is in session spec, in tz"""
	f = fields(ms, tz)
	m = f[3] * 60 + f[4]
	dow = f[6]
	for a, b, days in session(spec):
		if a < b:
			if a <= m < b and dow in days:
				return True
		elif a > b:	# overnight: the day is the one it ends on
			if m >= a and (dow % 7) + 1 in days:
				return True
			if m < b and dow in days:
				return True
		else:	# 24 hours
			if dow in days:
				return True
	return False

def ptime(tf=None, session_=None, tz=None, bars_back=0, close=False):
	"""time(tf, session, tz): the start (or close) of the tf bar holding the
	current bar, na outside session"""
	S, i = RT.S, RT.bar
	if bars_back:
		i -= int(bars_back)
		if i < 0:
			return na
	t = S.t[i]
	if session_ is not None and not isna(session_) and session_ != "":
		if not insession(t, session_, tz if tz is not None else RT.tz):
			return na
	if tf is None or isna(tf) or tf == "" or tf == RT.tfp:
		return S.tc[i] if close else t
	return RT.bartime(tf, t, close)

def time_(tf=None, session=None, timezone=None, bars_back=0, **k):
	if "session" in k:
		session = k["session"]
	return ptime(tf, session, timezone, bars_back)

def time_close_(tf=None, session=None, timezone=None, bars_back=0, **k):
	return ptime(tf, session, timezone, bars_back, close=True)

# ---------------------------------------------------------------- bars

class Series:
	"""bars of one time frame: lists of t (ms), o, h, l, c, v and tc (close time)"""
	def __init__(self, t, o, h, l, c, tc, tfp, v=None):
		self.t = [int(x) for x in t]
		self.o = [float(x) for x in o]
		self.h = [float(x) for x in h]
		self.l = [float(x) for x in l]
		self.c = [float(x) for x in c]
		self.v = [na] * len(self.t) if v is None else [float(x) for x in v]
		self.tc = [int(x) for x in tc]
		self.tfp = tfp
		self.n = len(self.t)
		f = np.asarray(self.t, dtype=np.int64)
		wall = f + tzoffs(RT.tz, f) if len(f) else f
		days = wall // 86400000
		self.tday = (((wall + 6 * 3600000) // 86400000) * 86400000).tolist()	# trading days start at 18:00
		self.hour = ((wall // 3600000) % 24).tolist()
		self.minute = ((wall // 60000) % 60).tolist()
		self.second = ((wall // 1000) % 60).tolist()
		self.dow = (((days + 4) % 7) + 1).tolist()
		dd = days.astype("datetime64[D]")
		self.year = (dd.astype("datetime64[Y]").astype(np.int64) + 1970).tolist()
		self.month = (dd.astype("datetime64[M]").astype(np.int64) % 12 + 1).tolist()
		self.dom = ((dd - dd.astype("datetime64[M]")).astype(np.int64) + 1).tolist()

	def find(self, ms):
		"""the index of the bar holding time ms, or -1"""
		return bisect_right(self.t, ms) - 1

SERIESVARS = ("open", "high", "low", "close", "volume", "time", "time_close", "bar_index", "hl2", "hlc3",
	"ohlc4", "hlcc4", "hour", "minute", "second", "dayofweek", "dayofmonth", "month", "year", "weekofyear",
	"time_tradingday", "last_bar_index", "last_bar_time", "timenow")

def setbar(ns, S, i):
	"""the built-in series of bar i of S into the script's globals ns"""
	RT.S = S
	RT.bar = i
	o, h, l, c = S.o[i], S.h[i], S.l[i], S.c[i]
	ns["open"] = o
	ns["high"] = h
	ns["low"] = l
	ns["close"] = c
	ns["volume"] = S.v[i]
	ns["time"] = S.t[i]
	ns["time_close"] = S.tc[i]
	ns["bar_index"] = i
	ns["hl2"] = (h + l) / 2
	ns["hlc3"] = (h + l + c) / 3
	ns["ohlc4"] = (o + h + l + c) / 4
	ns["hlcc4"] = (h + l + c + c) / 4
	ns["hour"] = S.hour[i]
	ns["minute"] = S.minute[i]
	ns["second"] = S.second[i]
	ns["dayofweek"] = S.dow[i]
	ns["dayofmonth"] = S.dom[i]
	ns["month"] = S.month[i]
	ns["year"] = S.year[i]
	ns["time_tradingday"] = S.tday[i]
	ns["last_bar_index"] = S.n - 1
	ns["last_bar_time"] = S.t[-1]
	ns["timenow"] = S.tc[-1]
	RT.isfirst = i == 0
	RT.islast = i == S.n - 1
	RT.tfp = S.tfp

SERIESOF = {"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v", "time": "t", "time_close": "tc",
	"hour": "hour", "minute": "minute", "second": "second", "dayofweek": "dow", "dayofmonth": "dom",
	"month": "month", "year": "year", "time_tradingday": "tday"}

def sh(name, n):
	"""builtin series name n bars ago"""
	if isna(n):
		return na
	i = RT.bar - int(n)
	if i < 0:
		return na
	S = RT.S
	if i >= S.n:
		return na
	if name == "bar_index":
		return i
	a = SERIESOF.get(name)
	if a is not None:
		return getattr(S, a)[i]
	o, h, l, c = S.o[i], S.h[i], S.l[i], S.c[i]
	if name == "hl2":
		return (h + l) / 2
	if name == "hlc3":
		return (h + l + c) / 3
	if name == "ohlc4":
		return (o + h + l + c) / 4
	if name == "hlcc4":
		return (h + l + c + c) / 4
	raise PineRuntimeError(f"no history for {name}")

class Runtime:
	"""the state of the run: the bars in context, barstate, the drawings"""
	def __init__(self):
		self.reset()

	def reset(self):
		self.S = None
		self.bar = 0
		self.isfirst = False
		self.islast = False
		self.tfp = "15"
		self.tz = "America/New_York"
		self.ns = None
		self.sources = None
		self.htfs = {}
		self.limits = {"line": 50, "label": 50, "box": 50, "polyline": 50}
		self.objs = {"line": deque(), "label": deque(), "box": deque(), "table": [], "polyline": deque(), "linefill": deque()}
		self.alive = {"line": 0, "label": 0, "box": 0, "polyline": 0, "linefill": 0}
		self.plots = {}
		self.inputs = {}	# {key: value} instead of the defaults
		self.specs = {}		# {call site: Input}
		self.inputkeys = set()
		self.symbol = "NQ"
		self.chart = None
		self.title = ""
		self.overlay = True
		self.depth = 0

	# barstate
	@property
	def isconfirmed(self):
		return True
	isnew = True
	isrealtime = False
	ishistory = True

	@property
	def islastconfirmedhistory(self):
		return self.islast

	# timeframe
	@property
	def multiplier(self):
		k, n = tfkind(self.tfp)
		return n

	@property
	def isminutes(self):
		return tfkind(self.tfp)[0] == "m"

	@property
	def isseconds(self):
		return tfkind(self.tfp)[0] == "S"

	@property
	def isdaily(self):
		return tfkind(self.tfp)[0] == "D"

	@property
	def isweekly(self):
		return tfkind(self.tfp)[0] == "W"

	@property
	def ismonthly(self):
		return tfkind(self.tfp)[0] == "M"

	@property
	def isintraday(self):
		return tfkind(self.tfp)[0] in "mS"

	@property
	def isdwm(self):
		return tfkind(self.tfp)[0] in "DWM"

	@property
	def tr(self):
		S, i = self.S, self.bar
		h, l = S.h[i], S.l[i]
		if i == 0:
			return h - l
		c1 = S.c[i - 1]
		return max(h - l, abs(h - c1), abs(l - c1))

	def htf(self, tf):
		"""the Series of time frame tf, built by the sources"""
		key = tfkind(tf)
		s = self.htfs.get(key)
		if s is None:
			s = self.htfs[key] = self.sources(key)
		return s

	def bartime(self, tf, t, close=False):
		"""the start (close) of the bar of tf that holds time t"""
		s = self.htf(tf)
		if s is None or not s.n:
			return na
		k = s.find(t)
		if k < 0:
			return na
		return s.tc[k] if close else s.t[k]

	def add(self, kind, obj):
		q = self.objs[kind]
		q.append(obj)
		self.alive[kind] += 1
		lim = self.limits.get(kind, 500)
		while self.alive[kind] > lim and q:
			old = q.popleft()
			if old.alive:
				old.alive = False
				self.alive[kind] -= 1
		return obj

	def gone(self, kind):
		self.alive[kind] -= 1
		q = self.objs[kind]
		while q and not q[0].alive:
			q.popleft()

RT = Runtime()

# ---------------------------------------------------------------- arrays and maps

class PArray(list):
	__slots__ = ("et",)
	def __init__(self, it=(), et=None):
		list.__init__(self, it)
		self.et = et

	def get(self, i):
		return list.__getitem__(self, i)

	def set(self, i, v):
		list.__setitem__(self, i, v)

	def push(self, v):
		self.append(v)

	def unshift(self, v):
		list.insert(self, 0, v)

	def shift(self):
		if not self:
			return na
		return list.pop(self, 0)

	def pop(self):
		if not self:
			return na
		return list.pop(self)

	def remove(self, i):
		return list.pop(self, i)

	def insert(self, i, v):
		list.insert(self, i, v)

	def size(self):
		return len(self)

	def first(self):
		return list.__getitem__(self, 0)

	def last(self):
		return list.__getitem__(self, -1)

	def clear(self):
		del self[:]

	def includes(self, v):
		return v in self

	def indexof(self, v):
		try:
			return self.index(v)
		except ValueError:
			return -1

	def lastindexof(self, v):
		for i in range(len(self) - 1, -1, -1):
			if self[i] == v:
				return i
		return -1

	def copy(self):
		return PArray(self, self.et)

	def slice(self, a, b=None):
		return PArray(list.__getitem__(self, slice(a, b)), self.et)

	def concat(self, other):
		self.extend(other)
		return self

	def reverse(self):
		list.reverse(self)

	def sort(self, order=None):
		list.sort(self, reverse=order == "descending")

	def sort_indices(self, order=None):
		return PArray(sorted(range(len(self)), key=lambda i: self[i], reverse=order == "descending"), "int")

	def fill(self, v, a=0, b=None):
		for i in range(a, len(self) if b is None else b):
			self[i] = v

	def _nums(self):
		return [x for x in self if not isna(x)]

	def sum(self):
		return math.fsum(self._nums()) if self else na

	def avg(self):
		n = self._nums()
		return math.fsum(n) / len(n) if n else na

	def max(self, nth=0):
		n = sorted(self._nums(), reverse=True)
		return n[nth] if len(n) > nth else na

	def min(self, nth=0):
		n = sorted(self._nums())
		return n[nth] if len(n) > nth else na

	def median(self):
		n = sorted(self._nums())
		if not n:
			return na
		k = len(n) // 2
		return n[k] if len(n) % 2 else (n[k - 1] + n[k]) / 2

	def range(self):
		n = self._nums()
		return max(n) - min(n) if n else na

	def stdev(self, biased=True):
		n = self._nums()
		if not n:
			return na
		m = sum(n) / len(n)
		d = len(n) if biased else max(1, len(n) - 1)
		return math.sqrt(sum((x - m) ** 2 for x in n) / d)

	def variance(self, biased=True):
		s = self.stdev(biased)
		return s * s

	def join(self, sep=","):
		return sep.join(tostring(x) for x in self)

	def every(self):
		return all(self)

	def some(self):
		return any(self)

	def abs(self):
		return PArray([abs(x) for x in self], self.et)

	def binary_search(self, v):
		i = bisect_left(self, v)
		return i if i < len(self) and self[i] == v else -1

	def binary_search_leftmost(self, v):
		return bisect_left(self, v)

	def binary_search_rightmost(self, v):
		return bisect_right(self, v)

class PMap(dict):
	__slots__ = ("kt", "vt")
	def __init__(self, kt=None, vt=None):
		dict.__init__(self)
		self.kt, self.vt = kt, vt

	def get(self, k):
		return dict.get(self, k, na)

	def put(self, k, v):
		old = dict.get(self, k, na)
		self[k] = v
		return old

	def contains(self, k):
		return k in self

	def remove(self, k):
		return dict.pop(self, k, na)

	def size(self):
		return len(self)

	def keys(self):
		return PArray(dict.keys(self), self.kt)

	def values(self):
		return PArray(dict.values(self), self.vt)

	def copy(self):
		m = PMap(self.kt, self.vt)
		m.update(self)
		return m

	def put_all(self, other):
		self.update(other)

def typename(t):
	if t is None:
		return None
	name, args = t
	return name + ("<" + ",".join(typename(a) for a in args) + ">" if args else "")

def array_new(*a, _t=None, **k):
	size = a[0] if a else k.get("size", 0)
	init = a[1] if len(a) > 1 else k.get("initial_value", na)
	et = typename(_t[0]) if _t else None
	return PArray([init] * int(size or 0), et)

def array_newof(et):
	def f(size=0, initial_value=na):
		return PArray([initial_value] * int(size or 0), et)
	return f

def array_from(*a, _t=None):
	et = typename(_t[0]) if _t else (typeof(a[0]) if a else None)
	return PArray(a, et)

def map_new(_t=None):
	return PMap(typename(_t[0]) if _t else None, typename(_t[1]) if _t and len(_t) > 1 else None)

def typeof(x):
	"""the Pine type name of value x, for methods"""
	c = x.__class__
	if c is float:
		return "float"
	if c is int:
		return "int"
	if c is bool:
		return "bool"
	if c is str:
		return "string"
	if c is tuple:
		return "color"
	if c is PArray:
		return "array<" + x.et + ">" if x.et else "array"
	if c is PMap:
		return "map"
	return getattr(c, "_pine", c.__name__)

class UDT:
	__slots__ = ()
	def copy(self):
		o = object.__new__(self.__class__)
		for f in self.__slots__:
			setattr(o, f, getattr(self, f))
		return o

# ---------------------------------------------------------------- colors

def rgb(r, g, b, t=0):
	if isna(r) or isna(g) or isna(b):
		return na
	return (r, g, b, 0 if isna(t) else t)

def color_new(c, t=0):
	if isna(c):
		return na
	return (c[0], c[1], c[2], 0 if isna(t) else max(0, min(100, t)))

def color_r(c):
	return na if isna(c) else c[0]

def color_g(c):
	return na if isna(c) else c[1]

def color_b(c):
	return na if isna(c) else c[2]

def color_t(c):
	return na if isna(c) else c[3]

def from_gradient(v, lo, hi, c1, c2):
	if isna(v) or isna(c1) or isna(c2):
		return na
	k = 0 if hi == lo else min(1, max(0, (v - lo) / (hi - lo)))
	return tuple(a + (b - a) * k for a, b in zip(c1, c2))

def hexcolor(s):
	s = s.lstrip("#")
	a = int(s[6:8], 16) if len(s) == 8 else 255
	return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), round((255 - a) / 255 * 100, 4))

COLORS = {"aqua": "#00BCD4", "black": "#363A45", "blue": "#2962FF", "fuchsia": "#E040FB", "gray": "#787B86",
	"green": "#4CAF50", "lime": "#00E676", "maroon": "#880E4F", "navy": "#311B92", "olive": "#808000",
	"orange": "#FF9800", "purple": "#9C27B0", "red": "#F23645", "silver": "#B2B5BE", "teal": "#089981",
	"white": "#FFFFFF", "yellow": "#FDD835"}

# ---------------------------------------------------------------- math and strings

def _nums(a):
	return any(isna(x) for x in a)

def mmax(*a):
	if len(a) == 1 and isinstance(a[0], list):
		a = a[0]
	return na if _nums(a) else max(a)

def mmin(*a):
	if len(a) == 1 and isinstance(a[0], list):
		a = a[0]
	return na if _nums(a) else min(a)

def mavg(*a):
	return na if _nums(a) else sum(a) / len(a)

def mabs(x):
	return na if isna(x) else abs(x)

def mround(x, precision=None):
	if isna(x):
		return na
	if precision is None or isna(precision):
		return int(math.floor(x + 0.5))
	k = 10 ** int(precision)
	return math.floor(x * k + 0.5) / k

def mfloor(x):
	return na if isna(x) else int(math.floor(x))

def mceil(x):
	return na if isna(x) else int(math.ceil(x))

def msign(x):
	return na if isna(x) else (1.0 if x > 0 else -1.0 if x < 0 else 0.0)

def _f1(fn):
	def f(x, *a):
		if isna(x):
			return na
		try:
			return fn(x, *a)
		except (ValueError, OverflowError, ZeroDivisionError):
			return na
	return f

def round_to_mintick(x):
	if isna(x):
		return na
	m = RT.mintick
	return round(x / m) * m

def tostring(v, fmt=None):
	if v is None or (v.__class__ is float and v != v):
		return "NaN"
	if v is True:
		return "true"
	if v is False:
		return "false"
	if isinstance(v, str):
		return v
	if isinstance(v, (PArray, list)):
		return "[" + ", ".join(tostring(x) for x in v) + "]"
	if isinstance(v, tuple):
		return "#%02X%02X%02X" % tuple(int(x) for x in v[:3])
	if not isinstance(v, (int, float)):
		return str(v)
	if fmt is None or isna(fmt):
		if v.__class__ is int:
			return str(v)
		s = f"{v:.10f}".rstrip("0").rstrip(".")
		return s if s not in ("-0", "") else "0"
	if fmt == "mintick":
		d = max(0, -int(math.floor(math.log10(RT.mintick)))) if RT.mintick < 1 else 0
		return f"{round_to_mintick(v):.{d}f}"
	if fmt == "percent":
		return tostring(round(v, 2)) + "%"
	if fmt == "volume":
		for div_, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
			if abs(v) >= div_:
				return tostring(round(v / div_, 3)) + suf
		return tostring(round(v, 3))
	if fmt in ("inherit", "price"):
		return tostring(v)
	m = re.fullmatch(r"([^#0.,]*)([#0,]*)(?:\.([#0]*))?(.*)", fmt)
	if not m:
		return tostring(v)
	pre, ip, dp, post = m.group(1), m.group(2), m.group(3) or "", m.group(4)
	fixed = dp.count("0")
	most = len(dp)
	s = f"{v:.{most}f}"
	if most > fixed and "." in s:
		whole, frac = s.split(".")
		frac = frac.rstrip("0")
		frac = frac.ljust(fixed, "0")
		s = whole + ("." + frac if frac else "")
	if "," in ip:
		whole, _, frac = s.partition(".")
		neg = whole.startswith("-")
		whole = f"{int(whole.lstrip('-')):,}"
		s = ("-" if neg else "") + whole + ("." + frac if frac else "")
	mins = ip.count("0")
	if mins > 1:
		whole, dot, frac = s.partition(".")
		neg = whole.startswith("-")
		whole = whole.lstrip("-").rjust(mins, "0")
		s = ("-" if neg else "") + whole + dot + frac
	if s in ("-0",):
		s = "0"
	return pre + s + post

def tonumber(s):
	if isna(s):
		return na
	try:
		return float(str(s).strip())
	except ValueError:
		return na

def substring(s, a, b=None):
	if isna(s):
		return na
	return s[int(a):] if b is None or isna(b) else s[int(a):int(b)]

def s_contains(s, x):
	return not isna(s) and x in s

def s_replace(s, target, repl, occurrence=0):
	if isna(s):
		return na
	i = -1
	for _ in range(int(occurrence) + 1):
		i = s.find(target, i + 1)
		if i < 0:
			return s
	return s[:i] + repl + s[i + len(target):]

def s_split(s, sep):
	if isna(s):
		return PArray([], "string")
	return PArray(list(s) if sep == "" else s.split(sep), "string")

def s_pos(s, x):
	if isna(s):
		return na
	i = s.find(x)
	return na if i < 0 else i

def s_format(fmt, *a):
	def rep(m):
		k = int(m.group(1))
		spec = m.group(2)
		v = a[k] if k < len(a) else na
		if spec:
			spec = spec.strip(", ")
			if spec.startswith("number"):
				p = spec[6:].strip(", ")
				if p == "percent":
					return tostring(v * 100, "#.##") + "%"
				if p == "integer":
					return tostring(v, "#")
				return tostring(v, p or None)
			if spec.startswith("date") or spec.startswith("time"):
				p = spec[4:].strip(", ")
				return format_time(v, p or "yyyy-MM-dd")
		return tostring(v)
	return re.sub(r"\{(\d+)((?:,[^}]*)?)\}", rep, fmt.replace("''", "\0")).replace("\0", "'")

def s_match(s, regex):
	m = re.search(regex, s or "")
	return m.group() if m else ""

def s_repeat(s, n, sep=""):
	return sep.join([s] * int(n))

def s_trim(s):
	return s.strip()

# ---------------------------------------------------------------- inputs

class Input:
	"""an input of the script: key (its group, title and inline, which
	stay when the script changes elsewhere), kind (int, float, bool,
	string, color, session, time, timeframe, symbol, source...), title,
	default value and the other arguments (options, minval, maxval, step,
	tooltip, group, inline)"""
	__slots__ = ("key", "kind", "title", "defval", "args")
	def __init__(self, key, kind, title, defval, args):
		self.key, self.kind, self.title, self.defval, self.args = key, kind, title, defval, args

ARGNAMES = {"any": ("defval", "title", "tooltip", "inline", "group"),
	"bool": ("defval", "title", "tooltip", "inline", "group", "confirm", "display"),
	"color": ("defval", "title", "tooltip", "inline", "group", "confirm", "display"),
	"source": ("defval", "title", "tooltip", "inline", "group", "display"),
	"time": ("defval", "title", "tooltip", "inline", "group", "confirm", "display"),
	"string": ("defval", "title", "options", "tooltip", "inline", "group", "confirm", "display"),
	"session": ("defval", "title", "options", "tooltip", "inline", "group", "confirm", "display"),
	"timeframe": ("defval", "title", "options", "tooltip", "inline", "group", "confirm", "display"),
	"symbol": ("defval", "title", "tooltip", "inline", "group", "confirm", "display"),
	"text_area": ("defval", "title", "tooltip", "group", "confirm", "display"),
	"int": ("defval", "title", "minval", "maxval", "step", "tooltip", "inline", "group", "confirm", "display"),
	"float": ("defval", "title", "minval", "maxval", "step", "tooltip", "inline", "group", "confirm", "display"),
	"price": ("defval", "title", "tooltip", "inline", "group", "confirm", "display")}

def mkinput(kind):
	names = ARGNAMES.get(kind, ARGNAMES["any"])
	def f(*a, _site=None, **k):
		args = dict(zip(names, a))
		if kind in ("int", "float") and len(a) > 2 and isinstance(a[2], (list, tuple)):	# input.int(1, "x", [1, 2, 3])
			args = dict(zip(("defval", "title", "options", "tooltip", "inline", "group", "confirm", "display"), a))
		args.update(k)
		spec = RT.specs.get(_site)
		if spec is None:
			defval = args.get("defval", na)
			title = args.get("title", "") or ""
			base = f"{args.get('group', '') or ''}|{title}|{args.get('inline', '') or ''}"
			key = base
			n = 1
			while key in RT.inputkeys:
				n += 1
				key = f"{base}#{n}"
			RT.inputkeys.add(key)
			spec = RT.specs[_site] = Input(key, "float" if kind == "price" else kind, title, defval, args)
		if kind == "source" or spec.key not in RT.inputs:
			return args.get("defval", na)
		return RT.inputs[spec.key]
	return f

# ---------------------------------------------------------------- ta

class _St:
	__slots__ = ("a", "b", "c", "d", "n")
	def __init__(self):
		self.a = None
		self.b = None
		self.c = None
		self.d = None
		self.n = 0

def _st(c, site):
	s = c.st.get(site)
	if s is None:
		s = c.st[site] = _St()
	return s

def _buf(s, n, x):
	"""push x into s.a, a deque of the last n values"""
	q = s.a
	if q is None or q.maxlen != n:
		q = s.a = deque(q or (), maxlen=n)
	q.append(x)
	return q

def ta_sma(c, site, src, length):
	s = _st(c, site)
	q = _buf(s, int(length), src)
	if len(q) < length or any(isna(x) for x in q):
		return na
	return sum(q) / length

def _rma(s, x, length, alpha):
	if s.b is None:
		s.b = []
	if s.c is None or isna(s.c):
		if isna(x):
			return na
		s.b.append(x)
		if len(s.b) < length:
			return na
		s.c = sum(s.b[-int(length):]) / length
		s.b = []
		return s.c
	if isna(x):
		return s.c
	s.c = alpha * x + (1 - alpha) * s.c
	return s.c

def ta_rma(c, site, src, length):
	return _rma(_st(c, site), src, length, 1 / length)

def ta_ema(c, site, src, length):
	return _rma(_st(c, site), src, length, 2 / (length + 1))

def ta_atr(c, site, length):
	return _rma(_st(c, site), RT.tr, length, 1 / length)

def ta_tr(c, site, handle_na=False):
	S, i = RT.S, RT.bar
	if i == 0:
		return S.h[i] - S.l[i] if handle_na else na
	return RT.tr

def ta_stdev(c, site, src, length, biased=True):
	s = _st(c, site)
	q = _buf(s, int(length), src)
	if len(q) < length or any(isna(x) for x in q):
		return na
	m = sum(q) / length
	d = length if biased else length - 1
	return math.sqrt(sum((x - m) ** 2 for x in q) / d)

def ta_change(c, site, src, length=1):
	s = _st(c, site)
	q = _buf(s, int(length) + 1, src)
	if len(q) <= length:
		return na if not isinstance(src, bool) else False
	old = q[0]
	if isinstance(src, bool):
		return src != old
	if isna(src) or isna(old):
		return na
	return src - old

def ta_barssince(c, site, cond):
	s = _st(c, site)
	if cond:
		s.c = RT.bar
	return na if s.c is None else RT.bar - s.c

def ta_valuewhen(c, site, cond, src, occurrence=0):
	s = _st(c, site)
	if s.b is None:
		s.b = deque(maxlen=int(occurrence) + 1)
	if cond:
		s.b.append(src)
	k = int(occurrence)
	return s.b[-1 - k] if len(s.b) > k else na

def _hl(c, site, a, b, src, fn):
	if b is None:
		length, src = a, src
	else:
		src, length = a, b
	s = _st(c, site)
	q = _buf(s, int(length), src)
	v = [x for x in q if not isna(x)]
	return fn(v) if v else na

def ta_highest(c, site, a, b=None):
	if b is None:
		return _hl(c, site, a, None, RT.S.h[RT.bar], max)
	return _hl(c, site, a, b, None, max)

def ta_lowest(c, site, a, b=None):
	if b is None:
		return _hl(c, site, a, None, RT.S.l[RT.bar], min)
	return _hl(c, site, a, b, None, min)

def _hlbars(c, site, a, b, dflt, hi):
	if b is None:
		src, length = dflt, a
	else:
		src, length = a, b
	s = _st(c, site)
	q = _buf(s, int(length), src)
	best, k = None, na
	for j, x in enumerate(reversed(q)):
		if isna(x):
			continue
		if best is None or (x > best if hi else x < best):
			best, k = x, j
	return na if best is None else -k

def ta_highestbars(c, site, a, b=None):
	return _hlbars(c, site, a, b, RT.S.h[RT.bar], True)

def ta_lowestbars(c, site, a, b=None):
	return _hlbars(c, site, a, b, RT.S.l[RT.bar], False)

def _pivot(c, site, a, b, cc, dflt, hi):
	if cc is None:
		src, left, right = dflt, a, b
	else:
		src, left, right = a, b, cc
	left, right = int(left), int(right)
	s = _st(c, site)
	q = _buf(s, left + right + 1, src)
	if len(q) < left + right + 1:
		return na
	v = q[left]
	if isna(v):
		return na
	for j, x in enumerate(q):
		if j == left:
			continue
		if isna(x):
			return na
		if (x >= v) if hi else (x <= v):
			return na
	return v

def ta_pivothigh(c, site, a, b, cc=None):
	return _pivot(c, site, a, b, cc, RT.S.h[RT.bar], True)

def ta_pivotlow(c, site, a, b, cc=None):
	return _pivot(c, site, a, b, cc, RT.S.l[RT.bar], False)

def ta_crossover(c, site, a, b):
	s = _st(c, site)
	pa, pb = s.c, s.d
	s.c, s.d = a, b
	return pa is not None and not isna(pa) and not isna(pb) and a > b and pa <= pb

def ta_crossunder(c, site, a, b):
	s = _st(c, site)
	pa, pb = s.c, s.d
	s.c, s.d = a, b
	return pa is not None and not isna(pa) and not isna(pb) and a < b and pa >= pb

def ta_cross(c, site, a, b):
	s = _st(c, site)
	pa, pb = s.c, s.d
	s.c, s.d = a, b
	return pa is not None and not isna(pa) and not isna(pb) and ((a > b and pa <= pb) or (a < b and pa >= pb))

def ta_cum(c, site, src):
	s = _st(c, site)
	s.c = (s.c or 0) + nz(src)
	return s.c

def ta_rsi(c, site, src, length):
	s = _st(c, site)
	if s.d is None:
		s.d = [_St(), _St(), None]
	prev = s.d[2]
	s.d[2] = src
	if prev is None or isna(prev) or isna(src):
		return na
	ch = src - prev
	up = _rma(s.d[0], max(ch, 0), length, 1 / length)
	dn = _rma(s.d[1], max(-ch, 0), length, 1 / length)
	if isna(up) or isna(dn):
		return na
	return 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)

def ta_wma(c, site, src, length):
	s = _st(c, site)
	q = _buf(s, int(length), src)
	if len(q) < length or any(isna(x) for x in q):
		return na
	w = range(1, len(q) + 1)
	return sum(x * k for x, k in zip(q, w)) / sum(w)

def math_sum(c, site, src, length):
	s = _st(c, site)
	q = _buf(s, int(length), src)
	if len(q) < length or any(isna(x) for x in q):
		return na
	return math.fsum(q)

def tf_change(c, site, tf):
	s = _st(c, site)
	t = RT.bartime(tf, RT.S.t[RT.bar])
	old = s.c
	s.c = t
	return old is not None and t != old

def fixnan(c, site, x):
	s = _st(c, site)
	if isna(x):
		return na if s.c is None else s.c
	s.c = x
	return x

# ---------------------------------------------------------------- request

class _Sec:
	__slots__ = ("S", "ctx", "vals", "n", "n0", "last", "_fn")

def _swap(fn, S, k, ctx):
	"""fn(ctx) on bar k of S, and back to the bar that was in context"""
	ns = RT.ns
	S0, i0 = RT.S, RT.bar
	setbar(ns, S, k)
	RT.depth += 1
	try:
		return fn(ctx)
	finally:
		RT.depth -= 1
		setbar(ns, S0, i0)

def _natuple(n):
	return na if not n else tuple([na] * n)

def request_security(c, site, symbol, timeframe, expression, gaps=False, lookahead=False, ignore_invalid_symbol=False,
		currency=None, calc_bars_count=None, _n=0, **_k):
	"""request.security: expression (a function of a Ctx) on the bars of
	timeframe; with lookahead the bar holding this one, without it the
	last one closed by the end of this bar (the one in progress on the last
	bar)"""
	S0, i = RT.S, RT.bar
	tf = timeframe
	sec0 = tfsecs(tf)
	cur = tfsecs(RT.tfp)
	if sec0 == cur:
		return expression(c.sub(site))
	s = c.st.get(site)
	if s is None:
		s = c.st[site] = _Sec()
		s.S = RT.htf(tf)
		s.ctx = Ctx()
		s.vals = []
		s.n = 0
		s.n0 = 0
		s.last = -2
	s._fn = expression
	H = s.S
	if H is None or not H.n:
		return _natuple(_n)
	t = S0.t[i]
	if sec0 < cur:	# a lower time frame: its last bar in this one
		a = bisect_left(H.t, t)
		b = bisect_left(H.t, S0.tc[i]) - 1
		if b < a:
			return _natuple(_n)
		_run(s, H, b, a)
		return s.vals[b - s.n0]
	j = H.find(t)
	if j < 0:
		return _natuple(_n)
	_run(s, H, j, None)
	if lookahead:
		k = j
	else:
		k = j if (S0.tc[i] >= H.tc[j] or i == S0.n - 1) else j - 1
	if gaps:
		changed = k != s.last
		s.last = k
		if not changed:
			return _natuple(_n)
	if k < s.n0:
		return _natuple(_n)
	return s.vals[k - s.n0]

def _run(s, H, j, start):
	if s.n == 0 and not s.vals:
		first = max(0, j - 5000) if start is None else start
		s.n = s.n0 = first
	if j < s.n0:
		return
	while s.n <= j:
		s.vals.append(_swap(s._fn, H, s.n, s.ctx))
		s.n += 1

def request_security_lower_tf(c, site, symbol, timeframe, expression, ignore_invalid_symbol=False, currency=None,
		ignore_invalid_timeframe=False, calc_bars_count=None, _n=0, **_k):
	"""request.security_lower_tf: the values of expression on the bars of
	timeframe inside this bar, as arrays"""
	S0, i = RT.S, RT.bar
	sec0 = tfsecs(timeframe)
	cur = tfsecs(RT.tfp)
	if sec0 >= cur:
		v = expression(c.sub(site))
		return tuple(PArray([x]) for x in v) if isinstance(v, tuple) and _n else PArray([v])
	s = c.st.get(site)
	if s is None:
		s = c.st[site] = _Sec()
		s.S = RT.htf(timeframe)
		s.ctx = Ctx()
		s.vals = []
		s.n = 0
		s.n0 = 0
		s.last = -2
	s._fn = expression
	H = s.S
	out = []
	if H is not None and H.n:
		a = bisect_left(H.t, S0.t[i])
		b = bisect_left(H.t, S0.tc[i])
		if b > a:
			if s.n == 0 and not s.vals:
				s.n = s.n0 = a
			if a > s.n:	# bars skipped: on from here
				s.vals = []
				s.n = s.n0 = a
			while s.n < b:
				s.vals.append(_swap(s._fn, H, s.n, s.ctx))
				s.n += 1
			out = s.vals[a - s.n0:b - s.n0]
			if len(s.vals) > 4000:
				drop = len(s.vals) - 2000
				del s.vals[:drop]
				s.n0 += drop
	if _n:
		cols = list(zip(*out)) if out else [()] * _n
		return tuple(PArray(col) for col in cols)
	return PArray(out)

# ---------------------------------------------------------------- drawings

def _p(k, name, a, i, dflt):
	return a[i] if len(a) > i else k.get(name, dflt)

class Line:
	__slots__ = ("x1", "y1", "x2", "y2", "xloc", "extend", "color", "style", "width", "alive")
	def __init__(self, x1, y1, x2, y2, xloc="bi", extend="n", color=None, style="solid", width=1):
		self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
		self.xloc, self.extend, self.color, self.style, self.width = xloc, extend, color, style, width
		self.alive = True

	def get_x1(self): return self.x1
	def get_x2(self): return self.x2
	def get_y1(self): return self.y1
	def get_y2(self): return self.y2
	def set_x1(self, x): self.x1 = x
	def set_x2(self, x): self.x2 = x
	def set_y1(self, y): self.y1 = y
	def set_y2(self, y): self.y2 = y
	def set_xy1(self, x, y): self.x1, self.y1 = x, y
	def set_xy2(self, x, y): self.x2, self.y2 = x, y
	def set_xloc(self, x1, x2, xloc): self.x1, self.x2, self.xloc = x1, x2, xloc
	def set_extend(self, e): self.extend = e
	def set_color(self, c): self.color = c
	def set_style(self, s): self.style = s
	def set_width(self, w): self.width = w
	def set_first_point(self, p): self.x1, self.y1 = (p.time if self.xloc == "bt" else p.index), p.price
	def set_second_point(self, p): self.x2, self.y2 = (p.time if self.xloc == "bt" else p.index), p.price

	def get_price(self, x):
		if self.x2 == self.x1:
			return self.y1
		return self.y1 + (self.y2 - self.y1) * (x - self.x1) / (self.x2 - self.x1)

	def delete(self):
		if self.alive:
			self.alive = False
			RT.gone("line")

	def copy(self):
		l = Line(self.x1, self.y1, self.x2, self.y2, self.xloc, self.extend, self.color, self.style, self.width)
		return RT.add("line", l)

def line_new(*a, **k):
	if a and isinstance(a[0], Point):	# line.new(first_point, second_point, ...)
		p1, p2 = a[0], a[1]
		xloc = k.get("xloc", a[2] if len(a) > 2 else "bi")
		x1 = p1.time if xloc == "bt" else p1.index
		x2 = p2.time if xloc == "bt" else p2.index
		a = (x1, p1.price, x2, p2.price) + tuple(a[2:])
	l = Line(a[0] if len(a) > 0 else k["x1"], _p(k, "y1", a, 1, na), _p(k, "x2", a, 2, na), _p(k, "y2", a, 3, na),
		_p(k, "xloc", a, 4, "bi"), _p(k, "extend", a, 5, "n"), _p(k, "color", a, 6, COLOR_BLUE),
		_p(k, "style", a, 7, "solid"), _p(k, "width", a, 8, 1))
	return RT.add("line", l)

class Label:
	__slots__ = ("x", "y", "text", "xloc", "yloc", "color", "style", "textcolor", "size", "textalign", "tooltip",
		"font", "formatting", "alive")
	def __init__(self, x, y, text="", xloc="bi", yloc="price", color=None, style="label_down", textcolor=None,
			size="normal", textalign="center", tooltip="", font="default", formatting="none"):
		self.x, self.y, self.text, self.xloc, self.yloc = x, y, text, xloc, yloc
		self.color, self.style, self.textcolor, self.size = color, style, textcolor, size
		self.textalign, self.tooltip, self.font, self.formatting = textalign, tooltip, font, formatting
		self.alive = True

	def get_x(self): return self.x
	def get_y(self): return self.y
	def get_text(self): return self.text
	def set_x(self, x): self.x = x
	def set_y(self, y): self.y = y
	def set_xy(self, x, y): self.x, self.y = x, y
	def set_text(self, t): self.text = t
	def set_color(self, c): self.color = c
	def set_textcolor(self, c): self.textcolor = c
	def set_style(self, s): self.style = s
	def set_size(self, s): self.size = s
	def set_textalign(self, a): self.textalign = a
	def set_tooltip(self, t): self.tooltip = t
	def set_xloc(self, x, xloc): self.x, self.xloc = x, xloc
	def set_yloc(self, y): self.yloc = y
	def set_text_font_family(self, f): self.font = f
	def set_text_formatting(self, f): self.formatting = f
	def set_point(self, p): self.x, self.y = (p.time if self.xloc == "bt" else p.index), p.price

	def delete(self):
		if self.alive:
			self.alive = False
			RT.gone("label")

	def copy(self):
		l = Label(self.x, self.y, self.text, self.xloc, self.yloc, self.color, self.style, self.textcolor, self.size,
			self.textalign, self.tooltip, self.font, self.formatting)
		return RT.add("label", l)

LABELARGS = ("x", "y", "text", "xloc", "yloc", "color", "style", "textcolor", "size", "textalign", "tooltip",
	"text_font_family", "force_overlay", "text_formatting")

def label_new(*a, **k):
	if a and isinstance(a[0], Point):
		p = a[0]
		xloc = k.get("xloc", "bi")
		a = (p.time if xloc == "bt" else p.index, p.price) + tuple(a[1:])
	v = dict(zip(LABELARGS, a))
	v.update(k)
	l = Label(v.get("x"), v.get("y", na), v.get("text", ""), v.get("xloc", "bi"), v.get("yloc", "price"),
		v.get("color", COLOR_BLUE), v.get("style", "label_down"), v.get("textcolor", COLOR_BLACK),
		v.get("size", "normal"), v.get("textalign", "center"), v.get("tooltip", ""),
		v.get("text_font_family", "default"), v.get("text_formatting", "none"))
	return RT.add("label", l)

class Box:
	__slots__ = ("left", "top", "right", "bottom", "border_color", "border_width", "border_style", "extend", "xloc",
		"bgcolor", "text", "text_size", "text_color", "text_halign", "text_valign", "text_wrap", "font", "formatting",
		"alive")
	def __init__(self, **v):
		for f in self.__slots__:
			setattr(self, f, v.get(f))
		self.alive = True

	def get_left(self): return self.left
	def get_top(self): return self.top
	def get_right(self): return self.right
	def get_bottom(self): return self.bottom
	def set_left(self, x): self.left = x
	def set_top(self, y): self.top = y
	def set_right(self, x): self.right = x
	def set_bottom(self, y): self.bottom = y
	def set_lefttop(self, x, y): self.left, self.top = x, y
	def set_rightbottom(self, x, y): self.right, self.bottom = x, y
	def set_top_left_point(self, p): self.left, self.top = (p.time if self.xloc == "bt" else p.index), p.price
	def set_bottom_right_point(self, p): self.right, self.bottom = (p.time if self.xloc == "bt" else p.index), p.price
	def set_border_color(self, c): self.border_color = c
	def set_border_width(self, w): self.border_width = w
	def set_border_style(self, s): self.border_style = s
	def set_bgcolor(self, c): self.bgcolor = c
	def set_extend(self, e): self.extend = e
	def set_text(self, t): self.text = t
	def set_text_size(self, s): self.text_size = s
	def set_text_color(self, c): self.text_color = c
	def set_text_halign(self, a): self.text_halign = a
	def set_text_valign(self, a): self.text_valign = a
	def set_text_wrap(self, w): self.text_wrap = w
	def set_text_font_family(self, f): self.font = f
	def set_text_formatting(self, f): self.formatting = f
	def set_xloc(self, left, right, xloc): self.left, self.right, self.xloc = left, right, xloc

	def delete(self):
		if self.alive:
			self.alive = False
			RT.gone("box")

	def copy(self):
		b = Box(**{f: getattr(self, f) for f in self.__slots__})
		return RT.add("box", b)

BOXARGS = ("left", "top", "right", "bottom", "border_color", "border_width", "border_style", "extend", "xloc",
	"bgcolor", "text", "text_size", "text_color", "text_halign", "text_valign", "text_wrap", "text_font_family",
	"force_overlay", "text_formatting")

def box_new(*a, **k):
	if a and isinstance(a[0], Point):
		p1, p2 = a[0], a[1]
		xloc = k.get("xloc", "bi")
		a = (p1.time if xloc == "bt" else p1.index, p1.price, p2.time if xloc == "bt" else p2.index, p2.price) + tuple(a[2:])
	v = dict(zip(BOXARGS, a))
	v.update(k)
	b = Box(left=v.get("left"), top=v.get("top"), right=v.get("right"), bottom=v.get("bottom"),
		border_color=v.get("border_color", COLOR_BLUE), border_width=v.get("border_width", 1),
		border_style=v.get("border_style", "solid"), extend=v.get("extend", "n"), xloc=v.get("xloc", "bi"),
		bgcolor=v.get("bgcolor", COLOR_BLUE), text=v.get("text", ""), text_size=v.get("text_size", "auto"),
		text_color=v.get("text_color", COLOR_BLACK), text_halign=v.get("text_halign", "center"),
		text_valign=v.get("text_valign", "center"), text_wrap=v.get("text_wrap", "none"),
		font=v.get("text_font_family", "default"), formatting=v.get("text_formatting", "none"))
	return RT.add("box", b)

class Table:
	__slots__ = ("position", "columns", "rows", "bgcolor", "frame_color", "frame_width", "border_color",
		"border_width", "cells", "alive")
	def __init__(self, position, columns, rows, bgcolor=None, frame_color=None, frame_width=0, border_color=None,
			border_width=0):
		self.position, self.columns, self.rows = position, columns, rows
		self.bgcolor, self.frame_color, self.frame_width = bgcolor, frame_color, frame_width
		self.border_color, self.border_width = border_color, border_width
		self.cells = {}
		self.alive = True

	def cell(self, column, row, text="", width=0, height=0, text_color=None, text_halign="center",
			text_valign="center", text_size="normal", bgcolor=None, tooltip="", text_font_family="default",
			text_formatting="none"):
		self.cells[(int(column), int(row))] = {"text": text, "text_color": text_color, "text_halign": text_halign,
			"text_valign": text_valign, "text_size": text_size, "bgcolor": bgcolor, "formatting": text_formatting,
			"width": width, "height": height}

	def _set(self, column, row, key, v):
		c = self.cells.setdefault((int(column), int(row)), {"text": "", "text_color": None, "text_halign": "center",
			"text_valign": "center", "text_size": "normal", "bgcolor": None, "formatting": "none", "width": 0, "height": 0})
		c[key] = v

	def cell_set_text(self, c, r, v): self._set(c, r, "text", v)
	def cell_set_bgcolor(self, c, r, v): self._set(c, r, "bgcolor", v)
	def cell_set_text_color(self, c, r, v): self._set(c, r, "text_color", v)
	def cell_set_text_size(self, c, r, v): self._set(c, r, "text_size", v)
	def cell_set_text_halign(self, c, r, v): self._set(c, r, "text_halign", v)
	def cell_set_text_valign(self, c, r, v): self._set(c, r, "text_valign", v)
	def cell_set_text_formatting(self, c, r, v): self._set(c, r, "formatting", v)
	def cell_set_tooltip(self, c, r, v): pass
	def cell_set_width(self, c, r, v): self._set(c, r, "width", v)
	def cell_set_height(self, c, r, v): self._set(c, r, "height", v)
	def set_position(self, p): self.position = p
	def set_bgcolor(self, c): self.bgcolor = c
	def set_frame_color(self, c): self.frame_color = c
	def set_frame_width(self, w): self.frame_width = w
	def set_border_color(self, c): self.border_color = c
	def set_border_width(self, w): self.border_width = w
	def merge_cells(self, *a): pass

	def clear(self, c0=0, r0=0, c1=None, r1=None):
		c1 = c0 if c1 is None else c1
		r1 = r0 if r1 is None else r1
		for k in list(self.cells):
			if c0 <= k[0] <= c1 and r0 <= k[1] <= r1:
				del self.cells[k]

	def delete(self):
		self.alive = False

def table_new(position, columns, rows, bgcolor=None, frame_color=None, frame_width=0, border_color=None,
		border_width=0, force_overlay=False):
	t = Table(position, columns, rows, bgcolor, frame_color, frame_width, border_color, border_width)
	RT.objs["table"].append(t)
	return t

class Point:
	__slots__ = ("time", "index", "price")
	def __init__(self, time=na, index=na, price=na):
		self.time, self.index, self.price = time, index, price
	def copy(self):
		return Point(self.time, self.index, self.price)

def point_from_index(index, price):
	S = RT.S
	t = S.t[index] if 0 <= index < S.n else na
	return Point(t, index, price)

def point_from_time(time, price):
	return Point(time, na, price)

def point_now(price=None):
	return Point(RT.S.t[RT.bar], RT.bar, RT.S.c[RT.bar] if price is None else price)

def point_new(time=na, index=na, price=na):
	return Point(time, index, price)

class Linefill:
	__slots__ = ("l1", "l2", "color", "alive")
	def __init__(self, l1, l2, color):
		self.l1, self.l2, self.color, self.alive = l1, l2, color, True
	def set_color(self, c): self.color = c
	def get_line1(self): return self.l1
	def get_line2(self): return self.l2
	def delete(self):
		if self.alive:
			self.alive = False
			RT.gone("linefill")

def linefill_new(l1, l2, color):
	return RT.add("linefill", Linefill(l1, l2, color))

# plots: per call site, {bar: values}

def _plot(kind):
	def f(c, site, *a, **k):
		if RT.depth:
			return na
		d = RT.plots.get(site)
		if d is None:
			d = RT.plots[site] = (kind, {}, k.get("title", a[1] if len(a) > 1 and kind != "bgcolor" else ""))
		v = a[0] if a else k.get("series", k.get("color"))
		d[1][RT.bar] = (v, a, k)
		return site
	return f

COLOR_BLUE = hexcolor(COLORS["blue"])
COLOR_BLACK = hexcolor(COLORS["black"])

def indicator(*a, **k):
	RT.title = a[0] if a else k.get("title", "")
	RT.overlay = k.get("overlay", a[2] if len(a) > 2 else False)
	for kind in ("line", "label", "box", "polyline"):
		n = k.get(f"max_{kind}s_count")
		if n is not None:
			RT.limits[kind] = int(n)

def runtime_error(msg):
	raise PineRuntimeError(msg)

def log_(*a, **k):
	return na

# ---------------------------------------------------------------- the names

def builtins():
	"""{Pine name: value} of the functions and constants, and the set of
	those that take the call site state (c, site, ...)"""
	F = {
		"na": isna, "nz": nz, "int": toint, "float": tofloat, "bool": ident, "string": ident, "color": ident,
		"line": ident, "label": ident, "box": ident, "table": ident, "linefill": ident, "polyline": ident,
		"time": time_, "time_close": time_close_, "timestamp": timestamp,
		"hour": _tfield(3), "minute": _tfield(4), "second": _tfield(5), "dayofweek": _tfield(6),
		"dayofmonth": _tfield(2), "month": _tfield(1), "year": _tfield(0), "weekofyear": weekofyear,
		"indicator": indicator, "strategy": indicator, "library": indicator,
		"alert": noop, "alertcondition": noop, "max_bars_back": noop, "barcolor": noop,
		"runtime.error": runtime_error,
		"strategy.entry": noop, "strategy.exit": noop, "strategy.close": noop, "strategy.close_all": noop,
		"strategy.cancel": noop, "strategy.cancel_all": noop, "strategy.order": noop,
		"ticker.modify": ident, "ticker.new": lambda prefix, ticker, *a, **k: f"{prefix}:{ticker}",
		"ticker.standard": ident, "ticker.heikinashi": ident, "ticker.inherit": ident, "log.info": log_, "log.warning": log_, "log.error": log_,
		"color.new": color_new, "color.rgb": rgb, "color.r": color_r, "color.g": color_g, "color.b": color_b,
		"color.t": color_t, "color.from_gradient": from_gradient,
		"math.max": mmax, "math.min": mmin, "math.avg": mavg, "math.abs": mabs, "math.round": mround,
		"math.floor": mfloor, "math.ceil": mceil, "math.sign": msign, "math.sqrt": _f1(math.sqrt),
		"math.pow": lambda a, b: na if isna(a) or isna(b) else _f1(math.pow)(a, b), "math.log": _f1(math.log),
		"math.log10": _f1(math.log10), "math.exp": _f1(math.exp), "math.sin": _f1(math.sin), "math.cos": _f1(math.cos),
		"math.tan": _f1(math.tan), "math.atan": _f1(math.atan), "math.round_to_mintick": round_to_mintick,
		"math.todegrees": _f1(math.degrees), "math.toradians": _f1(math.radians),
		"str.tostring": tostring, "str.tonumber": tonumber, "str.substring": substring, "str.contains": s_contains,
		"str.startswith": lambda s, x: not isna(s) and s.startswith(x),
		"str.endswith": lambda s, x: not isna(s) and s.endswith(x),
		"str.upper": lambda s: na if isna(s) else s.upper(), "str.lower": lambda s: na if isna(s) else s.lower(),
		"str.replace": s_replace, "str.replace_all": lambda s, a, b: na if isna(s) else s.replace(a, b),
		"str.split": s_split, "str.length": lambda s: 0 if isna(s) else len(s), "str.pos": s_pos,
		"str.format": s_format, "str.format_time": format_time, "str.match": s_match, "str.repeat": s_repeat,
		"str.trim": s_trim,
		"timeframe.in_seconds": tfsecs, "timeframe.from_seconds": from_seconds,
		"array.new": array_new, "array.from": array_from, "map.new": map_new,
		"line.new": line_new, "label.new": label_new, "box.new": box_new, "table.new": table_new,
		"linefill.new": linefill_new, "chart.point.new": point_new, "chart.point.from_index": point_from_index,
		"chart.point.from_time": point_from_time, "chart.point.now": point_now,
	}
	for t in ("float", "int", "bool", "string", "color", "line", "label", "box", "table", "linefill"):
		F["array.new_" + t] = array_newof(t)
	for k in ("int", "float", "bool", "string", "color", "session", "time", "timeframe", "symbol", "source",
			"text_area", "price", "enum"):
		F["input." + k] = mkinput(k)
	F["input"] = mkinput("any")
	S = {
		"ta.sma": ta_sma, "ta.ema": ta_ema, "ta.rma": ta_rma, "ta.atr": ta_atr, "ta.tr": ta_tr,
		"ta.stdev": ta_stdev, "ta.change": ta_change, "ta.barssince": ta_barssince, "ta.valuewhen": ta_valuewhen,
		"ta.highest": ta_highest, "ta.lowest": ta_lowest, "ta.highestbars": ta_highestbars,
		"ta.lowestbars": ta_lowestbars, "ta.pivothigh": ta_pivothigh, "ta.pivotlow": ta_pivotlow,
		"ta.crossover": ta_crossover, "ta.crossunder": ta_crossunder, "ta.cross": ta_cross, "ta.cum": ta_cum,
		"ta.rsi": ta_rsi, "ta.wma": ta_wma, "math.sum": math_sum, "timeframe.change": tf_change, "fixnan": fixnan,
		"request.security": request_security, "request.security_lower_tf": request_security_lower_tf,
		"plot": _plot("plot"), "plotshape": _plot("shape"), "plotchar": _plot("char"), "bgcolor": _plot("bgcolor"),
		"hline": _plot("hline"), "fill": _plot("fill"), "plotcandle": _plot("candle"), "plotbar": _plot("bar"),
		"plotarrow": _plot("arrow"),
	}
	F.update(S)
	K = {}
	for name, h in COLORS.items():
		K["color." + name] = hexcolor(h)
	for s in ("solid", "dashed", "dotted", "arrow_left", "arrow_right", "arrow_both"):
		K["line.style_" + s] = s
	for s in ("none", "xcross", "cross", "triangleup", "triangledown", "flag", "circle", "arrowup", "arrowdown",
			"label_up", "label_down", "label_left", "label_right", "label_lower_left", "label_lower_right",
			"label_upper_left", "label_upper_right", "label_center", "square", "diamond", "text_outline"):
		K["label.style_" + s] = s
	K.update({"extend.none": "n", "extend.right": "r", "extend.left": "l", "extend.both": "b",
		"xloc.bar_index": "bi", "xloc.bar_time": "bt", "yloc.price": "price", "yloc.abovebar": "abovebar",
		"yloc.belowbar": "belowbar"})
	for s in ("auto", "tiny", "small", "normal", "large", "huge"):
		K["size." + s] = s
	for s in ("top_left", "top_center", "top_right", "middle_left", "middle_center", "middle_right", "bottom_left",
			"bottom_center", "bottom_right"):
		K["position." + s] = s
	for s in ("left", "center", "right", "top", "bottom"):
		K["text.align_" + s] = s
	K.update({"text.wrap_auto": "auto", "text.wrap_none": "none", "text.format_bold": "bold",
		"text.format_italic": "italic", "text.format_none": "none", "font.family_default": "default",
		"font.family_monospace": "monospace"})
	for s in ("xcross", "cross", "triangleup", "triangledown", "flag", "circle", "arrowup", "arrowdown", "labelup",
			"labeldown", "square", "diamond"):
		K["shape." + s] = s
	K.update({"location.abovebar": "abovebar", "location.belowbar": "belowbar", "location.top": "top",
		"location.bottom": "bottom", "location.absolute": "absolute"})
	K.update({"barmerge.lookahead_on": True, "barmerge.lookahead_off": False, "barmerge.gaps_on": True,
		"barmerge.gaps_off": False})
	K.update({"alert.freq_once_per_bar": "bar", "alert.freq_once_per_bar_close": "close", "alert.freq_all": "all"})
	for i, d in enumerate(("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"), 1):
		K["dayofweek." + d] = i
	K.update({"format.mintick": "mintick", "format.percent": "percent", "format.volume": "volume",
		"format.price": "price", "format.inherit": "inherit"})
	for s in ("line", "linebr", "stepline", "stepline_diamond", "histogram", "cross", "area", "areabr", "columns",
			"circles"):
		K["plot.style_" + s] = s
	K.update({"hline.style_solid": "solid", "hline.style_dashed": "dashed", "hline.style_dotted": "dotted"})
	K.update({"display.all": "all", "display.none": "none", "display.data_window": "dw", "display.status_line": "sl",
		"display.pane": "pane", "display.price_scale": "ps"})
	K.update({"math.pi": math.pi, "math.e": math.e, "math.phi": (1 + 5 ** 0.5) / 2, "session.regular": "regular",
		"session.extended": "extended", "order.ascending": "ascending", "order.descending": "descending",
		"currency.USD": "USD", "currency.EUR": "EUR", "scale.right": "right", "scale.left": "left",
		"scale.none": "none", "adjustment.none": "none", "barmerge.gaps": False,
		"settlement_as_close.on": "on", "settlement_as_close.off": "off", "settlement_as_close.inherit": "inherit",
		"strategy.long": "long", "strategy.short": "short", "strategy.fixed": "fixed", "strategy.cash": "cash",
		"strategy.percent_of_equity": "percent", "chart.bg_color": hexcolor("#FFFFFF"),
		"chart.fg_color": hexcolor("#131722")})
	D = {
		"barstate.isfirst": "_RT.isfirst", "barstate.islast": "_RT.islast", "barstate.isconfirmed": "True",
		"barstate.isnew": "True", "barstate.isrealtime": "False", "barstate.ishistory": "True",
		"barstate.islastconfirmedhistory": "_RT.islast",
		"timeframe.period": "_RT.tfp", "timeframe.main_period": "_RT.chart", "timeframe.multiplier": "_RT.multiplier",
		"timeframe.isminutes": "_RT.isminutes", "timeframe.isseconds": "_RT.isseconds",
		"timeframe.isdaily": "_RT.isdaily", "timeframe.isweekly": "_RT.isweekly",
		"timeframe.ismonthly": "_RT.ismonthly", "timeframe.isintraday": "_RT.isintraday",
		"timeframe.isdwm": "_RT.isdwm", "timeframe.isticks": "False", "ta.tr": "_RT.tr",
		"syminfo.ticker": "_RT.sym['ticker']", "syminfo.tickerid": "_RT.sym['tickerid']",
		"syminfo.root": "_RT.sym['root']", "syminfo.prefix": "_RT.sym['prefix']",
		"syminfo.description": "_RT.sym['description']", "syminfo.type": "_RT.sym['type']",
		"syminfo.mintick": "_RT.mintick", "syminfo.pointvalue": "_RT.sym['pointvalue']",
		"syminfo.timezone": "_RT.tz", "syminfo.session": "'regular'", "syminfo.currency": "'USD'",
		"syminfo.basecurrency": "''", "syminfo.main_tickerid": "_RT.sym['tickerid']",
		"chart.is_standard": "True", "strategy.position_size": "0", "strategy.position_avg_price": "_na",
		"strategy.equity": "0", "strategy.netprofit": "0", "strategy.opentrades": "0", "strategy.closedtrades": "0", "chart.left_visible_bar_time": "_RT.S.t[0]",
		"chart.right_visible_bar_time": "_RT.S.t[-1]",
		"line.all": "_RT.all('line')", "label.all": "_RT.all('label')", "box.all": "_RT.all('box')",
		"table.all": "_RT.all('table')",
	}
	return F, S, K, D

def _all(kind):
	return PArray([o for o in RT.objs[kind] if o.alive], kind)

RT.all = _all
RT.mintick = 0.25
RT.sym = {}
