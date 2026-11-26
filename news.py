#
# the days with US news that move the market: FOMC decisions (14:00 New
# York), CPI, PPI and NFP (the Employment Situation) releases (08:30). The
# dates from 2022 on are built in, from the Federal Reserve's and the BLS's
# calendars (the later ones as scheduled); fetch() reads those calendars
# again for the dates scheduled since, kept in FETCHED for every journal;
# a journal may add more, or other reports, in NEWSFILE, with
# lines like "2027-01-13 CPI" or "2027-01-29 NFP 08:30"; "-2027-01-13 CPI"
# takes one away. They are shown on the data charts and list, and are tags
# of the captures of those days.
#
# The market and bank holidays and the special days (early closes) are
# marked too, all day: the US ones are reckoned from their rules (see
# holidays), the Federal Reserve's holiday calendar fetched adds those it
# names (kept in FETCHEDHOL), and a line of NEWSFILE with a name of HOLIDAYS
# or "Hday" adds one (e.g. "2027-01-09 Mourning"). They are tags of the
# captures by their names, and shown on the lists by their abbreviations.
#
import os
import re
import urllib.request
from datetime import date, timedelta
from html import unescape

NEWSFILE = "news.txt"
TIMES = {"FOMC": 14.0, "CPI": 8.5, "PPI": 8.5, "NFP": 8.5}
FETCHED = None	# the file fetch writes, set by the app (in its data folder)	# New York hour of the release
DEFTIME = 8.5

FOMC = """
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16 2026-10-28 2026-12-09
2027-01-27 2027-03-17 2027-04-28 2027-06-09 2027-07-28 2027-09-15 2027-10-27 2027-11-17
"""
CPI = """
2022-01-12 2022-02-10 2022-03-10 2022-04-12 2022-05-11 2022-06-10 2022-07-13 2022-08-10 2022-09-13 2022-10-13 2022-11-10 2022-12-13
2023-01-12 2023-02-14 2023-03-14 2023-04-12 2023-05-10 2023-06-13 2023-07-12 2023-08-10 2023-09-13 2023-10-12 2023-11-14 2023-12-12
2024-01-11 2024-02-13 2024-03-12 2024-04-10 2024-05-15 2024-06-12 2024-07-11 2024-08-14 2024-09-11 2024-10-10 2024-11-13 2024-12-11
2025-01-15 2025-02-12 2025-03-12 2025-04-10 2025-05-13 2025-06-11 2025-07-15 2025-08-12 2025-09-11 2025-10-24 2025-12-18
2026-01-13 2026-02-13 2026-03-11 2026-04-10 2026-05-12 2026-06-10 2026-07-14 2026-08-12 2026-09-11 2026-10-14 2026-11-10 2026-12-10
2027-01-13 2027-02-11 2027-03-10 2027-04-13 2027-05-12 2027-06-10 2027-07-14 2027-08-11 2027-09-14 2027-10-14 2027-11-10 2027-12-10
"""
PPI = """
2022-01-13 2022-02-15 2022-03-15 2022-04-13 2022-05-12 2022-06-14 2022-07-14 2022-08-11 2022-09-14 2022-10-12 2022-11-15 2022-12-09
2023-01-18 2023-02-16 2023-03-15 2023-04-13 2023-05-11 2023-06-14 2023-07-13 2023-08-11 2023-09-14 2023-10-11 2023-11-15 2023-12-13
2024-01-12 2024-02-16 2024-03-14 2024-04-11 2024-05-14 2024-06-13 2024-07-12 2024-08-13 2024-09-12 2024-10-11 2024-11-14 2024-12-12
2025-01-14 2025-02-13 2025-03-13 2025-04-11 2025-05-15 2025-06-12 2025-07-16 2025-08-14 2025-09-10 2025-11-25
2026-01-14 2026-01-30 2026-02-27 2026-03-18 2026-04-14 2026-05-13 2026-06-11 2026-07-15 2026-08-13 2026-09-10 2026-10-15 2026-11-13 2026-12-15
2027-01-14 2027-02-12 2027-03-12 2027-04-14 2027-05-13 2027-06-11 2027-07-15 2027-08-10 2027-09-10 2027-10-15 2027-11-12 2027-12-15
"""
NFP = """
2022-01-07 2022-02-04 2022-03-04 2022-04-01 2022-05-06 2022-06-03 2022-07-08 2022-08-05 2022-09-02 2022-10-07 2022-11-04 2022-12-02
2023-01-06 2023-02-03 2023-03-10 2023-04-07 2023-05-05 2023-06-02 2023-07-07 2023-08-04 2023-09-01 2023-10-06 2023-11-03 2023-12-08
2024-01-05 2024-02-02 2024-03-08 2024-04-05 2024-05-03 2024-06-07 2024-07-05 2024-08-02 2024-09-06 2024-10-04 2024-11-01 2024-12-06
2025-01-10 2025-02-07 2025-03-07 2025-04-04 2025-05-02 2025-06-06 2025-07-03 2025-08-01 2025-09-05 2025-11-20 2025-12-16
2026-01-09 2026-02-11 2026-03-06 2026-04-03 2026-05-08 2026-06-05 2026-07-02 2026-08-07 2026-09-04 2026-10-02 2026-11-06 2026-12-04
2027-01-08 2027-02-05 2027-03-05 2027-04-02 2027-05-07 2027-06-04 2027-07-02 2027-08-06 2027-09-03 2027-10-08 2027-11-05 2027-12-03
"""
# the holidays and special days: name (a tag) -> abbreviation (on the lists)
HOLIDAYS = {
	"NewYear": "NewYr", "MLKDay": "MLK", "PresidentsDay": "Pres", "GoodFriday": "GdFri", "MemorialDay": "Memor",
	"Juneteenth": "Jun19", "IndependenceDay": "Jul4", "LaborDay": "Labor", "ColumbusDay": "Colum",
	"VeteransDay": "Vets", "Thanksgiving": "Thksg", "Christmas": "Xmas",
	"BlackFriday": "BlkFri", "ChristmasEve": "XmEve", "July3": "Jul3", "NewYearsEve": "NYEve",
	"Mourning": "Mourn", "EarlyClose": "Early", "Hday": "Hday",
}
# days the markets closed, or closed early, out of the rules
SPECIAL = {"2025-01-09": "Mourning", "2018-12-05": "Mourning"}
FETCHEDHOL = None	# the holidays fetch writes (next to FETCHED when not set)

def observed(d, saturday=True):
	"""the weekday a holiday of date d is kept on: Sunday's on Monday,
	Saturday's on Friday (none with saturday False)"""
	if d.weekday() == 6:
		return d + timedelta(days=1)
	if d.weekday() == 5:
		return d - timedelta(days=1) if saturday else None
	return d

def nth(year, month, weekday, n):
	"""the nth weekday (0 Monday) of month; n -1 the last"""
	if n > 0:
		d = date(year, month, 1)
		return d + timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))
	d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
	return d - timedelta(days=(d.weekday() - weekday) % 7)

def easter(year):
	"""Easter Sunday (the Gregorian computus)"""
	a, b, c = year % 19, year // 100, year % 100
	d, e = b // 4, b % 4
	f = (b + 8) // 25
	g = (b - f + 1) // 3
	h = (19 * a + b - d - g + 15) % 30
	i, k = c // 4, c % 4
	l = (32 + 2 * e + 2 * i - h - k) % 7
	m = (a + 11 * h + 22 * l) // 451
	month = (h + l - 7 * m + 114) // 31
	day = (h + l - 7 * m + 114) % 31 + 1
	return date(year, month, day)

def holidays(year):
	"""the US market and bank holidays and special days of year, as kept:
	{date: name}"""
	out = {}
	def put(d, name):
		if d is not None and d.year == year:
			out.setdefault(d, name)
	put(observed(date(year, 1, 1), False), "NewYear")
	put(nth(year, 1, 0, 3), "MLKDay")
	put(nth(year, 2, 0, 3), "PresidentsDay")
	put(easter(year) - timedelta(days=2), "GoodFriday")
	put(nth(year, 5, 0, -1), "MemorialDay")
	if year >= 2022:
		put(observed(date(year, 6, 19)), "Juneteenth")
	jul4 = observed(date(year, 7, 4))
	put(jul4, "IndependenceDay")
	put(nth(year, 9, 0, 1), "LaborDay")
	put(nth(year, 10, 0, 2), "ColumbusDay")
	put(observed(date(year, 11, 11), False), "VeteransDay")
	thanks = nth(year, 11, 3, 4)
	put(thanks, "Thanksgiving")
	put(thanks + timedelta(days=1), "BlackFriday")
	xmas = observed(date(year, 12, 25))
	put(xmas, "Christmas")
	eve = date(year, 12, 24)
	if eve.weekday() < 5 and eve != xmas:
		put(eve, "ChristmasEve")
	j3 = date(year, 7, 3)
	if j3.weekday() < 5 and j3 != jul4:
		put(j3, "July3")
	for k, name in SPECIAL.items():
		put(date.fromisoformat(k), name)
	return out

def holname(name):
	"""the name of HOLIDAYS name is (in any case), or None"""
	low = name.lower()
	return next((h for h in HOLIDAYS if h.lower() == low), None)

LINE = re.compile(r"^(-?)(\d{4}-\d{2}-\d{2})\s+([A-Za-z][\w&.-]*)(?:\s+(\d{1,2}):(\d{2}))?\s*(?:#.*)?$")

def builtin():
	out = {}
	for name, text in (("FOMC", FOMC), ("CPI", CPI), ("PPI", PPI), ("NFP", NFP)):
		for s in text.split():
			out.setdefault(date.fromisoformat(s), {})[name] = TIMES[name]
	return out

class News:
	"""the news of each day: {date: {name: New York hour}}"""
	def __init__(self, dir=None):
		self.days = builtin()
		self.hol = {}	# {date: holiday name}, see holidays
		for y in range(2015, date.today().year + 3):
			self.hol.update(holidays(y))
		self.bad = []	# lines of NEWSFILE not understood
		if FETCHED:
			self.read(FETCHED)
		if holpath():
			self.read(holpath())
		if dir:
			self.read(os.path.join(dir, NEWSFILE))

	def read(self, path):
		try:
			with open(path, encoding="utf-8") as f:
				lines = f.read().splitlines()
		except OSError:
			return
		for ln in lines:
			s = ln.strip()
			if not s or s.startswith("#"):
				continue
			m = LINE.match(s)
			if m is None:
				self.bad.append(ln)
				continue
			minus, d, name, hh, mm = m.groups()
			try:
				d = date.fromisoformat(d)
			except ValueError:
				self.bad.append(ln)
				continue
			h = holname(name)
			if h is not None:
				if minus:
					if self.hol.get(d) == h:
						del self.hol[d]
				else:
					self.hol[d] = h
				continue
			name = name.upper()
			if minus:
				self.days.get(d, {}).pop(name, None)
				if d in self.days and not self.days[d]:
					del self.days[d]
				continue
			hour = int(hh) + int(mm) / 60 if hh else TIMES.get(name, DEFTIME)
			self.days.setdefault(d, {})[name] = hour

	def of(self, d):
		"""the news of day d, by time: [(hour, name)]"""
		return sorted((h, n) for n, h in self.days.get(d, {}).items())

	def names(self, d):
		"""the names of the news of day d, and of its holiday (and Holiday): its tags"""
		return [n for _, n in self.of(d)] + ([self.hol[d], "Holiday"] if d in self.hol else [])

	def holiday(self, d):
		"""the name of the holiday of day d, or None"""
		return self.hol.get(d)

	def inweek(self, monday):
		"""the news of the week of monday: [(date, hour, name)]"""
		return [(monday + timedelta(days=k), h, n) for k in range(5) for h, n in self.of(monday + timedelta(days=k))]

	def marks(self, d, week=False):
		"""what the lists show of day d (or of the week of monday d): the
		news names and the holidays' abbreviations, as one string"""
		days = [d + timedelta(days=k) for k in range(5)] if week else [d]
		out = []
		for day in days:
			out += [n for _, n in self.of(day)]
			if day in self.hol:
				out.append(HOLIDAYS.get(self.hol[day], "Hday"))
		return " ".join(dict.fromkeys(out))

def holpath():
	"""where the fetched holidays are kept"""
	if FETCHEDHOL:
		return FETCHEDHOL
	return os.path.join(os.path.dirname(FETCHED), "holidays.txt") if FETCHED else None

# ---- fetching the calendars ----
SOURCES = {
	"FOMC": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
	"CPI": "https://www.bls.gov/schedule/news_release/cpi.htm",
	"PPI": "https://www.bls.gov/schedule/news_release/ppi.htm",
	"NFP": "https://www.bls.gov/schedule/news_release/empsit.htm",
}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
BLSDATE = re.compile(r"(" + MONTH + r")\.?\s+(\d{1,2}),\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*([AP]M)")
FEDYEAR = re.compile(r"(\d{4}) FOMC Meetings")
FEDMEET = re.compile(r"\b(" + MONTH + r")(?:/(" + MONTH + r"))?\s+(\d{1,2})-(\d{1,2})\b")

def text(html):
	"""the text of a page, its tags as spaces"""
	return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))

def month(name):
	return MONTHS.index(name[:3].lower()) + 1

def blsdates(page):
	"""the release dates and times of a BLS schedule page: [(date, hour)],
	from the dates with a time (its other dates, as the page's, have none)"""
	out = []
	for m in BLSDATE.finditer(text(page)):
		mo, day, year, hh, mm, ampm = m.groups()
		try:
			d = date(int(year), month(mo), int(day))
		except ValueError:
			continue
		hour = int(hh) % 12 + (12 if ampm == "PM" else 0) + int(mm) / 60
		out.append((d, hour))
	return out

def feddates(page):
	"""the days of the FOMC decisions (the last day of each meeting) of the
	Federal Reserve's calendar page"""
	t = text(page)
	years = list(FEDYEAR.finditer(t))
	out = []
	for k, y in enumerate(years):
		part = t[y.end():years[k + 1].start() if k + 1 < len(years) else len(t)]
		for m in FEDMEET.finditer(part):
			m1, m2, d1, d2 = m.groups()
			mo = month(m2 or m1)
			try:
				out.append(date(int(y.group(1)), mo, int(d2)))
			except ValueError:
				pass
	out = sorted(set(out))	# a meeting given twice, as days a day apart: its last day
	return [d for k, d in enumerate(out) if k + 1 == len(out) or (out[k + 1] - d).days > 3]

def get(url, timeout=20):
	req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh) DayJournal", "Accept": "text/html"})
	with urllib.request.urlopen(req, timeout=timeout) as r:
		return r.read().decode("utf-8", "replace")

def fetch(path=None, get=get):
	"""read the calendars of SOURCES again and keep the dates they give in
	path (FETCHED) as lines of NEWSFILE: {name: number of dates, or the
	error}"""
	path = path or FETCHED
	found, res = {}, {}
	for name, url in SOURCES.items():
		try:
			page = get(url)
			got = [(d, TIMES["FOMC"]) for d in feddates(page)] if name == "FOMC" else blsdates(page)
		except Exception as x:	# the network, the page: say which
			res[name] = str(x) or type(x).__name__
			continue
		res[name] = len(got)
		found[name] = got
	old = []
	try:
		with open(path, encoding="utf-8") as f:
			old = [ln for ln in f.read().splitlines() if ln.strip() and not ln.startswith("#")]
	except OSError:
		pass
	keep = [ln for ln in old if not any(f" {n}" in ln for n, got in found.items() if got)]	# reports not read now stay
	lines = keep + [f"{d.isoformat()} {n} {int(h):02d}:{int(round(h % 1 * 60)):02d}" for n, got in found.items() for d, h in sorted(set(got))]
	if any(found.values()):
		os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
		tmp = path + ".tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			f.write("# news dates read from the Federal Reserve's and the BLS's calendars\n" + "\n".join(lines) + "\n")
		os.replace(tmp, path)
	res.update(fetchholidays(os.path.join(os.path.dirname(path), "holidays.txt") if path != FETCHED else holpath(), get))
	return res

# ---- fetching the holidays ----
HOLSOURCES = {
	"Holidays (NYSE)": "https://www.nyse.com/markets/hours-calendars",
	"Holidays (Fed)": "https://www.federalreserve.gov/aboutthefed/k8.htm",
}
HOLWORDS = [("new year", "NewYear"), ("king", "MLKDay"), ("washington", "PresidentsDay"), ("president", "PresidentsDay"),
	("good friday", "GoodFriday"), ("memorial", "MemorialDay"), ("juneteenth", "Juneteenth"),
	("independence", "IndependenceDay"), ("labor", "LaborDay"), ("columbus", "ColumbusDay"), ("veterans", "VeteransDay"),
	("thanksgiving", "Thanksgiving"), ("christmas", "Christmas")]
DAYDATE = re.compile(r"(" + MONTH + r")\s+(\d{1,2})(?:,\s+(\d{4}))?")
EARLY = re.compile(r"[Ee]arly close[^*]*?\bon\s+((?:(?:Monday|Tuesday|Wednesday|Thursday|Friday),\s+" + MONTH +
	r"\s+\d{1,2},\s+\d{4}(?:,\s+(?:and\s+)?)?)+)([^.*]*)")

def holkey(name):
	low = text(name).lower()
	return next((k for w, k in HOLWORDS if w in low), None)

def tables(page):
	"""the rows of the first table of page: [[cell text]], the header first"""
	m = re.search(r"<table.*?</table>", page, re.S | re.I)
	if m is None:
		return []
	rows = []
	for r in re.findall(r"<tr.*?</tr>", m.group(0), re.S | re.I):
		rows.append([text(c).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S | re.I)])
	return rows

def tabledates(page, fed=False):
	"""the holidays of the table of the NYSE's or the Fed's calendar:
	[(date, name)]. The NYSE's give the day kept; the Fed's the date, kept
	on the Monday when a Sunday and not by the banks when a Saturday"""
	rows = tables(page)
	if not rows:
		return []
	years = [int(y) if re.fullmatch(r"\d{4}", y) else None for y in rows[0]]
	out = []
	for r in rows[1:]:
		if not r:
			continue
		name = holkey(r[0])
		if name is None:
			continue
		for k, cell in enumerate(r[1:], 1):
			y = years[k] if k < len(years) else None
			m = DAYDATE.search(cell)
			if y is None or m is None:
				continue
			try:
				d = date(y, month(m.group(1)), int(m.group(2)))
			except ValueError:
				continue
			if fed:
				d = observed(d, False)
				if d is None:
					continue
			out.append((d, name))
	return out

def earlycloses(page):
	"""the days the NYSE closes early, from the notes of its calendar: [(date, name)]"""
	out = []
	for m in EARLY.finditer(text(page)):
		days, rest = m.group(1), m.group(2).lower()
		for dm in DAYDATE.finditer(days):
			if not dm.group(3):
				continue
			try:
				d = date(int(dm.group(3)), month(dm.group(1)), int(dm.group(2)))
			except ValueError:
				continue
			if "thanksgiving" in rest or (d.month == 11 and d.weekday() == 4 and d.day >= 23):
				name = "BlackFriday"
			elif (d.month, d.day) == (12, 24):
				name = "ChristmasEve"
			elif (d.month, d.day) == (7, 3):
				name = "July3"
			else:
				name = "EarlyClose"
			out.append((d, name))
	return out

def fetchholidays(path, get=get):
	"""read the NYSE's and the Fed's holiday calendars and keep the days
	they give in path, as lines of NEWSFILE: {source: number of days, or the
	error}"""
	res, found = {}, []
	for name, url in HOLSOURCES.items():
		try:
			page = get(url)
			got = tabledates(page, fed="federalreserve" in url)
			if "nyse" in url:
				got += earlycloses(page)
		except Exception as x:
			res[name] = str(x) or type(x).__name__
			continue
		res[name] = len(got)
		found += got
	if found and path:
		old = []
		try:
			with open(path, encoding="utf-8") as f:
				old = [ln for ln in f.read().splitlines() if ln.strip() and not ln.startswith("#")]
		except OSError:
			pass
		seen = {}
		for d, n in sorted(found):
			seen.setdefault(d, n)	# the NYSE's name of a day first
		years = {d.year for d in seen}
		keep = [ln for ln in old if ln[:4].isdigit() and int(ln[:4]) not in years]	# years not read now stay
		lines = keep + [f"{d.isoformat()} {n}" for d, n in sorted(seen.items())]
		os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
		tmp = path + ".tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			f.write("# holidays read from the NYSE's and the Federal Reserve's calendars\n" + "\n".join(lines) + "\n")
		os.replace(tmp, path)
	return res
