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
		self.bad = []	# lines of NEWSFILE not understood
		if FETCHED:
			self.read(FETCHED)
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
		return [n for _, n in self.of(d)]

	def inweek(self, monday):
		"""the news of the week of monday: [(date, hour, name)]"""
		return [(monday + timedelta(days=k), h, n) for k in range(5) for h, n in self.of(monday + timedelta(days=k))]

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
	return res
