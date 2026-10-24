#
# a day journal: a directory of chart snapshots named dayYYMMDD.png (a day)
# and dayYYMMDDweekprof.png (the week profile). Weeks start on Monday; a
# week profile dated a Sunday is for the week that starts the day after,
# otherwise it is for the week of its date. A letter after the date (day260916b.png) is another snapshot of
# the same day. Each image may have notes in a .txt file with its name, and
# the words read from it by OCR are its tags, cached in TAGSFILE. What is
# drawn on it (see drawing.py) is kept in a DRAWEXT file with its name.
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
DRAWEXT = ".drw"

@dataclass
class Entry:
	"""one image of the journal"""
	name: str			# file name, day261014.png
	day: date
	week: bool = False	# a week profile
	extra: str = ""		# the letter of a second snapshot of the day
	tags: list[str] = field(default_factory=list)
	notes: str = ""
	drawtext: str = ""	# what is written in its text boxes

	def base(self):
		return os.path.splitext(self.name)[0]

	def notesname(self):
		return self.base() + ".txt"

	def drawname(self):
		return self.base() + DRAWEXT

	def weekmonday(self):
		"""the Monday of the week this entry is about"""
		if self.week and self.day.weekday() == 6:
			return weekstart(self.day + timedelta(days=1))	# a Sunday: the next week
		return weekstart(self.day)

	def groupday(self):
		"""the date used to place the entry: a week profile goes with
		the Monday of its week"""
		return self.weekmonday() if self.week else self.day

	def sortkey(self):
		# the week profile comes before the days of its week
		return (self.groupday(), 0 if self.week else 1, self.extra)

	def label(self):
		if self.week:
			start = self.weekmonday()
			end = start + timedelta(days=6)
			return f"Week {start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
		s = self.day.strftime("%a %d %b %Y")
		return f"{s} ({self.extra})" if self.extra else s

def drawtext(data):
	"""the words written in the text boxes and rectangle labels of a drawing"""
	return " ".join(str(s.get("text") or s.get("label") or "") for s in (data or {}).get("shapes", [])
		if isinstance(s, dict) and s.get("kind") in ("text", "rect"))

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

def capturename(d, week=False, letter=""):
	"""the file name of a capture: day261014.png, day261011weekprof.png, day261014b.png"""
	return f"day{d:%y%m%d}{'weekprof' if week else ''}{letter}.png"

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
			e.drawtext = drawtext(self.readdrawing(e))
			e.tags = self.tagsof(e)
			entries.append(e)
		entries.sort(key=Entry.sortkey)
		self.entries = entries

	def newname(self, d, week=False):
		"""the name for one more capture of day d (or the week profile dated d):
		the plain name for the first one, then the letters after the last
		one there (day261014.png, day261014b.png, day261014c.png...).
		None when the letters run out."""
		used = [x.extra or "a" for x in self.entries if x.day == d and x.week == week]
		if not used:
			return capturename(d, week)
		last = max(used)
		if last >= "z":
			return None
		return capturename(d, week, chr(ord(last) + 1))

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

	# ---- drawings ----
	def readdrawing(self, e):
		"""the drawing of e as saved, or None"""
		try:
			with open(os.path.join(self.dir, e.drawname()), encoding="utf-8") as f:
				d = json.load(f)
			return d if isinstance(d, dict) else None
		except (FileNotFoundError, ValueError):
			return None

	def savedrawing(self, e, data):
		"""write the drawing of e; None or no shapes removes the file"""
		p = os.path.join(self.dir, e.drawname())
		if not data or not data.get("shapes"):
			if os.path.exists(p):
				os.remove(p)
		else:
			tmp = p + ".tmp"
			with open(tmp, "w", encoding="utf-8") as f:
				json.dump(data, f, ensure_ascii=False, indent=1)
			os.replace(tmp, p)
		e.drawtext = drawtext(data)

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
			if x.week and x.weekmonday() == start:
				return x
		return None

	def daysof(self, w):
		"""the days of week profile w"""
		start = w.weekmonday()
		return [x for x in self.entries if not x.week and weekstart(x.day) == start]

	def days(self):
		return {x.day for x in self.entries}

def weekstart(d):
	"""the Monday that starts the week of d"""
	return d - timedelta(days=d.weekday())

def groupkeys(e):
	"""the year, month and week groups of entry e, as [(key, label)...].
	A week profile goes in the week it is for, in the month of its Monday,
	and a week that spans two months is shown in both, with the days of each."""
	d = e.groupday()
	y, mo = d.year, d.month
	w = weekstart(d)
	return [(("y", y), str(y)),
		(("m", y, mo), d.strftime("%B")),
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
