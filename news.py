#
# the days with US news that move the market: FOMC decisions (14:00 New
# York), CPI and PPI releases (08:30). The dates from 2022 on are built in,
# from the Federal Reserve's and the BLS's calendars (the later ones as
# scheduled); a journal may add more, or other reports, in NEWSFILE, with
# lines like "2027-01-13 CPI" or "2027-01-29 NFP 08:30"; "-2027-01-13 CPI"
# takes one away. They are shown on the data charts and list, and are tags
# of the captures of those days.
#
import os
import re
from datetime import date

NEWSFILE = "news.txt"
TIMES = {"FOMC": 14.0, "CPI": 8.5, "PPI": 8.5}	# New York hour of the release
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
LINE = re.compile(r"^(-?)(\d{4}-\d{2}-\d{2})\s+([A-Za-z][\w&.-]*)(?:\s+(\d{1,2}):(\d{2}))?\s*(?:#.*)?$")

def builtin():
	out = {}
	for name, text in (("FOMC", FOMC), ("CPI", CPI), ("PPI", PPI)):
		for s in text.split():
			out.setdefault(date.fromisoformat(s), {})[name] = TIMES[name]
	return out

class News:
	"""the news of each day: {date: {name: New York hour}}"""
	def __init__(self, dir=None):
		self.days = builtin()
		self.bad = []	# lines of NEWSFILE not understood
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
		from datetime import timedelta
		return [(monday + timedelta(days=k), h, n) for k in range(5) for h, n in self.of(monday + timedelta(days=k))]
