#
# adding a capture to the journal: guess its date from the dates written in
# the image (read with the OCR), in its file name and the file's own date,
# let the user confirm or change it, and copy it with the right name.
#
import os
import re
import shutil
from collections import Counter
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
	QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout
)

from journal import parsename
from ocrworker import OCRWorker

IMAGEEXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff")
MONTHS = {"ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "may": 5, "jun": 6,
	"jul": 7, "ago": 8, "aug": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12, "dec": 12}
MON = "(" + "|".join(MONTHS) + r")[a-z]*\.?"
YMD = re.compile(r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)")	# 2026-10-14
YYMMDD = re.compile(r"(?<!\d)(\d{2})-(\d{2})-(\d{2})(?!\d)")		# 26-10-14, as in the charts
DMY = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?!\d)")	# 14/10/2026
DMONY = re.compile(r"(?<!\d)(\d{1,2})\s+(?:de\s+)?" + MON + r"(?:\s+(?:de\s+)?(\d{4}))?", re.IGNORECASE)	# 14 oct 2026
# Oct 14, 2026; not "mar", which is also Tuesday in Spanish (mar 26-10-13)
MONDY = re.compile(r"\b" + MON.replace("|mar|", "|") + r"\s+(\d{1,2})(?:,?\s+(\d{4}))?(?![\d.,-])", re.IGNORECASE)

def isimage(path):
	return path.lower().endswith(IMAGEEXTS)

def mkdate(y, m, d):
	y = int(y)
	if y < 100:
		y += 2000
	try:
		x = date(y, int(m), int(d))
	except ValueError:
		return None
	return x if 2000 <= x.year <= 2099 else None

def datesin(texts, year=None):
	"""the dates written in texts, with how many times each one is there.
	year is used for dates written without one."""
	year = year or date.today().year
	found = Counter()
	for t in texts:
		ds = []
		for m in YMD.finditer(t):
			ds.append(mkdate(*m.groups()))
		for m in YYMMDD.finditer(t):
			ds.append(mkdate(*m.groups()))
		for m in DMY.finditer(t):
			ds.append(mkdate(m.group(3), m.group(2), m.group(1)))
		for m in DMONY.finditer(t):
			ds.append(mkdate(m.group(3) or year, MONTHS[m.group(2).lower()[:3]], m.group(1)))
		for m in MONDY.finditer(t):
			ds.append(mkdate(m.group(3) or year, MONTHS[m.group(1).lower()[:3]], m.group(2)))
		found.update(d for d in ds if d is not None)
	return found

def filedate(path):
	"""when the file was made (or last changed, when the system doesn't keep that)"""
	st = os.stat(path)
	t = getattr(st, "st_birthtime", None) or st.st_mtime
	return datetime.fromtimestamp(t).date()

def guess(path, raw=None, today=None):
	"""the date and kind (week profile or not) of the capture at path, and the
	dates that were considered: [(date, where)...], best first. raw is what
	the OCR read in the image, [[text, confidence]...], None if not read yet.

	Charts show the days before the one they are about too, and sometimes the
	next ones on the axis, so the date taken from the image is the last one
	not after the day the capture was made (a week profile made on Sunday shows
	the Monday after). Captures made on a weekend are week profiles."""
	today = today or date.today()
	fd = filedate(path)
	limit = fd + timedelta(days=2 if fd.weekday() == 5 else 1)
	inimage = datesin([t for t, _ in raw or []], fd.year)
	inname = datesin([os.path.basename(path)], fd.year)
	cands = []
	ok = [d for d in inimage if d <= limit]
	if ok:
		n = inimage[max(ok)]
		cands.append((max(ok), f"in the image ({n} time{'s' if n > 1 else ''}), the last day"))
	for d, n in inimage.most_common():
		if d <= today + timedelta(days=7):
			cands.append((d, f"in the image ({n} time{'s' if n > 1 else ''})"))
	for d in inname:
		cands.append((d, "in the file name"))
	cands.append((fd, "the day the file was made"))
	seen = set()
	cands = [(d, w) for d, w in cands if not (d in seen or seen.add(d))]
	name = os.path.basename(path).lower()
	week = any(w in name for w in ("week", "prof", "semana")) or fd.weekday() >= 5
	best = cands[0][0]
	if week:
		best = weekname(fd if fd.weekday() >= 5 else best)
	return best, week, cands

def weekname(d):
	"""the date in the name of the week profile for the week of d, or for the week
	starting the next Monday when d is a weekend day: the Sunday before that week"""
	if d.weekday() == 6:
		return d
	if d.weekday() == 5:
		return d + timedelta(days=1)
	return d - timedelta(days=d.weekday() + 1)

def savecapture(journal, src, name):
	"""copy the image at src into the journal as name, as a PNG"""
	dst = os.path.join(journal.dir, name)
	if os.path.exists(dst):
		raise OSError(f"{name} is already there")
	tmp = dst + ".tmp"
	if src.lower().endswith(".png"):
		shutil.copy2(src, tmp)
	else:
		img = QImage(src)
		if img.isNull() or not img.save(tmp, "PNG"):
			raise OSError(f"can't convert {os.path.basename(src)} to PNG")
	os.replace(tmp, dst)
	return dst

def injournal(journal, src):
	"""whether src is already one of the images of the journal"""
	return (os.path.dirname(os.path.abspath(src)) == journal.dir and
		parsename(os.path.basename(src)) is not None)

class CaptureDialog(QDialog):
	"""asks for the date of a capture being added; the OCR reads the dates
	written in it meanwhile. raw has what it read, if it finished."""
	def __init__(self, journal, src, parent=None):
		super().__init__(parent)
		self.journal = journal
		self.src = src
		self.raw = None
		self.touched = False	# the user changed the date or kind
		self.setting = False
		self.setWindowTitle("Add Capture")
		lay = QVBoxLayout(self)
		pv = QLabel()
		pm = QPixmap(src)
		if not pm.isNull():
			pv.setPixmap(pm.scaled(560, 340, Qt.AspectRatioMode.KeepAspectRatio,
				Qt.TransformationMode.SmoothTransformation))
		pv.setAlignment(Qt.AlignmentFlag.AlignCenter)
		lay.addWidget(pv)
		form = QFormLayout()
		srcl = QLabel(os.path.basename(src))
		srcl.setToolTip(src)
		form.addRow("Capture:", srcl)
		self.cands = QComboBox()
		self.cands.setToolTip("the dates found for this capture; pick one to use it")
		self.cands.activated.connect(self.candpicked)
		form.addRow("Dates found:", self.cands)
		self.dateedit = QDateEdit()
		self.dateedit.setCalendarPopup(True)
		self.dateedit.setDisplayFormat("ddd d MMM yyyy")
		self.dateedit.dateChanged.connect(self.datechanged)
		form.addRow("Date:", self.dateedit)
		self.weekbox = QCheckBox("Week profile")
		self.weekbox.setToolTip("a week profile is named on the Sunday before its week")
		self.weekbox.toggled.connect(self.weektoggled)
		form.addRow("", self.weekbox)
		self.namel = QLabel()
		form.addRow("Saved as:", self.namel)
		lay.addLayout(form)
		self.status = QLabel("Reading the dates in the image…")
		self.status.setStyleSheet("color: gray")
		lay.addWidget(self.status)
		self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
		self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add")
		self.buttons.accepted.connect(self.accept)
		self.buttons.rejected.connect(self.reject)
		lay.addWidget(self.buttons)
		self.setguess()
		self.ocr = OCRWorker("", [(src, src)], self)
		self.ocr.tagged.connect(self.tagged)
		self.ocr.failed.connect(self.ocrfailed)
		self.ocr.finished.connect(self.ocrdone)
		self.ocr.start()

	def setguess(self):
		d, week, cands = guess(self.src, self.raw)
		self.candlist = cands
		self.cands.clear()
		for c, where in cands:
			self.cands.addItem(f"{c:%a %d %b %Y} — {where}")
		if not self.touched:
			self.setting = True
			self.weekbox.setChecked(week)
			self.dateedit.setDate(QDate(d.year, d.month, d.day))
			self.setting = False
		self.updatename()

	def tagged(self, _dir, _name, raw):
		self.raw = raw
		self.setguess()
		n = len(datesin([t for t, _ in raw]))
		self.status.setText(f"{n} date{'s' if n != 1 else ''} found in the image." if n else "No dates found in the image.")

	def ocrfailed(self, _name, err):
		self.status.setText(f"Can't read the image: {err}")

	def ocrdone(self):
		if self.raw is None and self.status.text().startswith("Reading"):
			self.status.setText("The image could not be read.")

	def candpicked(self, i):
		if 0 <= i < len(self.candlist):
			d = self.candlist[i][0]
			if self.weekbox.isChecked():
				d = weekname(d)
			self.touched = True
			self.dateedit.setDate(QDate(d.year, d.month, d.day))

	def datechanged(self, _qd):
		if not self.setting:
			self.touched = True
		self.updatename()

	def weektoggled(self, on):
		if not self.setting:
			self.touched = True
			d = self.date()
			if on and d.weekday() != 6:
				self.setting = True
				d = weekname(d)
				self.dateedit.setDate(QDate(d.year, d.month, d.day))
				self.setting = False
		self.updatename()

	def date(self):
		return self.dateedit.date().toPython()

	def week(self):
		return self.weekbox.isChecked()

	def name(self):
		return self.journal.newname(self.date(), self.week())

	def updatename(self):
		n = self.name()
		self.namel.setText(n or "no more letters left for that day")
		self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(n is not None)

	def done(self, r):
		self.ocr.stop()
		super().done(r)
