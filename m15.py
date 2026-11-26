#
# m15 data: the 15 minute candles of a market, imported from CSV files
# exported from TradingView (time,open,high,low,close,... with the time in
# seconds since 1970, UTC), kept in the journal compressed, in files of
# at most about MAXFILE bytes named after the trading day of their first
# candle: MNQ-260102.m15.csv.gz. Files named otherwise (from before) are
# renamed so, and plain ones compressed. What is drawn on the chart of a day or week is kept
# in DRAWDIR, a file per day (d261117.drw) or week (w261116.drw). A file
# imported later adds only the candles after the last one kept (and before
# the first one), so files that overlap don't make duplicates.
#
# Times are taken to New York's clock, as the futures sessions are: a
# trading day D goes from 18:00 of the day before to 17:00 of D, so Sunday
# evening is part of Monday, and a week from Sunday 18:00 to Friday 17:00.
# Its profile is the same as that of a week capture (weekprof.py): points
# (t, v), t in days from Monday 00:00 and v from 0 (its low) to 1 (its
# high). A day's profile is like it with t in hours from the day's midnight
# (-6 is 18:00 the day before). No widgets here.
#
import csv
import glob
import re
import gzip
import json
import io
import os
import zipfile
from datetime import date, datetime, timedelta, timezone

import numpy as np

import weekprof

EXT = ".m15.csv.gz"
OLDEXT = ".m15.csv"	# kept plain, before: compressed when found
MAXFILE = 512 * 1024	# a data file is not made larger than this, compressed: about a year and a half of m15
MAXLOW = 2 * 1024 * 1024	# nor one of a lower time frame: about four months of m1
DAILY, WEEKLY, MONTHLY = 1440, 10080, 43200	# the time frames of days, weeks and months, as minutes
TFS = [1, 3, 5, 15, 30, 60, 240, DAILY, WEEKLY, MONTHLY]	# the time frames charts are drawn in, minutes
PERIODS = {DAILY: 130, WEEKLY: 104, MONTHLY: 120}	# the candles a chart of days, weeks or months shows

def tfname(tf):
	"""m1, m15, h1, h4, D, W, M"""
	if tf in PERIODS:
		return {DAILY: "D", WEEKLY: "W", MONTHLY: "M"}[tf]
	return f"h{tf // 60}" if tf >= 60 and tf % 60 == 0 else f"m{tf}"

def periodkeys(dayno, tf):
	"""the day (D), week (W) or month (M) of each trading day of array dayno, as numbers"""
	dayno = np.asarray(dayno, dtype=np.int64)
	if tf == DAILY:
		return dayno
	if tf == WEEKLY:
		return (dayno - 4) // 7	# weeks from Monday
	return dayno.astype("datetime64[D]").astype("datetime64[M]").astype(np.int64)

def periodlast(key, tf):
	"""the last trading day (dayno) of the periods key of tf"""
	key = np.asarray(key, dtype=np.int64)
	if tf == DAILY:
		return key
	if tf == WEEKLY:
		return key * 7 + 4 + 4	# its Friday
	last = (key + 1).astype("datetime64[M]").astype("datetime64[D]").astype(np.int64) - 1
	wd = (last + 3) % 7	# 0 Monday
	return last - np.where(wd == 5, 1, np.where(wd == 6, 2, 0))

def daystart(dayno):
	"""the UTC seconds when trading days dayno (an array) start: 18:00 New York the day before"""
	wall = np.asarray(dayno, dtype=np.int64) * 86400 + DAYSTART * 3600
	return wall - nyoffsets(wall)

def dayend(dayno):
	wall = np.asarray(dayno, dtype=np.int64) * 86400 + DAYEND * 3600
	return wall - nyoffsets(wall)

def extof(tf):
	return f".{tfname(tf)}.csv.gz"
DRAWDIR = "m15draw"
TICK = 0.25	# the price step offsets are rounded to
ROLLMIN = 20	# candles in common it takes to find the offsets
ROLLTOL = 0.5	# how far the offset of a day may wander before it is a new one
HEADER = ["time", "open", "high", "low", "close"]
DAYSTART = -6	# hours from midnight a trading day starts at: 18:00 the day before
DAYEND = 17		# and ends at, 17:00
WEEKSWING = weekprof.SWING	# the smallest swing of a profile, as a part of the range
DAYSWING = 0.25

# sessions: name, start and end in hours from the day's midnight (New York),
# color; the times of the ICTlevels indicator (US hours)
SESSIONS = [
	("Asia", -4.0, 0.0, "#f23645"),
	("London", 2.0, 5.0, "#089981"),
	("NY AM", 7.0, 11.5, "#2962ff"),
]

EPOCH = date(1970, 1, 1)

def price(x):
	"""a price as the charts write it: 27312.75, 26659"""
	return f"{x:.2f}".rstrip("0").rstrip(".")

try:
	from zoneinfo import ZoneInfo
	NY = ZoneInfo("America/New_York")
except Exception:	# no time zone data: US Eastern rules by hand
	NY = None

def nyoffset(t):
	"""seconds to add to UTC time t for New York's clock"""
	if NY is not None:
		return int(datetime.fromtimestamp(int(t), NY).utcoffset().total_seconds())
	d = datetime.fromtimestamp(int(t), timezone.utc)
	y = d.year
	def nthsunday(month, n):
		first = date(y, month, 1)
		return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))
	start = datetime.combine(nthsunday(3, 2), datetime.min.time(), timezone.utc) + timedelta(hours=7)
	end = datetime.combine(nthsunday(11, 1), datetime.min.time(), timezone.utc) + timedelta(hours=6)
	return -4 * 3600 if start <= d < end else -5 * 3600

def parsetime(s):
	"""seconds since 1970 UTC of a time as TradingView writes it: a number,
	or an ISO date with its offset"""
	s = s.strip()
	try:
		return int(float(s))
	except ValueError:
		pass
	d = datetime.fromisoformat(s.replace("Z", "+00:00"))
	if d.tzinfo is None:
		d = d.replace(tzinfo=timezone.utc)
	return int(d.timestamp())

TIMENAMES = ("time", "time_utc", "time_utc_close", "time_close", "date", "datetime")

def readtext(path):
	"""the text of the CSV at path: plain, gzipped, or the first CSV in a zip"""
	if path.lower().endswith(".gz"):
		with gzip.open(path, "rt", encoding="utf-8-sig") as f:
			return f.read()
	if zipfile.is_zipfile(path):
		with zipfile.ZipFile(path) as z:
			names = [n for n in z.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX")]
			if not names:
				raise ValueError(f"no CSV file in {os.path.basename(path)}")
			return z.read(names[0]).decode("utf-8-sig")
	with open(path, encoding="utf-8-sig") as f:
		return f.read()

def readrows(path):
	"""the candles in the CSV at path (see readtext), sorted by time: an
	array of rows [t, o, h, l, c], t the start of the candle in seconds since
	1970 (UTC). Columns are taken by name (time, open, high, low, close; the
	first of each), separated by commas or semicolons; the time is a number
	or a date and time in UTC, and when its column says close
	(time_utc_close) it is the end of the candle"""
	text = readtext(path)
	nl = text.find("\n")
	first = text[:nl if nl >= 0 else len(text)]
	sep = ";" if first.count(";") > first.count(",") else ","
	head = [h.strip().lower() for h in first.split(sep)]
	tcol = next((i for i, h in enumerate(head) if h in TIMENAMES), None)
	try:
		cols = [head.index(h) for h in HEADER[1:]]
	except ValueError:
		cols = None
	if tcol is None or cols is None:
		raise ValueError(f"{os.path.basename(path)} has no {', '.join(HEADER)} columns")
	closing = "close" in head[tcol]
	try:	# at once, with numpy
		px = np.loadtxt(io.StringIO(text), delimiter=sep, skiprows=1, usecols=cols, ndmin=2, dtype=float)
		try:
			t = np.loadtxt(io.StringIO(text), delimiter=sep, skiprows=1, usecols=(tcol,), ndmin=1, dtype=float).astype(np.int64)
		except ValueError:
			t = np.loadtxt(io.StringIO(text), delimiter=sep, skiprows=1, usecols=(tcol,), ndmin=1,
				dtype="datetime64[s]").astype(np.int64)
		a = np.column_stack([t.astype(float), px])
	except ValueError:	# line by line: dates with their offset
		rows = []
		for row in csv.reader(io.StringIO(text), delimiter=sep):
			try:
				rows.append([parsetime(row[tcol])] + [float(row[i]) for i in cols])
			except (ValueError, IndexError):
				continue
		a = np.array(rows[1:] if rows and not str(rows[0][0]).isdigit() else rows, dtype=float).reshape(-1, 5)
	a = a[np.unique(a[:, 0], return_index=True)[1]]	# sorted, the first of each time
	if closing and len(a):
		a[:, 0] -= tfof(a) * 60
	return a

def tfof(rows):
	"""the time frame of candles rows, in minutes: the most common step"""
	if len(rows) < 2:
		return 15
	d = np.diff(np.asarray(rows)[:2000, 0].astype(np.int64))
	d = d[d > 0]
	if not len(d):
		return 15
	v, n = np.unique(d, return_counts=True)
	return max(1, int(v[n.argmax()]) // 60)

def resample(rows, tf):
	"""candles rows in candles of tf minutes, from 18:00 New York"""
	a = np.asarray(rows, dtype=float).reshape(-1, 5)
	if not len(a):
		return a
	t = a[:, 0].astype(np.int64)
	wall = t + nyoffsets(t)
	k = (wall - DAYSTART * 3600) // (tf * 60)
	starts = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
	out = np.empty((len(starts), 5))
	out[:, 0] = t[starts] - (wall[starts] - DAYSTART * 3600) % (tf * 60)	# the start of the candle
	out[:, 1] = a[starts, 1]
	out[:, 2] = np.maximum.reduceat(a[:, 2], starts)
	out[:, 3] = np.minimum.reduceat(a[:, 3], starts)
	out[:, 4] = a[np.r_[starts[1:] - 1, len(a) - 1], 4]
	return out

def nyoffsets(t):
	"""nyoffset of each time of array t"""
	k, inv = np.unique(t // 3600, return_inverse=True)
	return np.array([nyoffset(int(x) * 3600) for x in k], dtype=np.int64)[inv]

def symbolof(path):
	"""the symbol in a file name: MNQ for MNQ.m15.csv.zip"""
	b = os.path.basename(path)
	return b.split(".")[0].split("_")[0] or "data"

def dayof(t):
	"""the trading day (New York) of the candle at UTC time t"""
	return EPOCH + timedelta(days=(int(t) + nyoffset(t) - DAYSTART * 3600) // 86400)

def filename(symbol, t, tf=15):
	"""the name of a data file of symbol whose first candle is at time t"""
	return f"{symbol}-{dayof(t):%y%m%d}{extof(tf)}"

def symbolin(name):
	"""the symbol of a data file name: MNQ for MNQ-260102.m15.csv.gz or MNQ.m15.csv"""
	b = re.sub(r"\.[mh]\d+\.csv(\.gz)?$", "", name)
	return re.sub(r"-\d{6}$", "", b) or "data"

def lowtfs(dir):
	"""the time frames under m15 with data in journal dir"""
	out = set()
	for p in glob.glob(os.path.join(glob.escape(dir), "*.m*.csv.gz")):
		m = re.search(r"\.m(\d+)\.csv\.gz$", p)
		if m and int(m.group(1)) < 15:
			out.add(int(m.group(1)))
	return sorted(out)

def storeof(dir, tf=15):
	"""the data files of time frame tf in journal dir, in order; plain ones
	are compressed and those not named after their first day renamed so first"""
	esc = glob.escape(dir)
	ext = extof(tf)
	for p in sorted(glob.glob(os.path.join(esc, "*" + ext[:-3]))):
		rows = readrows(p)
		if len(rows):
			writerows(os.path.join(dir, filename(symbolin(os.path.basename(p)), rows[0][0], tf)), rows)
		os.remove(p)
	out = []
	for p in sorted(glob.glob(os.path.join(esc, "*" + ext))):
		rows = readrows(p)
		if not len(rows):
			continue
		want = os.path.join(dir, filename(symbolin(os.path.basename(p)), rows[0][0], tf))
		if want != p and not os.path.exists(want):
			os.rename(p, want)
			p = want
		out.append((rows[0][0], p, rows))
	return [(p, rows) for _, p, rows in sorted(out, key=lambda x: x[0])]

def writerows(dest, rows):
	"""write the candles rows compressed at dest, through a temporary file"""
	a = np.asarray(rows, dtype=float).reshape(-1, 5)
	tmp = dest + ".tmp"
	with gzip.open(tmp, "wt", newline="", compresslevel=6) as f:
		f.write(",".join(HEADER) + "\n")
		if len(a):
			f.write("\n".join(map("%d,%.10g,%.10g,%.10g,%.10g".__mod__, map(tuple, a.tolist()))) + "\n")
	os.replace(tmp, dest)

class Data:
	"""the candles of time frame tf (m15 by default) kept in a journal"""
	def __init__(self, dir, tf=15):
		self.dir = dir
		self.tf = tf
		self.load()

	def load(self):
		files = storeof(self.dir, self.tf)
		self.files = [p for p, _ in files]
		self.symbol = symbolin(os.path.basename(self.files[0])) if files else None
		a = np.concatenate([rs for _, rs in files]) if files else np.zeros((0, 5))
		a = a[np.unique(a[:, 0], return_index=True)[1]]
		self.setrows(a)

	def setrows(self, rows):
		a = np.array(rows, dtype=float).reshape(-1, 5)
		self.t = a[:, 0].astype(np.int64)
		self.o, self.h, self.l, self.c = a[:, 1], a[:, 2], a[:, 3], a[:, 4]
		self.wall = self.t + nyoffsets(self.t) if len(self.t) else self.t	# New York's clock
		# the trading day of each candle, in days since 1970
		self.dayno = (self.wall - DAYSTART * 3600) // 86400
		self.profs = {}

	def __len__(self):
		return len(self.t)

	def rows(self):
		return np.column_stack([self.t.astype(float), self.o, self.h, self.l, self.c])

	def add(self, path, new=None, symbol=None):
		"""add the candles of the file at path (or new) that are not here
		yet (after the last one or before the first): (added, skipped)"""
		if new is None:
			new = readrows(path)
		new = np.asarray(new, dtype=float).reshape(-1, 5)
		if not len(new):
			raise ValueError(f"no candles in {os.path.basename(path)}")
		if len(self):
			first, last = self.t[0], self.t[-1]
			after, before = new[new[:, 0] > last], new[new[:, 0] < first]
		else:
			after, before = new, new[:0]
		added = len(after) + len(before)
		if added:
			sym = self.symbol or symbol or symbolof(path)
			if len(before):	# files of their own, with the first one's candles (it may have the same name)
				first = self.files[0]
				kept = readrows(first)
				os.remove(first)
				self.write(sym, np.concatenate([before, kept]), None)
				if len(after):
					self.load()
			if len(after):	# the last file, while it is not too large, then new ones
				last = self.files[-1] if self.files else None
				self.write(sym, after, last)
			self.load()
		return added, len(new) - added

	def write(self, sym, rows, path=None):
		"""write rows after the candles in the file at path (or in new
		files), starting a new file named after its first day each time one
		would go over MAXFILE (MAXLOW under m15)"""
		mx = MAXFILE if self.tf >= 15 else MAXLOW
		kept = readrows(path) if path else None
		while len(rows):
			n = len(rows)
			if kept is not None and len(kept):	# how many fit, by the bytes a candle takes in the file
				size = os.path.getsize(path)
				n = max(0, min(n, int((mx - size) / max(1, size / len(kept)))))
			elif len(rows) * 17 > mx:	# about 17 bytes a candle, compressed
				n = mx // 17
			if n == 0:	# that one is full
				kept, path = None, None
				continue
			chunk, rows = rows[:n], rows[n:]
			dest = path or os.path.join(self.dir, filename(sym, chunk[0][0], self.tf))
			writerows(dest, chunk if kept is None else np.concatenate([kept, chunk]))
			kept, path = None, None

	def first(self):
		return self.daydate(int(self.dayno[0])) if len(self) else None

	def last(self):
		return self.daydate(int(self.dayno[-1])) if len(self) else None

	@staticmethod
	def daydate(n):
		return EPOCH + timedelta(days=n)

	@staticmethod
	def dayn(d):
		return (d - EPOCH).days

	def days(self):
		"""the trading days with candles, Monday to Friday"""
		return [d for d in (self.daydate(int(n)) for n in np.unique(self.dayno)) if d.weekday() < 5]

	def weeks(self):
		"""the Mondays of the weeks with candles"""
		return sorted({d - timedelta(days=d.weekday()) for d in self.days()})

	def daysof(self, monday):
		return [d for d in self.days() if monday <= d < monday + timedelta(days=5)]

	def span(self, kind, d):
		"""the indexes [i, j) of the candles of day d ("d") or of the week of
		Monday d ("w"), and the wall time (s) where its t is 0"""
		if kind == "d":
			n = self.dayn(d)
			lo, hi = n, n + 1
			zero = n * 86400
		else:
			n = self.dayn(d)
			lo, hi = n, n + 5
			zero = n * 86400
		i, j = np.searchsorted(self.dayno, [lo, hi])
		return int(i), int(j), zero

	def tof(self, kind, i, zero):
		"""the t of candle i in a profile: days for a week, hours for a day"""
		return (self.wall[i] - zero) / (3600 if kind == "d" else 86400)

	def profile(self, kind, d, prices=False, upto=None, until=None):
		"""the profile of day d or week d: [(t, v)], or None. The points
		are at the middle of their candles. With prices, [(t, price)]. With
		upto, that of the week only to the end of day upto; with until, only
		to time until (hours of a day, days of a week)"""
		k = (kind, d, upto, until)
		if k not in self.profs:
			adj = self.adjusted(kind, d) if upto is None and until is None else None
			self.profs[k] = self.normal(adj) if adj else self.findprofile(kind, d, upto, until)
		p = self.profs[k]
		return p and p[1 if prices else 0]

	def findprofile(self, kind, d, upto=None, until=None):
		i, j, zero = self.span(kind, d)
		if upto is not None:
			j = min(j, int(np.searchsorted(self.dayno, self.dayn(upto) + 1)))
		if until is not None:	# the candles that end by until
			unit = 3600 if kind == "d" else 86400
			j = min(j, int(np.searchsorted(self.wall, zero + until * unit - 900, "right")))
		if j - i < 4:
			return None
		xs = np.arange(j - i)
		hi, lo = -self.h[i:j], -self.l[i:j]	# as in an image: down is more
		pts, top, bot = weekprof.zigzag(xs, hi, lo, WEEKSWING if kind == "w" else DAYSWING)
		half = 7.5 * 60 / (3600 if kind == "d" else 86400)
		pts = [(float(self.tof(kind, i + x, zero)) + half, -y, x) for x, y in pts]
		pts = weekprof.clean(pts, 0.05 if kind == "w" else 0.5)
		return self.normal([(t, y) for t, y, _ in pts])

	@staticmethod
	def normal(pts):
		"""([(t, v)], [(t, price)]) of profile pts [(t, price)], v from 0 at its low to 1"""
		ys = [y for _, y in pts]
		low, high = min(ys), max(ys)
		return ([(round(t, 3), round((y - low) / max(1e-9, high - low), 3)) for t, y in pts], list(pts))

	def adjpath(self, kind, d):
		return os.path.join(self.dir, DRAWDIR, f"{kind}{d:%y%m%d}.prof")

	def adjusted(self, kind, d):
		"""the profile of day or week d as adjusted by hand, [(t, price)], or None"""
		try:
			with open(self.adjpath(kind, d)) as f:
				pts = [(float(t), float(p)) for t, p in json.load(f)]
			return pts if len(pts) >= 2 else None
		except (OSError, ValueError, TypeError):
			return None

	def adjust(self, kind, d, pts):
		"""keep pts [(t, price)] as the profile of day or week d; None goes back to the one found"""
		p = self.adjpath(kind, d)
		for k in [k for k in self.profs if k[:2] == (kind, d)]:
			del self.profs[k]
		if not pts:
			if os.path.exists(p):
				os.remove(p)
			return
		os.makedirs(os.path.dirname(p), exist_ok=True)
		with open(p + ".tmp", "w") as f:
			json.dump([[t, v] for t, v in sorted(pts)], f)
		os.replace(p + ".tmp", p)

	def end(self, kind, d):
		"""the time the last candle of day or week d ends, in its t"""
		i, j, zero = self.span(kind, d)
		return float(self.tof(kind, j - 1, zero)) + 900 / (3600 if kind == "d" else 86400) if j > i else None

	def sessions(self, d):
		"""[(name, start, end, high, low, i, j, color)] of the sessions of day
		d with candles: start and end in hours, i and j its candles"""
		i0, j0, zero = self.span("d", d)
		hours = (self.wall[i0:j0] - zero) / 3600
		out = []
		for name, a, b, color in SESSIONS:
			k = np.flatnonzero((hours >= a) & (hours < b))
			if len(k):
				i, j = i0 + int(k[0]), i0 + int(k[-1]) + 1
				out.append((name, a, b, float(self.h[i:j].max()), float(self.l[i:j].min()), i, j, color))
		return out

	def summary(self, kind, d):
		"""a line with what happened: the range, and when the high and low were"""
		i, j, zero = self.span(kind, d)
		if j <= i:
			return ""
		h, l = self.h[i:j], self.l[i:j]
		ih, il = i + int(h.argmax()), i + int(l.argmin())
		when = lambda k: self.walltime(k).strftime("%a %H:%M" if kind == "w" else "%H:%M")
		s = (f"Open {price(self.o[i])}   High {price(h.max())} ({when(ih)})   Low {price(l.min())} ({when(il)})   "
			f"Close {price(self.c[j-1])}   Range {price(h.max() - l.min())}")
		if kind == "d":
			for name, a, b, sh, sl, _, _, _ in self.sessions(d):
				s += f"\n{name}: {price(sl)} – {price(sh)} ({price(sh - sl)})"
		return s

	def walltime(self, i):
		"""New York's time of candle i, as a naive datetime"""
		return datetime(1970, 1, 1) + timedelta(seconds=int(self.wall[i]))

	# ---- drawings on the charts ----
	def drawpath(self, kind, d, tf=15):
		"""the file of what is drawn on the chart of day or week d in time
		frame tf: d261117.drw in m15, d261117-m5.drw in m5"""
		return os.path.join(self.dir, DRAWDIR, f"{kind}{d:%y%m%d}" + ("" if tf == 15 else "-" + tfname(tf)) + ".drw")

	def notespath(self, kind, d):
		"""the file of the notes of day or week d: d261117.txt, w261116.txt"""
		return os.path.join(self.dir, DRAWDIR, f"{kind}{d:%y%m%d}.txt")

	def readnotes(self, kind, d):
		try:
			with open(self.notespath(kind, d), encoding="utf-8") as f:
				return f.read()
		except OSError:
			return ""

	def savenotes(self, kind, d, text):
		"""keep the notes of day or week d; empty ones remove the file"""
		p = self.notespath(kind, d)
		if not text.strip():
			if os.path.exists(p):
				os.remove(p)
			return
		os.makedirs(os.path.dirname(p), exist_ok=True)
		tmp = p + ".tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			f.write(text)
		os.replace(tmp, p)

	def readdrawing(self, kind, d, tf=15):
		"""what is drawn on the chart of day or week d, or None"""
		try:
			with open(self.drawpath(kind, d, tf), encoding="utf-8") as f:
				x = json.load(f)
			return x if isinstance(x, dict) else None
		except (OSError, ValueError):
			return None

	def drawn(self, kind, d):
		"""whether something is drawn on the chart of day or week d, in any time frame"""
		return any(os.path.exists(self.drawpath(kind, d, tf)) for tf in TFS)

	def savedrawing(self, kind, d, data, tf=15):
		"""keep what is drawn on the chart of day or week d; nothing removes it"""
		p = self.drawpath(kind, d, tf)
		if not data or not data.get("shapes"):
			if os.path.exists(p):
				os.remove(p)
			return
		os.makedirs(os.path.dirname(p), exist_ok=True)
		tmp = p + ".tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			json.dump(data, f, ensure_ascii=False, indent=1)
		os.replace(tmp, p)

	def periodbars(self, kind, d, tf, n=None):
		"""the candles of days, weeks or months (tf DAILY, WEEKLY, MONTHLY)
		up to the end of day d or of the week of Monday d: (start, o, h, l,
		c, end) arrays, start and end in UTC seconds, the last n (PERIODS)"""
		last = self.dayn(d) + (4 if kind == "w" else 0)
		j = int(np.searchsorted(self.dayno, last, "right"))
		r = periodrows(self.t[:j], self.o[:j], self.h[:j], self.l[:j], self.c[:j], self.dayno[:j], tf)
		if len(r[0]):
			r[5][-1] = min(int(r[5][-1]), int(dayend(np.array([last]))[0]))
		n = PERIODS[tf] if n is None else n
		return tuple(a[-n:] for a in r)

	def bars(self, kind, d, tf=15):
		"""the candles of day or week d in tf minutes (tf a multiple of this
		data's): (wall, o, h, l, c) arrays, wall each candle's start in New
		York's clock, and the wall time where t is 0"""
		i, j, zero = self.span(kind, d)
		a = np.column_stack([self.t[i:j].astype(float), self.o[i:j], self.h[i:j], self.l[i:j], self.c[i:j]])
		if tf != self.tf:
			a = resample(a, tf)
		t = a[:, 0].astype(np.int64)
		wall = t + nyoffsets(t) if len(t) else t
		return wall, a[:, 1], a[:, 2], a[:, 3], a[:, 4], zero

def periodrows(t, o, h, l, c, dayno, tf):
	"""candles t, o, h, l, c (of trading days dayno) as candles of days,
	weeks or months: (start, o, h, l, c, end) arrays, start and end in UTC
	seconds (end that of the period's last trading day)"""
	if not len(t):
		e = np.zeros(0)
		return e.astype(np.int64), e, e, e, e, e.astype(np.int64)
	key = periodkeys(dayno, tf)
	starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
	ends = np.r_[starts[1:] - 1, len(t) - 1]
	return (daystart(dayno[starts]), o[starts], np.maximum.reduceat(h, starts), np.minimum.reduceat(l, starts), c[ends],
		dayend(periodlast(key[starts], tf)))

def daynos(t):
	"""the trading day of each UTC time of array t, in days since 1970"""
	t = np.asarray(t).astype(np.int64)
	return (t + nyoffsets(t) - DAYSTART * 3600) // 86400 if len(t) else t

def rolls(ref, rows):
	"""the price offsets that make the m15 candles rows match those in ref
	where both have them, one for each contract (a roll moves it): a list of
	(dayno, offset) from that trading day on, empty when they don't overlap.
	A day starts a new offset when its median close difference moves and the
	next day agrees, so a roll day or a bad tick doesn't."""
	ref = np.asarray(ref, dtype=float).reshape(-1, 5)
	rows = np.asarray(rows, dtype=float).reshape(-1, 5)
	_, i, j = np.intersect1d(ref[:, 0], rows[:, 0], assume_unique=True, return_indices=True)
	if len(i) < ROLLMIN:
		return []
	diff = ref[i, 4] - rows[j, 4]
	days, starts = np.unique(daynos(rows[j, 0]), return_index=True)
	med = [float(np.median(x)) for x in np.split(diff, starts[1:])]
	lv = []	# (index of its first day, level)
	for k, m in enumerate(med):
		if lv and abs(m - lv[-1][1]) <= ROLLTOL:
			continue
		if not lv or (k + 1 < len(med) and abs(med[k + 1] - m) <= ROLLTOL):
			lv.append((k, m))
	res = []
	for n, (k, _) in enumerate(lv):	# each offset, from all its candles, in ticks
		lo = starts[k]
		hi = starts[lv[n + 1][0]] if n + 1 < len(lv) else len(diff)
		res.append((int(days[k]), round(float(np.median(diff[lo:hi])) / TICK) * TICK))
	return res

def shift(rows, offs):
	"""rows with the prices of each candle moved by its offset in offs, from
	rolls (the first one for the candles before it)"""
	a = np.array(rows, dtype=float).reshape(-1, 5)
	if not offs or not len(a):
		return a
	starts = np.array([d for d, _ in offs])
	k = np.clip(np.searchsorted(starts, daynos(a[:, 0]), "right") - 1, 0, None)
	a[:, 1:] += np.array([o for _, o in offs])[k][:, None]
	return a

def importfile(dir, path, data=None, offsets=None):
	"""import the candles of the file at path into journal dir: kept in
	their own time frame, and, under m15, made m15 candles too that the m15
	data takes. Their prices are first moved to match the m15 data already
	there, contract by contract (see rolls); offsets, if given, gets the
	(first day, offset) used. [(tf, added, skipped)]"""
	rows = readrows(path)
	if not len(rows):
		raise ValueError(f"no candles in {os.path.basename(path)}")
	tf = tfof(rows)
	data = data or Data(dir)
	sym = data.symbol or symbolof(path)
	if tf <= data.tf and len(data):
		offs = rolls(data.rows(), rows if tf == data.tf else resample(rows, data.tf))
		if any(o for _, o in offs):
			rows = shift(rows, offs)
			if offsets is not None:
				offsets.extend((EPOCH + timedelta(days=d), o) for d, o in offs)
	out = []
	if tf == data.tf:
		return [(tf, *data.add(path, rows, sym))]
	if tf < 15 and 15 % tf == 0:
		low = Data(dir, tf)
		out.append((tf, *low.add(path, rows, sym)))
		out.append((15, *data.add(path, resample(rows, 15), sym)))
		return out
	raise ValueError(f"{os.path.basename(path)} has candles of {tfname(tf)}: only m15 and lower time frames that make it (m1, m3, m5) are taken")
