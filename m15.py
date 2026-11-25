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
DRAWDIR = "m15draw"
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

def readrows(path):
	"""the candles [(t, o, h, l, c)] in the CSV at path, or in the first
	CSV in the zip at path, sorted by time"""
	if path.lower().endswith(".gz"):
		with gzip.open(path, "rt", encoding="utf-8-sig") as f:
			text = f.read()
	elif zipfile.is_zipfile(path):
		with zipfile.ZipFile(path) as z:
			names = [n for n in z.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX")]
			if not names:
				raise ValueError(f"no CSV file in {os.path.basename(path)}")
			text = z.read(names[0]).decode("utf-8-sig")
	else:
		with open(path, encoding="utf-8-sig") as f:
			text = f.read()
	r = csv.reader(io.StringIO(text))
	head = [h.strip().lower() for h in next(r, [])]
	try:
		cols = [head.index(h) for h in HEADER]	# the first of each name
	except ValueError:
		raise ValueError(f"{os.path.basename(path)} has no {', '.join(HEADER)} columns")
	rows = {}
	for row in r:
		try:
			t = parsetime(row[cols[0]])
			rows[t] = tuple([t] + [float(row[i]) for i in cols[1:]])
		except (ValueError, IndexError):
			continue
	return [rows[t] for t in sorted(rows)]

def symbolof(path):
	"""the symbol in a file name: MNQ for MNQ.m15.csv.zip"""
	b = os.path.basename(path)
	return b.split(".")[0].split("_")[0] or "data"

def dayof(t):
	"""the trading day (New York) of the candle at UTC time t"""
	return EPOCH + timedelta(days=(int(t) + nyoffset(t) - DAYSTART * 3600) // 86400)

def filename(symbol, t):
	"""the name of a data file of symbol whose first candle is at time t"""
	return f"{symbol}-{dayof(t):%y%m%d}{EXT}"

def symbolin(name):
	"""the symbol of a data file name: MNQ for MNQ-260102.m15.csv.gz or MNQ.m15.csv"""
	b = name[:-len(EXT)] if name.endswith(EXT) else name[:-len(OLDEXT)]
	return re.sub(r"-\d{6}$", "", b) or "data"

def storeof(dir):
	"""the data files in journal dir, in order; plain ones are compressed
	and those not named after their first day renamed so first"""
	esc = glob.escape(dir)
	for p in sorted(glob.glob(os.path.join(esc, "*" + OLDEXT))):
		rows = readrows(p)
		if rows:
			writerows(os.path.join(dir, filename(symbolin(os.path.basename(p)), rows[0][0])), rows)
		os.remove(p)
	out = []
	for p in sorted(glob.glob(os.path.join(esc, "*" + EXT))):
		rows = readrows(p)
		if not rows:
			continue
		want = os.path.join(dir, filename(symbolin(os.path.basename(p)), rows[0][0]))
		if want != p and not os.path.exists(want):
			os.rename(p, want)
			p = want
		out.append((rows[0][0], p, rows))
	return [(p, rows) for _, p, rows in sorted(out)]

def writerows(dest, rows):
	"""write the candles rows compressed at dest, through a temporary file"""
	tmp = dest + ".tmp"
	with gzip.open(tmp, "wt", newline="") as f:
		w = csv.writer(f)
		w.writerow(HEADER)
		for t, o, h, l, c in rows:
			w.writerow([t] + [repr(float(x)).removesuffix(".0") for x in (o, h, l, c)])
	os.replace(tmp, dest)

class Data:
	"""the m15 candles kept in a journal"""
	def __init__(self, dir):
		self.dir = dir
		self.load()

	def load(self):
		files = storeof(self.dir)
		self.files = [p for p, _ in files]
		self.symbol = symbolin(os.path.basename(self.files[0])) if files else None
		rows = {}
		for _, rs in files:
			for r in rs:
				rows[r[0]] = r
		self.setrows([rows[t] for t in sorted(rows)])

	def setrows(self, rows):
		a = np.array(rows, dtype=float).reshape(-1, 5)
		self.t = a[:, 0].astype(np.int64)
		self.o, self.h, self.l, self.c = a[:, 1], a[:, 2], a[:, 3], a[:, 4]
		# New York's clock, in seconds, cached by the hour
		offs = {}
		def off(t):
			k = t // 3600
			if k not in offs:
				offs[k] = nyoffset(k * 3600)
			return offs[k]
		self.wall = np.array([t + off(t) for t in self.t.tolist()], dtype=np.int64)
		# the trading day of each candle, in days since 1970
		self.dayno = (self.wall - DAYSTART * 3600) // 86400
		self.profs = {}

	def __len__(self):
		return len(self.t)

	def rows(self):
		return list(zip(self.t.tolist(), self.o.tolist(), self.h.tolist(), self.l.tolist(), self.c.tolist()))

	def add(self, path):
		"""add the candles of the file at path that are not here yet (after
		the last one or before the first): (added, skipped)"""
		new = readrows(path)
		if not new:
			raise ValueError(f"no candles in {os.path.basename(path)}")
		old = self.rows()
		if old:
			first, last = old[0][0], old[-1][0]
			keep = [r for r in new if r[0] > last or r[0] < first]
		else:
			keep = new
		if keep:
			sym = self.symbol or symbolof(path)
			after = [r for r in keep if not old or r[0] > old[-1][0]]
			before = [r for r in keep if old and r[0] < old[0][0]]
			if before:	# a file of their own, or more
				self.write(sym, before, [])
			if after:	# the last file, while it is not too large, then new ones
				last = self.files[-1] if self.files else None
				self.write(sym, after, readrows(last) if last else [], last)
			self.load()
		return len(keep), len(new) - len(keep)

	def write(self, sym, rows, kept, path=None):
		"""write rows after the candles kept in the file at path (or in new
		files), starting a new file named after its first day each time one
		would go over MAXFILE"""
		while rows:
			n = len(rows)
			if kept and path:	# how many fit, by the bytes a candle takes in the file
				per = os.path.getsize(path) / max(1, len(kept))
				n = max(0, min(n, int((MAXFILE - os.path.getsize(path)) / max(1, per))))
			elif len(rows) * 17 > MAXFILE:	# about 17 bytes a candle, compressed
				n = MAXFILE // 17
			if n == 0:	# that one is full
				kept, path = [], None
				continue
			chunk, rows = rows[:n], rows[n:]
			writerows(path or os.path.join(self.dir, filename(sym, chunk[0][0])), kept + chunk)
			kept, path = [], None

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
	def drawpath(self, kind, d):
		return os.path.join(self.dir, DRAWDIR, f"{kind}{d:%y%m%d}.drw")

	def readdrawing(self, kind, d):
		"""what is drawn on the chart of day or week d, or None"""
		try:
			with open(self.drawpath(kind, d), encoding="utf-8") as f:
				x = json.load(f)
			return x if isinstance(x, dict) else None
		except (OSError, ValueError):
			return None

	def drawn(self, kind, d):
		return os.path.exists(self.drawpath(kind, d))

	def savedrawing(self, kind, d, data):
		"""keep what is drawn on the chart of day or week d; nothing removes it"""
		p = self.drawpath(kind, d)
		if not data or not data.get("shapes"):
			if os.path.exists(p):
				os.remove(p)
			return
		os.makedirs(os.path.dirname(p), exist_ok=True)
		tmp = p + ".tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			json.dump(data, f, ensure_ascii=False, indent=1)
		os.replace(tmp, p)
