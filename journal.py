#
# a day journal: a directory of chart snapshots named dayYYMMDD.png (a day)
# and dayYYMMDDweekprof.png (the week profile, dated the Sunday the week
# starts). A letter after the date (day260916b.png) is another snapshot of
# the same day. Each image may have notes in a .txt file with its name, and
# the words read from it by OCR are its tags, cached in TAGSFILE.
#
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from tags import cleantags

NAMERE = re.compile(r"^day(\d{2})(\d{2})(\d{2})(weekprof)?([a-z]?)\.png$", re.IGNORECASE)
TAGSFILE = ".pyjou-tags.json"
TAGSVERSION = 1		# bump when the cache layout changes

@dataclass
class Entry:
	"""one image of the journal"""
	name: str			# file name, day261014.png
	day: date
	week: bool = False	# a week profile
	extra: str = ""		# the letter of a second snapshot of the day
	tags: list[str] = field(default_factory=list)
	notes: str = ""

	def base(self):
		return os.path.splitext(self.name)[0]

	def notesname(self):
		return self.base() + ".txt"

	def sortkey(self):
		# the week profile comes before the days of its week
		return (self.day, 0 if self.week else 1, self.extra)

	def label(self):
		if self.week:
			end = self.day + timedelta(days=6)
			return f"Week {self.day.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
		s = self.day.strftime("%a %d %b %Y")
		return f"{s} ({self.extra})" if self.extra else s

def parsename(name):
	"""the Entry for a file name, or None when it isn't a journal image"""
	m = NAMERE.match(name)
	if not m:
		return None
	try:
		d = date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
	except ValueError:
		return None
	return Entry(name, d, week=m.group(4) is not None, extra=m.group(5).lower())

class Journal:
	def __init__(self, dir):
		self.dir = os.path.abspath(dir)
		self.entries: list[Entry] = []
		self.cache = {}		# name -> {"mtime", "raw": [[text, conf]...]}
		self.load()

	def path(self, e: Entry, notes=False):
		return os.path.join(self.dir, e.notesname() if notes else e.name)

	def load(self):
		"""scan the directory again, keeping the OCR cache"""
		self.loadcache()
		entries = []
		for n in os.listdir(self.dir):
			e = parsename(n)
			if e is None:
				continue
			e.notes = self.readnotes(e)
			e.tags = self.tagsof(e)
			entries.append(e)
		entries.sort(key=Entry.sortkey)
		self.entries = entries

	# ---- notes ----
	def readnotes(self, e):
		try:
			with open(self.path(e, notes=True), encoding="utf-8") as f:
				return f.read()
		except FileNotFoundError:
			return ""

	def savenotes(self, e, text):
		"""write the notes of e; empty notes remove the file"""
		p = self.path(e, notes=True)
		if text.strip() == "":
			if os.path.exists(p):
				os.remove(p)
		else:
			tmp = p + ".tmp"
			with open(tmp, "w", encoding="utf-8") as f:
				f.write(text)
			os.replace(tmp, p)
		e.notes = text

	# ---- tags ----
	def loadcache(self):
		try:
			with open(os.path.join(self.dir, TAGSFILE), encoding="utf-8") as f:
				c = json.load(f)
			self.cache = c.get("images", {}) if c.get("version") == TAGSVERSION else {}
		except (FileNotFoundError, ValueError, AttributeError):
			self.cache = {}

	def savecache(self):
		p = os.path.join(self.dir, TAGSFILE)
		tmp = p + ".tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			json.dump({"version": TAGSVERSION, "images": self.cache}, f, ensure_ascii=False, indent=0)
		os.replace(tmp, p)

	def mtime(self, e):
		try:
			return os.path.getmtime(self.path(e))
		except OSError:
			return None

	def needsocr(self, e):
		c = self.cache.get(e.name)
		return c is None or c.get("mtime") != self.mtime(e)

	def tagsof(self, e):
		c = self.cache.get(e.name)
		return cleantags(c["raw"]) if c else []

	def settext(self, e, raw):
		"""record the OCR results [(text, confidence)...] for e"""
		self.cache[e.name] = {"mtime": self.mtime(e), "raw": [[t, round(float(c), 3)] for t, c in raw]}
		e.tags = cleantags(self.cache[e.name]["raw"])

	def forget(self, e):
		"""drop the tags of e, so they are read again"""
		self.cache.pop(e.name, None)
		e.tags = []

	# ---- navigation ----
	def index(self, e):
		for i, x in enumerate(self.entries):
			if x.name == e.name:
				return i
		return -1

	def find(self, name):
		for x in self.entries:
			if x.name == name:
				return x
		return None

	def nearest(self, d, entries=None):
		"""the first entry of day d, or the closest one after it, or the last"""
		entries = self.entries if entries is None else entries
		best = None
		for x in entries:
			if x.day >= d and not x.week:
				return x
			best = x
		for x in entries:
			if x.day >= d:
				return x
		return best

	def weekof(self, e):
		"""the week profile for the week of day entry e, or None"""
		start = weekstart(e.day)
		for x in self.entries:
			if x.week and start - timedelta(days=1) <= x.day <= start + timedelta(days=1):
				return x
		return None

	def daysof(self, w):
		"""the days of week profile w"""
		return [x for x in self.entries if not x.week and w.day <= x.day < w.day + timedelta(days=7)]

	def days(self):
		return {x.day for x in self.entries}

def weekstart(d):
	"""the Sunday that starts the week of d, as the week profiles"""
	return d - timedelta(days=(d.weekday() + 1) % 7)

def groupkeys(e):
	"""the year, month and week groups of entry e, as [(key, label)...].
	A week profile goes in the week it starts, and a week that spans two
	months is shown in both, with the days of each."""
	y, mo = e.day.year, e.day.month
	w = weekstart(e.day)
	return [(("y", y), str(y)),
		(("m", y, mo), e.day.strftime("%B")),
		(("w", y, mo, w), f"Week {w.strftime('%d %b')}")]

def defaultjournals():
	"""journal directories found where they usually are: /u/trade/DayJournal*
	and ~/u/trade/DayJournal*"""
	import glob
	found = []
	for base in ("/u/trade", os.path.expanduser("~/u/trade")):
		for d in sorted(glob.glob(os.path.join(base, "DayJournal*"))):
			d = os.path.realpath(d)
			if os.path.isdir(d) and d not in found:
				found.append(d)
	return found
