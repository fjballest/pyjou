#
# the main window: the images of a journal on the left, found by a search
# and a calendar, and the image with its tags and notes on the right
#
import copy
import html
from types import SimpleNamespace
from datetime import date, timedelta
import json
import os
import sys
import zipfile

from PySide6.QtCore import QDate, QEvent, QFileSystemWatcher, QMimeData, QPoint, QPointF, QRect, QRectF, QSettings, QSize, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import (
	QAction, QBrush, QColor, QCursor, QDesktopServices, QDrag, QFont, QIcon, QKeySequence, QPainter, QPalette, QPen, QPixmap, QPolygonF, QTextCharFormat
)
from PySide6.QtWidgets import (
	QAbstractItemView, QApplication, QCalendarWidget, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
	QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
	QProgressBar, QSplitter, QStackedWidget, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableView, QToolTip, QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem,
	QVBoxLayout, QWidget, QDialogButtonBox
)

from capture import IMAGEEXTS, CaptureDialog, injournal, isimage, savecapture, weekname
from journal import Journal, defaultjournals, setdrawing, groupkeys, tradedir, weekno
from ocrworker import startocr
from search import Search
from drawbar import DrawBar
from viewer import ImageView, renderfile
from weekprof import Profiles, dayprofile, matches, partial, similarity
from weekedit import ProfileEditor
from rail import withrail
import winlayout
from shiboken6 import isValid
from winlayout import windowmenu
from version import VERSION
from helpwin import addtopics, showguide
import m15
import news
import indicators
import dataview
from dataview import ChartItem, DataPanel, Geom, drawpts, mapdrawing, render, widened
import tempfile

RECENTMAX = 10
CLIPMIME = "application/x-pyjou-capture"	# {"dir", "name", "cut"} of a capture cut or copied
SAVEDELAY = 800		# ms after the last key before notes are saved
SEARCHTIP = ("<p>Show the images whose tags or notes have these words, ignoring case.</p>"
	"<p>Words one after another must all be there, <b>|</b> means or, <b>!</b> means not, "
	"and parentheses group: <code>(a b) | !(c d)</code>.</p>"
	"<p>A final lowercase s is optional (EQL finds EQLs) and <b>*</b> matches any letters "
	"within a word (EQ*). Esc empties the search.</p>"
	"<p>A word also finds its aliases, kept in the journal's aliases.txt (Edit ▸ Aliases…): "
	"with <code>news: NFP, PPI, CPI</code>, news also finds NFP, PPI and CPI.</p>")

ALIASHELP = ("One word per line, then : and the words it also finds, separated by commas. "
	"Case and a final s don't matter. # starts a comment.")

def settings():
	return QSettings("pyjou", "DayJournal")

# where temporary directories are made: /tmp, and /var/folders on macOS
TEMPDIRS = ("/tmp", "/var/tmp", "/var/folders")

def istemp(path):
	"""whether path is in a temporary directory, as the tests make"""
	import tempfile
	p = os.path.realpath(path)
	for t in {os.path.realpath(t) for t in TEMPDIRS + (tempfile.gettempdir(),)}:
		if p == t or p.startswith(t.rstrip(os.sep) + os.sep):
			return True
	return False

def recentjournals():
	"""the journals used last, leaving out those in temporary directories"""
	v = settings().value("recent", [])
	if isinstance(v, str):
		v = [v]
	return [p for p in (v or []) if p and not istemp(p)]

def addrecent(path):
	path = os.path.abspath(path)
	if istemp(path):
		return
	l = [path] + [p for p in recentjournals() if p != path]
	settings().setValue("recent", l[:RECENTMAX])

class SearchEdit(QLineEdit):
	def keyPressEvent(self, ev):
		if ev.key() == Qt.Key.Key_Escape and self.text():
			self.clear()
			return
		super().keyPressEvent(ev)

windows = []	# the windows made with New Window, so they are kept
following = False	# synced windows are being moved: they don't move others

DRAGMIME = "application/x-pyjou-drag"	# a capture dragged from the list
NAMESROLE = Qt.ItemDataRole.UserRole + 3	# the captures of a day row, in order

MATCHCOLOR = QColor("#e53935")
DATAPFX = "m15:"	# a week of the m15 data in Match Week: m15:2026-11-16
DRAWPFX = "m15draw:"	# the drawing of a data chart in pending: m15draw:w:2026-11-16:15 (its time frame)

def drawprofile(painter, box, pts, pal, selected=False, upto=None):
	"""draw week profile pts in box, with the midnights faint behind it; the
	part before day upto (a match) in red"""
	x = lambda t: box.left() + (t + 0.3) / 5.3 * box.width()
	y = lambda v: box.bottom() - v * box.height()
	painter.save()
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	painter.setPen(QPen(pal.color(QPalette.ColorRole.Mid), 0.5, Qt.PenStyle.DotLine))
	for d in range(6):	# midnights, Monday to Saturday
		painter.drawLine(QPointF(x(d), box.top()), QPointF(x(d), box.bottom()))
	line = QPolygonF([QPointF(x(t), y(v)) for t, v in pts])
	painter.setPen(QPen(pal.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Highlight), 1.5))
	if upto is None:
		painter.drawPolyline(line)
	else:	# the rest after the match, then the match over it
		painter.save()
		painter.setClipRect(QRectF(x(upto), box.top() - 2, box.right() - x(upto) + 4, box.height() + 4))
		painter.drawPolyline(line)
		painter.restore()
		painter.setClipRect(QRectF(box.left() - 4, box.top() - 2, x(upto) - box.left() + 4, box.height() + 4))
		painter.setPen(QPen(MATCHCOLOR, 2))
		painter.drawPolyline(line)
	painter.restore()

class MatchDialog(QDialog):
	"""the weeks like the one in progress, best first: click one to show it"""
	def __init__(self, win, src, found):
		super().__init__(win)
		self.win = win
		self.setWindowTitle("Match Week")
		self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
		lay = QVBoxLayout(self)
		lay.addWidget(QLabel(f"Weeks like the week of {win.matchmonday(src):%d %b %Y} so far, "
			f"to {daytime(win.matchend)} (in red):"))
		self.lst = QListWidget()
		self.lst.setItemDelegate(MatchDelegate(self.lst, win))
		for s, name in found:
			data = " (m15 data)" if name.startswith(DATAPFX) else ""
			it = QListWidgetItem(f"Week {win.matchmonday(name):%d %b %Y}{data}   {s:.0%}")
			it.setData(Qt.ItemDataRole.UserRole, name)
			self.lst.addItem(it)
		self.lst.setCurrentRow(-1)
		self.lst.currentItemChanged.connect(self.picked)
		self.lst.itemClicked.connect(lambda it: self.picked(it, None))	# the row current at first too
		lay.addWidget(self.lst)
		if not found:
			lay.addWidget(QLabel("No full week with a profile to compare it with."))
		self.resize(420, 360)
		self.finished.connect(lambda _: win.clearmatch())

	def picked(self, it, _prev):
		if it is not None:
			self.win.showmatch(it.data(Qt.ItemDataRole.UserRole))

class MatchDelegate(QStyledItemDelegate):
	"""a row of the match window: the week, how well it matches, and its profile"""
	def __init__(self, lst, win):
		super().__init__(lst)
		self.win = win

	def sizeHint(self, option, index):
		s = super().sizeHint(option, index)
		s.setHeight(max(s.height(), 2 * option.fontMetrics.height() + 8))
		return s

	def paint(self, painter, option, index):
		super().paint(painter, option, index)
		pts = self.win.profileof(index.data(Qt.ItemDataRole.UserRole))
		r = option.rect
		box = QRectF(r.right() - 150, r.top() + 4, 140, r.height() - 8)
		if pts:
			drawprofile(painter, box, pts, option.palette,
				bool(option.state & QStyle.StateFlag.State_Selected), self.win.matchend)

class MatchDayDialog(QDialog):
	"""the days of the data like day d up to a time, best first: click one to show it"""
	def __init__(self, win, d, cap=None):
		super().__init__(win)
		self.win, self.d, self.cap = win, d, cap
		self.setWindowTitle("Match Day")
		self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
		lay = QVBoxLayout(self)
		src = QHBoxLayout()
		src.addWidget(QLabel(f"Days like {d:%a %d %b %Y}, from"))
		self.source = QComboBox()
		data = win.data
		if cap:
			self.source.addItem("the capture, so far", "capture")
		if d in data.days():
			self.source.addItem("the m15 data", "data")
		self.source.currentIndexChanged.connect(self.refill)
		src.addWidget(self.source)
		src.addStretch()
		lay.addLayout(src)
		top = QHBoxLayout()
		top.addWidget(QLabel("up to"))
		self.until = QComboBox()
		end = data.end("d", d) or m15.DAYEND
		h = m15.DAYSTART + 1
		while h <= end + 1e-9:
			self.until.addItem(f"{int(h % 24):02d}:{int(round(h % 1 * 60)):02d}", h)
			h += 0.5
		if self.until.count() == 0 or self.until.itemData(self.until.count() - 1) < end - 1e-9:
			self.until.addItem(f"{int(end % 24):02d}:{int(round(end % 1 * 60)):02d}", end)
		self.until.setCurrentIndex(self.until.count() - 1)
		self.until.setToolTip("New York time; the part of the day compared (in red)")
		self.until.currentIndexChanged.connect(self.refill)
		top.addWidget(self.until)
		top.addWidget(QLabel("(New York)"))
		top.addStretch()
		lay.addLayout(top)
		self.lst = QListWidget()
		self.lst.setItemDelegate(MatchDayDelegate(self.lst, self))
		self.lst.currentItemChanged.connect(self.picked)
		self.lst.itemClicked.connect(lambda it: self.picked(it, None))	# the row current at first too
		lay.addWidget(self.lst)
		self.none = QLabel("No other day of the data to compare it with.")
		lay.addWidget(self.none)
		self.resize(440, 420)
		self.refill()

	def refill(self):
		data, d = self.win.data, self.d
		if self.source.currentData() == "capture":
			pts = self.cap
			self.upto = pts[-1][0]
			self.until.setEnabled(False)
		else:
			self.upto = self.until.currentData()
			self.until.setEnabled(True)
			pts = data.profile("d", d, until=self.upto)
		others = {x: data.profile("d", x) for x in data.days() if x != d}
		others = {x: p for x, p in others.items() if p and p[-1][0] >= m15.DAYEND - 0.5}	# whole days
		found = []
		for x, p in others.items():
			s = similarity(pts, p) if pts else None
			if s is not None:
				found.append((s, x))
		found.sort(reverse=True)
		self.lst.blockSignals(True)
		self.lst.clear()
		for s, x in found[:12]:
			it = QListWidgetItem(f"{x:%a %d %b %Y}   {s:.0%}")
			it.setData(Qt.ItemDataRole.UserRole, x)
			self.lst.addItem(it)
		self.lst.setCurrentRow(-1)	# none picked yet, so any click picks
		self.lst.blockSignals(False)
		self.none.setVisible(not found)

	def picked(self, it, _prev):
		if it is not None:
			self.win.showday(it.data(Qt.ItemDataRole.UserRole))

class MatchDayDelegate(QStyledItemDelegate):
	"""a row of Match Day: the day, how well it matches, and its profile, the part compared in red"""
	def __init__(self, lst, dlg):
		super().__init__(lst)
		self.dlg = dlg

	def sizeHint(self, option, index):
		s = super().sizeHint(option, index)
		s.setHeight(max(s.height(), 2 * option.fontMetrics.height() + 8))
		return s

	def paint(self, painter, option, index):
		super().paint(painter, option, index)
		pts = self.dlg.win.data.profile("d", index.data(Qt.ItemDataRole.UserRole))
		r = option.rect
		box = QRectF(r.right() - 170, r.top() + 4, 160, r.height() - 8)
		if pts:
			drawpts(painter, box, "d", pts, option.palette,
				bool(option.state & QStyle.StateFlag.State_Selected), upto=self.dlg.upto)

def daytime(t):
	"""day t of a week profile (days from Monday 00:00) as 'Tue 04:00'"""
	d = int(t // 1)
	h = round((t - d) * 24)
	if h == 24:
		d, h = d + 1, 0
	return f"{['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][(d + 1) % 7]} {h:02d}:00"

class RowDelegate(QStyledItemDelegate):
	"""draws a day row with several captures as its day and a compact chip
	for each capture (a, b, c...), the one shown highlighted"""
	def __init__(self, lst):
		super().__init__(lst)
		self.lst = lst

	def paint(self, painter, option, index):
		names = index.data(NAMESROLE) or []
		if len(names) < 2:
			super().paint(painter, option, index)
			self.paintprofile(painter, option, names)
			return
		opt = QStyleOptionViewItem(option)
		self.initStyleOption(opt, index)
		fm = opt.fontMetrics
		opt.rect = QRect(option.rect.left(), option.rect.top(), self.lst.labelwidth(fm, opt.text), option.rect.height())
		st = opt.widget.style() if opt.widget else QApplication.style()
		st.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
		win = self.lst.win
		pal = option.palette
		painter.save()
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		for name, r in self.lst.chiprects(option.rect, opt.text, names, fm):
			e = win.journal.find(name) if win.journal else None
			cur = win.current is not None and win.current.name == name
			if cur:
				painter.setPen(Qt.PenStyle.NoPen)
				painter.setBrush(pal.color(QPalette.ColorRole.Highlight))
			else:
				painter.setPen(QPen(pal.color(QPalette.ColorRole.Mid), 1))
				painter.setBrush(Qt.BrushStyle.NoBrush)
			painter.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
			if name == win.cutname:
				painter.setPen(QColor("gray"))
			else:
				painter.setPen(pal.color(QPalette.ColorRole.HighlightedText if cur else QPalette.ColorRole.Text))
			painter.drawText(r, Qt.AlignmentFlag.AlignCenter, win.chiplabel(e) if e else "?")
		painter.restore()
		self.paintprofile(painter, option, names)

	def sizeHint(self, option, index):
		"""a week profile's row is taller, for its profile"""
		s = super().sizeHint(option, index)
		names = index.data(NAMESROLE) or []
		win = self.lst.win
		e = win.journal.find(names[0]) if win.journal and names else None
		if e is not None and e.week:
			s.setHeight(max(s.height(), 2 * option.fontMetrics.height() + 6))
		return s

	def paintprofile(self, painter, option, names):
		"""the profile of the week at the right of a week profile's row"""
		win = self.lst.win
		e = win.journal.find(names[0]) if win.journal and names else None
		if e is None or not e.week or win.profiles is None:
			return
		pts = win.profiles.get(e.name)
		win.profsave.start()
		r = option.rect
		w = min(90, r.width() // 3)
		box = QRectF(r.right() - w - 4, r.top() + 3, w, r.height() - 6)
		if not pts or box.height() < 6:
			return
		sel = option.state & QStyle.StateFlag.State_Selected
		pal = option.palette
		upto = None
		if win.matchsrc is not None and (e.name == win.matchsrc or e.name in win.matching):
			upto = win.matchend
			if e.name in win.matching:	# how well it matches, left of the profile
				painter.save()
				painter.setPen(pal.color(QPalette.ColorRole.HighlightedText if sel else QPalette.ColorRole.Text))
				painter.drawText(QRectF(box.left() - 48, r.top(), 44, r.height()),
					Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{win.matching[e.name]:.0%}")
				painter.restore()
		drawprofile(painter, box, pts, pal, sel, upto)

class CaptureList(QTreeWidget):
	"""the list; its captures can be dragged, to a day of the calendar to
	move them there, before or after another capture of their day to
	reorder them, or to another program or window as image files"""
	def __init__(self, win):
		super().__init__()
		self.win = win
		self.dropline = None	# where a capture dropped goes: a y, or (x, top, bottom) in a row
		self.pick = None		# the capture of the row clicked
		self.pressed = None		# the capture the mouse went down on, to drag it
		self.setItemDelegate(RowDelegate(self))
		self.setDragEnabled(True)
		self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
		self.setAcceptDrops(True)
		self.viewport().setAcceptDrops(True)

	@staticmethod
	def labelwidth(fm, label):
		"""the width of a row's label, the same for all days so the chips line up"""
		return max(fm.horizontalAdvance(label), fm.horizontalAdvance("Wed 30")) + 14

	def chiprects(self, rect, label, names, fm):
		"""[(name, QRect)] of the chips of a day row at rect"""
		win = self.win
		x = rect.left() + self.labelwidth(fm, label) + 4
		out = []
		for n in names:
			e = win.journal.find(n) if win.journal else None
			w = fm.horizontalAdvance(win.chiplabel(e) if e else "?") + 14
			out.append((n, QRect(x, rect.top() + 2, w, rect.height() - 4)))
			x += w + 4
		return out

	def chips(self, it):
		"""[(name, QRect)] of the chips of row it, in viewport coordinates;
		empty for a row with one capture, or a group"""
		names = it.data(0, NAMESROLE) if it is not None else None
		if not names or len(names) < 2:
			return []
		return self.chiprects(self.visualItemRect(it), it.text(0), names, self.fontMetrics())

	def chiprect(self, name):
		"""where the chip of capture name is, or the rect of its row"""
		it = self.win.items.get(name)
		for n, r in self.chips(it):
			if n == name:
				return r
		return self.visualItemRect(it) if it is not None else QRect()

	def captureat(self, pos):
		"""the name of the capture at pos: its chip, or the only one of its row"""
		it = self.itemAt(pos)
		names = it.data(0, NAMESROLE) if it is not None else None
		if not names:
			return None
		if len(names) == 1:
			return names[0]
		for n, r in self.chips(it):
			if r.contains(pos):
				return n
		return None

	def mousePressEvent(self, ev):
		pos = ev.position().toPoint()
		n = self.captureat(pos)
		self.pick = self.pressed = n
		super().mousePressEvent(ev)
		self.pick = None
		w = self.win
		if n and ev.button() == Qt.MouseButton.LeftButton and (w.current is None or w.current.name != n):
			e = w.journal.find(n) if w.journal else None
			if e is not None:
				w.show_(e)

	def keyPressEvent(self, ev):
		"""left and right go along the captures of a day row"""
		it = self.currentItem()
		names = it.data(0, NAMESROLE) if it is not None else None
		w = self.win
		if names and len(names) > 1 and ev.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) \
				and w.current is not None and w.current.name in names:
			i = names.index(w.current.name) + (1 if ev.key() == Qt.Key.Key_Right else -1)
			if 0 <= i < len(names):
				w.show_(w.journal.find(names[i]))
				return
		super().keyPressEvent(ev)

	def viewportEvent(self, ev):
		if ev.type() == QEvent.Type.ToolTip:
			pos = ev.pos()
			it = self.itemAt(pos)
			if self.chips(it):
				n = self.captureat(pos)
				e = self.win.journal.find(n) if n and self.win.journal else None
				if e is not None:
					QToolTip.showText(ev.globalPos(), e.name + ("\n" + self.win.itemtip(e) if self.win.itemtip(e) else ""), self)
				else:
					QToolTip.hideText()
				return True
		return super().viewportEvent(ev)

	def startDrag(self, actions):
		md = self.win.dragdata(self.pressed or self.currentItem())
		if md is None:
			return
		drag = QDrag(self)
		drag.setMimeData(md)
		drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, Qt.DropAction.CopyAction)

	def droporder(self, md, pos):
		"""the names of the captures of its day in the order they get when
		capture md is dropped at pos, and the y where it goes; None when it
		goes nowhere, or stays where it is"""
		e = self.win.owndrag(md)
		it = self.itemAt(pos)
		chips = self.chips(it)
		name = None
		for n, r in chips:	# the chip under pos, or the nearest one
			if name is None or abs(r.center().x() - pos.x()) < abs(rr.center().x() - pos.x()):
				name, rr = n, r
		t = self.win.journal.find(name) if e is not None and name else None
		if t is None or t.day != e.day or t.week != e.week:
			return None
		r = rr
		after = pos.x() >= r.center().x()
		old = [x.name for x in self.win.journal.capturesof(e.day, e.week)]
		order = [n for n in old if n != e.name]
		if t.name != e.name:
			order.insert(order.index(t.name) + after, e.name)
		else:
			order = old
		if order == old:
			return None
		return order, (r.right() + 2 if after else r.left() - 2, r.top(), r.bottom())

	def dragEnterEvent(self, ev):
		if self.win.owndrag(ev.mimeData()) is None:
			self.win.dragEnterEvent(ev)	# images from elsewhere are added
			return
		ev.setDropAction(Qt.DropAction.MoveAction)
		ev.accept()	# it may come to a capture of its day

	def dragMoveEvent(self, ev):
		if self.win.owndrag(ev.mimeData()) is None:
			self.win.dragMoveEvent(ev)
			return
		o = self.droporder(ev.mimeData(), ev.position().toPoint())
		self.setdropline(o[1] if o else None)
		if o is None:
			ev.ignore()
			return
		ev.setDropAction(Qt.DropAction.MoveAction)
		ev.accept()

	def dragLeaveEvent(self, ev):
		self.setdropline(None)

	def dropEvent(self, ev):
		self.setdropline(None)
		if self.win.owndrag(ev.mimeData()) is None:
			self.win.dropEvent(ev)
			return
		o = self.droporder(ev.mimeData(), ev.position().toPoint())
		if o is None:
			ev.ignore()
			return
		ev.setDropAction(Qt.DropAction.MoveAction)
		ev.accept()
		e = self.win.owndrag(ev.mimeData())
		QTimer.singleShot(0, lambda: self.win.reorder(o[0], e.name))	# after the drop is over

	def setdropline(self, y):
		if y != self.dropline:
			self.dropline = y
			self.viewport().update()

	def paintEvent(self, ev):
		super().paintEvent(ev)
		if self.dropline is not None:
			p = QPainter(self.viewport())
			p.setPen(QPen(self.palette().color(QPalette.ColorRole.Highlight), 2))
			if isinstance(self.dropline, tuple):
				x, y0, y1 = self.dropline
				p.drawLine(x, y0, x, y1)
			else:
				p.drawLine(0, self.dropline, self.viewport().width(), self.dropline)
			p.end()

def calendardate(cal, pos):
	"""the date of the calendar cell at pos of its view's viewport, or None"""
	v = cal.findChild(QTableView, "qt_calendar_calendarview")
	if v is None:
		return None
	i = v.indexAt(pos)
	m = v.model()
	if not i.isValid():
		return None
	first = None	# where the 1st of the month shown is
	for r in range(min(4, m.rowCount())):
		for c in range(m.columnCount()):
			if m.data(m.index(r, c)) == 1:
				first = (r, c)
				break
		if first:
			break
	if first is None or not isinstance(m.data(i), int):
		return None
	off = 7 * (i.row() - first[0]) + i.column() - first[1]
	return date(cal.yearShown(), cal.monthShown(), 1) + timedelta(days=off)

class MainWindow(QMainWindow):
	def __init__(self, path=None):
		super().__init__()
		if news.FETCHED is None:	# the news dates fetched, for every journal
			news.FETCHED = os.path.join(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation),
				"DayJournal", "news.txt")
		if indicators.DIR is None:	# the Pine indicators imported, for every journal
			indicators.setup(os.path.join(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation),
				"DayJournal", "indicators"), settings)
		self.dataoverlay = None	# what the indicators draw on the data chart
		self.datapending = False	# and whether runs for it are still to come
		indicators.runner().done.connect(self.indicatorsdone)
		self.journal = None
		self.child = False		# made by New Window: it can be synced
		self.current = None		# the Entry shown
		self.shown = []			# entries that pass the search, in order
		self.search = Search("")
		self.ocrworker = None
		self.ocrpending = []

		self.savetimer = QTimer(self, singleShot=True, interval=SAVEDELAY)
		self.savetimer.timeout.connect(self.savenotes)
		self.searchtimer = QTimer(self, singleShot=True, interval=250)
		self.searchtimer.timeout.connect(self.applysearch)
		self.reloadtimer = QTimer(self, singleShot=True, interval=1000)
		self.reloadtimer.timeout.connect(self.reload)
		self.watcher = QFileSystemWatcher(self)
		self.watcher.directoryChanged.connect(lambda _: self.reloadtimer.start())
		self.profiles = None	# the profiles of the weeks, found in their captures
		self.profsave = QTimer(self)	# saved a while after finding new ones
		self.profsave.setSingleShot(True)
		self.profsave.setInterval(3000)
		self.profsave.timeout.connect(lambda: self.profiles and self.profiles.save())
		self.matchsrc = None	# the week profile matched, its time up to which, and the others' scores
		self.matchend = None
		self.matching = {}
		self.adjuster = None	# the ProfileEditor while adjusting a week profile
		self.data = None		# the m15 data of the journal (m15.Data)
		self.datamode = False	# the data view is shown instead of the captures
		self.datakey = None		# ("w" or "d", date) shown in the data view
		self.datatf = 15		# the time frame of its charts, minutes
		self.lowdata = None		# the data of a time frame under m15, read when first needed
		self.datapath = None	# the chart shown, and its time frame
		self.datashowntf = 15
		self.datadir = tempfile.mkdtemp(prefix="dj-data-")	# where its charts are drawn
		self.datageom = None	# the Geom of the chart shown
		self.datazooms = {}		# (kind, date, tf) -> the part of the chart shown (see Geom.zoomed)
		self.panning = None		# dragging a zoomed data chart: see datapan

		self.pending = {}		# image name -> its drawing not saved yet (None: no drawings)
		self.mkactions()
		self.mkwidgets()
		self.mktoolbar()
		self.mkmenus()
		self.resize(1500, 950)
		self.updatetitle()
		for w, a, key in ((self.left, self.listact, "showlist"), (self.bottom, self.notespanelact, "shownotes")):
			if settings().value(key, True) in (False, "false"):
				self.showpanel(w, a, False)
		# captures dropped anywhere on the window are added
		self.setAcceptDrops(True)
		for w in (self.view, self.view.viewport(), self.notes):
			w.setAcceptDrops(False)

		if path is None:
			path = self.startjournal()
		if path:
			self.openjournal(path)

	# ---- building ----
	def mkaction(self, text, fn, icon=None, shortcut=None, tip=None):
		a = QAction(text, self)
		if icon is not None:
			a.setIcon(self.style().standardIcon(icon))
		if shortcut:
			a.setShortcut(QKeySequence(shortcut))
		if tip:
			a.setToolTip(tip)
			a.setStatusTip(tip)
		a.triggered.connect(lambda _=False: fn())
		return a

	def dupicon(self):
		"""two windows, one over the other, for New Window"""
		pm = QPixmap(36, 36)
		pm.fill(Qt.GlobalColor.transparent)
		p = QPainter(pm)
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		fg = self.palette().color(QPalette.ColorRole.WindowText)
		pen = QPen(fg, 2.5)
		p.setPen(pen)
		p.drawRoundedRect(QRectF(3, 3, 21, 17), 2, 2)
		p.fillRect(QRectF(3, 3, 21, 4), fg)
		p.setBrush(self.palette().color(QPalette.ColorRole.Window))
		p.drawRoundedRect(QRectF(12, 15, 21, 17), 2, 2)
		p.fillRect(QRectF(12, 15, 21, 4), fg)
		p.end()
		return QIcon(pm)

	def mkactions(self):
		S = QStyle.StandardPixmap
		self.openact = self.mkaction("&Open Journal…", self.choosejournal, S.SP_DirOpenIcon,
			QKeySequence.StandardKey.Open, "open a journal directory")
		self.saveact = self.mkaction("&Save Drawings", self.savedrawings, S.SP_DialogSaveButton,
			QKeySequence.StandardKey.Save, "save the drawings made")
		self.saveact.setIconText("Save")
		self.aliasact = self.mkaction("&Aliases…", self.editaliases, None, None,
			"words a search word also finds, like news: NFP, PPI, CPI")
		self.saveact.setEnabled(False)
		self.addact = self.mkaction("&Add Capture…", self.choosecaptures, None, "Ctrl+I",
			"add a capture to the journal; you can also drop it on the window")
		self.reloadact = self.mkaction("&Reload", self.reload, S.SP_BrowserReload,
			QKeySequence.StandardKey.Refresh, "look for new images and notes")
		self.prevact = self.mkaction("Previous", lambda: self.step(-1), S.SP_ArrowBack,
			"PgUp", "the previous image (PgUp)")
		self.nextact = self.mkaction("Next", lambda: self.step(1), S.SP_ArrowForward,
			"PgDown", "the next image (PgDown)")
		self.weekact = self.mkaction("Week", self.toggleweek, S.SP_FileDialogDetailedView,
			"Ctrl+W", "switch between a day and the profile of its week")
		self.todayact = self.mkaction("Last", lambda: self.jump(True), S.SP_MediaSkipForward,
			"Ctrl+End", "the last image")
		self.firstact = self.mkaction("First", lambda: self.jump(False), S.SP_MediaSkipBackward,
			"Ctrl+Home", "the first image")
		self.fitact = self.mkaction("Fit", lambda: self.datazoom(None) or self.view.fit(), None, "Ctrl+0", "fit the image in the window")
		self.realact = self.mkaction("Real Size", lambda: self.view.realsize(), None, "Ctrl+1", "show the image at its size")
		self.zoominact = self.mkaction("Zoom +", lambda: self.view.zoom(1.25), None,
			QKeySequence.StandardKey.ZoomIn, "zoom in")
		self.zoomoutact = self.mkaction("Zoom −", lambda: self.view.zoom(0.8), None,
			QKeySequence.StandardKey.ZoomOut, "zoom out")
		self.osviewact = self.mkaction("Open in Preview", self.osview, None, "Ctrl+Shift+O",
			"open the image with the system viewer")
		self.retagact = self.mkaction("Read Tags Again", self.retag, None, "Ctrl+T",
			"read the text of this image again to make its tags")
		self.retagallact = self.mkaction("Read All Tags Again", self.retagall, None, None,
			"read the text of every image again")
		self.findact = self.mkaction("&Search", self.find,
			None, QKeySequence.StandardKey.Find, "search the tags and notes")
		self.notesact = self.mkaction("Edit &Notes", self.editnotes, None, "Ctrl+N",
			"write notes for this image")
		self.listact = self.mkaction("Show &List", lambda: self.showpanel(self.left, self.listact), None,
			"Ctrl+Shift+L", "show or hide the list of images, the search and the calendar")
		self.notespanelact = self.mkaction("Show N&otes", lambda: self.showpanel(self.bottom, self.notespanelact),
			None, "Ctrl+Shift+N", "show or hide the tags and notes under the image")
		for a, text in ((self.listact, "List"), (self.notespanelact, "Notes")):
			a.setCheckable(True)
			a.setChecked(True)
			a.setIconText(text)
		self.newwinact = self.mkaction("&New Window", self.newwindow, None, "Ctrl+Alt+N",
			"open another window on this journal and image, to browse it or open another journal")
		self.newwinact.setIcon(self.dupicon())
		self.newwinact.setIconText("Window")
		self.syncact = self.mkaction("S&ync with Other Windows", self.syncchanged, None, None,
			"move with the main window (and the other synced ones) to the day or week shown, "
			"and show their crosshair here")
		self.syncact.setCheckable(True)
		self.syncact.setIconText("Sync")
		self.syncact.setVisible(False)	# only in the windows made with New Window
		self.exportselact = self.mkaction("&Export Selected…", lambda: self.export(False), None, "Ctrl+E",
			"save the capture selected, or those of the week, month or year selected, as PNGs with their drawings in a zip file")
		self.exportallact = self.mkaction("Export &All…", lambda: self.export(True), None, "Ctrl+Shift+E",
			"save the captures shown, as the search and the Days and Weeks boxes leave them, as PNGs with their drawings in a zip file")
		self.scaleact = self.mkaction("Scale &Panel…", self.scalepanel, None, "Ctrl+Shift+S",
			"scale one of two charts of a capture vertically, so its price levels match the other one")
		self.matchact = self.mkaction("&Match Week…", self.matchweek, None, "Ctrl+Shift+M",
			"compare the week profile shown, a week in progress, with the same days of the other weeks, and list the closest")
		self.resetprofact = self.mkaction("Find the Data Profile Again", self.resetprofile, None, None,
			"forget the profile adjusted by hand for the day or week of the data shown")
		self.matchdayact = self.mkaction("Match &Day…", self.matchday, None, "Ctrl+Shift+Y",
			"compare the day shown (a capture's day or a day of the data), up to a time, with the other days of the m15 data, and list the closest")
		self.adjustact = self.mkaction("Adjust P&rofile…", self.adjustprofile, None, "Ctrl+Shift+R",
			"draw the profile of the week shown on its capture, or of the day or week of the data on its chart, "
			"to move its points, add or remove some")
		self.quitact = self.mkaction("&Quit", QApplication.closeAllWindows, None, QKeySequence.StandardKey.Quit)
		self.quitact.setMenuRole(QAction.MenuRole.QuitRole)
		# cut, copy and paste captures in the list, between journals too
		self.cutact = self.mkaction("Cu&t", lambda: self.clipcapture(True), None,
			QKeySequence.StandardKey.Cut, "cut this capture, to paste it in another journal")
		self.copyact = self.mkaction("&Copy", lambda: self.clipcapture(False), None,
			QKeySequence.StandardKey.Copy, "copy this capture, to paste it in this or another journal")
		self.pasteact = self.mkaction("&Paste", self.pastecapture, None,
			QKeySequence.StandardKey.Paste, "paste the capture cut or copied here, keeping its date")
		self.delcapact = self.mkaction("&Delete Capture…", self.deletecapture, None, None,
			"delete this capture, with its notes and drawings (Del in the list)")
		# Del in the list, or with the mouse on it: the menu entry has no
		# shortcut, so Del on the image deletes the drawings selected there
		self.dellistact = QAction("Delete Capture", self)
		self.dellistact.setShortcuts([QKeySequence(Qt.Key.Key_Delete), QKeySequence(Qt.Key.Key_Backspace)])
		self.dellistact.triggered.connect(lambda: self.delpressed(False))
		self.askdelact = self.mkaction("As&k Before Deleting", lambda: settings().setValue("askdelete",
			self.askdelact.isChecked()), None, None, "ask before deleting a capture")
		self.askdelact.setCheckable(True)
		self.sessionsact = self.mkaction("&Session Rectangles", lambda: self.setsessions(self.sessionsact.isChecked()), None, None,
			"Draw the Asia, London and NY AM sessions of the days of the data as rectangles")
		self.sessionsact.setCheckable(True)
		dataview.SHOWSESSIONS = settings().value("datasessions", True) not in (False, "false")
		self.sessionsact.setChecked(dataview.SHOWSESSIONS)
		self.profileact = self.mkaction("&Profile Lines", lambda: self.setprofilelines(self.profileact.isChecked()), None, None,
			"Draw the profile lines (the ones adjusted) on the data charts; the drawings are shown or hidden on their own")
		self.profileact.setCheckable(True)
		dataview.SHOWPROFILE = settings().value("dataprofile", True) not in (False, "false")
		self.profileact.setChecked(dataview.SHOWPROFILE)
		self.newsact = self.mkaction("Update &News Dates", self.updatenews, None, None,
			"read the FOMC, CPI, PPI and NFP dates scheduled from the Federal Reserve's and the BLS's calendars")
		self.importdataact = self.mkaction("Import &Data…", self.choosedata, None, None,
			"add the candles of a CSV exported from TradingView (or a zip with it), in m15 or a lower time frame "
			"(m1 also makes m15), to the journal's data; only those after the last one kept or before the first are added")
		self.addchartact = self.mkaction("Add Chart as &Capture", self.addchart, None, "Ctrl+Shift+K",
			"add the chart of the data view, in its time frame and with its drawings, to the captures of its day or week")
		self.dataact = self.mkaction("&Data View", lambda: self.setdatamode(not self.datamode), None,
			"Ctrl+Shift+D", "switch between the captures and the weeks and days of the m15 data, "
			"drawn from the candles with their profiles")
		self.dataact.setIconText("Data")
		self.recentmenu = QMenu("Open &Recent", self)
		self.recentmenu.aboutToShow.connect(self.fillrecent)

	def mktoolbar(self):
		tb = QToolBar("Journal", self)
		tb.setObjectName("journaltoolbar")
		tb.setMovable(False)
		tb.setIconSize(QSize(18, 18))
		tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
		# first, so they don't end up hidden under » when the window is narrow
		tb.addAction(self.listact)
		tb.addAction(self.notespanelact)
		tb.addSeparator()
		ob = QToolButton(tb)
		ob.setDefaultAction(self.openact)
		self.openact.setIconText("Open")
		ob.setMenu(self.recentmenu)
		ob.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
		ob.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
		tb.addWidget(ob)
		tb.addAction(self.saveact)
		tb.addAction(self.reloadact)
		nb = QToolButton(tb)	# with a menu of time frames, in the data view
		nb.setDefaultAction(self.newwinact)
		self.newwinmenu = QMenu(nb)
		self.newwinmenu.aboutToShow.connect(self.filltfwindows)
		nb.setMenu(self.newwinmenu)
		nb.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
		nb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
		tb.addWidget(nb)
		tb.addAction(self.syncact)
		tb.addSeparator()
		for a in (self.firstact, self.prevact, self.nextact, self.todayact, self.weekact, self.dataact):
			tb.addAction(a)
		self.tfcombo = QComboBox(tb)
		self.tfcombo.setToolTip("the time frame of the data charts; a lower one than m15 takes data of it "
			"(File ▸ Import Data… with an m1 CSV)")
		self.tfcombo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
		self.tfcombo.activated.connect(lambda i: self.setdatatf(self.tfcombo.itemData(i)))
		self.tfcomboact = tb.addWidget(self.tfcombo)
		self.tfcomboact.setVisible(False)	# in the data view
		tb.addSeparator()
		for a in (self.fitact, self.realact, self.zoominact, self.zoomoutact):
			tb.addAction(a)
		self.addToolBar(tb)

	def mkmenus(self):
		mb = self.menuBar()
		f = mb.addMenu("&File")
		f.addAction(self.newwinact)
		f.addAction(self.syncact)
		f.addAction(self.openact)
		f.addMenu(self.recentmenu)
		f.addAction(self.saveact)
		f.addAction(self.addact)
		f.addAction(self.importdataact)
		f.addAction(self.newsact)
		f.addAction(self.addchartact)
		f.addAction(self.reloadact)
		f.addSeparator()
		f.addAction(self.exportselact)
		f.addAction(self.exportallact)
		f.addSeparator()
		f.addAction(self.quitact)
		e = mb.addMenu("&Edit")
		e.addAction(self.undoact)
		e.addAction(self.redoact)
		e.addAction(self.delact)
		e.addSeparator()
		e.addAction(self.delcapact)
		e.addAction(self.askdelact)
		e.addAction(self.copyimgact)
		e.addAction(self.scaleact)
		e.addAction(self.matchact)
		e.addAction(self.matchdayact)
		e.addAction(self.adjustact)
		e.addAction(self.resetprofact)
		e.aboutToShow.connect(lambda: (self.updateclipacts(),
			self.askdelact.setChecked(settings().value("askdelete", True) not in (False, "false"))))
		e.addSeparator()
		e.addAction(self.findact)
		e.addAction(self.aliasact)
		e.addAction(self.notesact)
		e.addSeparator()
		e.addAction(self.retagact)
		e.addAction(self.retagallact)
		g = mb.addMenu("&Go")
		for a in (self.firstact, self.prevact, self.nextact, self.todayact, self.weekact):
			g.addAction(a)
		v = mb.addMenu("&View")
		v.addAction(self.listact)
		v.addAction(self.notespanelact)
		v.addAction(self.dataact)
		self.tfmenu = v.addMenu("&Time Frame")
		self.tfmenu.setEnabled(False)	# in the data view
		self.indmenu = v.addMenu("&Indicators")
		self.indmenu.aboutToShow.connect(self.fillindicators)
		v.addAction(self.sessionsact)
		v.addAction(self.profileact)
		v.addSeparator()
		for a in (self.fitact, self.realact, self.zoominact, self.zoomoutact):
			v.addAction(a)
		v.addSeparator()
		tools = v.addMenu("&Draw")
		for a in self.toolacts.values():
			tools.addAction(a)
		v.addSeparator()
		v.addAction(self.osviewact)
		mb.addMenu(windowmenu(self, self.mainwindow))
		h = mb.addMenu("&Help")
		guide = h.addAction("DayJournal &User Guide")
		guide.setShortcut(QKeySequence.StandardKey.HelpContents)
		guide.triggered.connect(lambda: showguide("DayJournal", self))
		addtopics(h, "DayJournal")
		about = h.addAction("&About DayJournal")
		about.setMenuRole(QAction.MenuRole.AboutRole)
		about.triggered.connect(self.about)

	def mkwidgets(self):
		# left: search, list, calendar
		self.searchbox = SearchEdit()
		self.searchbox.setPlaceholderText("Search tags and notes: a b | !c")
		self.searchbox.setClearButtonEnabled(True)
		self.searchbox.setToolTip(SEARCHTIP)
		self.searchbox.textChanged.connect(self.searchchanged)
		self.searchbox.returnPressed.connect(self.applysearch)
		self.daysbox = QCheckBox("Days")
		self.weeksbox = QCheckBox("Weeks")
		for b in (self.daysbox, self.weeksbox):
			b.setChecked(True)
			b.toggled.connect(self.applysearch)
		self.countlabel = QLabel()
		self.allbtn = QToolButton()
		self.allbtn.setAutoRaise(True)
		self.allbtn.clicked.connect(self.toggleall)
		self.monthsbtn = QToolButton()
		self.monthsbtn.setText("m")
		self.monthsbtn.setToolTip("collapse to months, showing the weeks of the last month and the days of its last week")
		self.monthsbtn.clicked.connect(lambda: self.collapseto("m"))
		self.weeksbtn = QToolButton()
		self.weeksbtn.setText("w")
		self.weeksbtn.setToolTip("collapse to weeks, showing the days of the last week")
		self.weeksbtn.clicked.connect(lambda: self.collapseto("w"))
		kinds = QHBoxLayout()
		kinds.addWidget(self.allbtn)
		for b in (self.monthsbtn, self.weeksbtn):
			b.setAutoRaise(True)
			kinds.addWidget(b)
		kinds.addWidget(self.daysbox)
		kinds.addWidget(self.weeksbox)
		kinds.addStretch()
		kinds.addWidget(self.countlabel)
		self.list = CaptureList(self)
		self.list.setHeaderHidden(True)
		self.list.setIndentation(14)
		self.list.setUniformRowHeights(False)	# week profile rows are taller, for their profiles
		self.list.currentItemChanged.connect(self.listchanged)
		self.list.itemClicked.connect(self.groupclicked)
		self.list.itemDoubleClicked.connect(self.itemdoubleclicked)
		self.list.itemExpanded.connect(lambda it: self.groupexpanded(it, True))
		self.list.itemCollapsed.connect(lambda it: self.groupexpanded(it, False))
		self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
		self.list.customContextMenuRequested.connect(self.listmenu)
		for a in (self.cutact, self.copyact, self.pasteact, self.dellistact):
			a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)	# not in the notes
			self.list.addAction(a)
		self.items = {}			# entry name -> its row in the list
		self.cutname = None		# the capture cut, gray in the list
		self.groups = {}		# group key -> its tree item
		self.expanded = set()	# keys of the groups open
		self.calendar = QCalendarWidget()
		self.calendar.setGridVisible(False)
		self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
		self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
		self.calendar.clicked.connect(self.calendarclicked)
		self.calview = self.calendar.findChild(QTableView, "qt_calendar_calendarview")
		self.calview.viewport().setAcceptDrops(True)
		self.calview.viewport().installEventFilter(self)
		left = self.left = QWidget()
		ll = QVBoxLayout(left)
		ll.setContentsMargins(4, 4, 4, 4)
		caps = QWidget()	# the captures, or the data view
		cl = QVBoxLayout(caps)
		cl.setContentsMargins(0, 0, 0, 0)
		cl.addLayout(kinds)
		cl.addWidget(withrail(self.list), 1)
		self.datapanel = DataPanel(self)
		self.datapanel.picked.connect(lambda kind, d: self.showdata((kind, d)))
		self.datapanel.importbtn.clicked.connect(self.choosedata)
		self.datapanel.backbtn.clicked.connect(lambda: self.setdatamode(False))
		self.datapanel.tfbox.setVisible(False)	# it is on the toolbar, and in View ▸ Time Frame
		self.datapanel.capbtn.clicked.connect(self.addchart)
		self.leftstack = QStackedWidget()
		self.leftstack.addWidget(caps)
		self.leftstack.addWidget(self.datapanel)
		ll.addWidget(self.searchbox)	# searching the captures, or the days and weeks of the data
		ll.addWidget(self.leftstack, 1)
		ll.addWidget(self.calendar)

		# right: title, image, tags, notes
		self.titlelabel = QLabel()
		f = self.titlelabel.font()
		f.setBold(True)
		f.setPointSizeF(f.pointSizeF() * 1.2)
		self.titlelabel.setFont(f)
		self.view = ImageView()
		self.view.delkey = lambda: self.delpressed(True)
		self.view.dclickzoom = False	# a double tap zooms; double clicks are for the drawings
		self.view.navigate.connect(self.navigate)
		self.view.hint.connect(lambda t: self.statusBar().showMessage(t) if t else self.statusBar().clearMessage())
		self.view.drawchanged.connect(self.drawchanged)
		self.view.hiddenchanged.connect(self.datahidden)
		self.view.zoomhook = self.datazoom	# zooming a data chart scales its axes, which stay in the window
		self.view.viewport().installEventFilter(self)	# scrolling on the axes of the data charts
		drawbar = self.mkdrawbar()
		self.tagslabel = QLabel()
		self.tagslabel.setWordWrap(True)
		self.tagslabel.setTextFormat(Qt.TextFormat.RichText)
		self.tagslabel.setToolTip("tags read from the image; click one to search it")
		self.tagslabel.linkActivated.connect(self.tagclicked)
		self.notes = QPlainTextEdit()
		self.notes.setPlaceholderText("Notes for this image. They are saved as you type, "
			"in a .txt file next to it.")
		self.notes.textChanged.connect(self.noteschanged)
		bottom = self.bottom = QWidget()
		bl = QVBoxLayout(bottom)
		bl.setContentsMargins(0, 0, 0, 0)
		bl.addWidget(self.tagslabel)
		bl.addWidget(self.notes, 1)
		vsplit = QSplitter(Qt.Orientation.Vertical)
		vsplit.addWidget(self.view)
		vsplit.addWidget(bottom)
		vsplit.setStretchFactor(0, 4)
		vsplit.setStretchFactor(1, 1)
		vsplit.setSizes([700, 200])
		right = QWidget()
		rl = QVBoxLayout(right)
		rl.setContentsMargins(4, 4, 4, 4)
		top = QHBoxLayout()
		top.addWidget(drawbar)
		top.addSpacing(12)
		top.addWidget(self.titlelabel, 1)
		rl.addLayout(top)
		rl.addWidget(vsplit, 1)

		split = QSplitter(Qt.Orientation.Horizontal)
		split.addWidget(left)
		split.addWidget(right)
		split.setStretchFactor(1, 1)
		split.setSizes([330, 1170])
		self.setCentralWidget(split)

		self.ocrlabel = QLabel()
		self.ocrbar = QProgressBar()
		self.ocrbar.setMaximumWidth(200)
		self.ocrbar.hide()
		self.statusBar().addPermanentWidget(self.ocrlabel)
		self.statusBar().addPermanentWidget(self.ocrbar)

	def mkdrawbar(self):
		"""the tools for drawing on the image"""
		tb = DrawBar(self.view, self)
		self.drawbar = tb
		self.toolacts = tb.toolacts
		self.undoact, self.redoact, self.delact = tb.undoact, tb.redoact, tb.delact
		self.copyimgact = tb.copyimgact
		self.copyimgact.setText("Copy Image")
		self.copyimgact.setIconText("Copy")
		self.setcolor = tb.setcolor
		return tb

	# ---- the data view ----
	def loaddata(self):
		"""read the m15 data of the journal, if it has any"""
		try:
			self.data = m15.Data(self.journal.dir) if self.journal else None
		except (OSError, ValueError) as x:
			self.data = None
			self.statusBar().showMessage(f"Can't read the m15 data: {x}", 5000)
		self.lowdata = None
		low = m15.lowtfs(self.journal.dir) if self.journal else []
		tfs = [t for t in m15.TFS if t >= 15 or (low and t >= low[0] and t % low[0] == 0)]
		if self.datatf not in tfs:
			self.datatf = 15
		self.settfs(tfs, self.datatf)
		self.datapanel.fill(self.data)
		self.dataact.setEnabled(self.journal is not None)
		if self.datamode:
			keys = self.datapanel.keys()
			self.showdata(self.datakey if self.datakey in keys else (keys[-1] if keys else None), force=True)

	def getlow(self):
		"""the data of the lowest time frame under m15, read now if not yet"""
		if self.lowdata is None and self.journal is not None:
			low = m15.lowtfs(self.journal.dir)
			if low:
				QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
				try:
					self.lowdata = m15.Data(self.journal.dir, low[0])
				except (OSError, ValueError) as x:
					self.statusBar().showMessage(f"Can't read the {m15.tfname(low[0])} data: {x}", 5000)
				finally:
					QApplication.restoreOverrideCursor()
		return self.lowdata

	def settfs(self, tfs, tf):
		"""the time frames to pick (None keeps them), and tf picked, on the
		toolbar and in View ▸ Time Frame"""
		self.datapanel.settfs(tfs, tf)
		self.tfcombo.blockSignals(True)
		if tfs is not None:
			self.tfcombo.clear()
			self.tfmenu.clear()
			for t in tfs:
				self.tfcombo.addItem(m15.tfname(t), t)
				a = self.tfmenu.addAction(m15.tfname(t))
				a.setCheckable(True)
				a.setData(t)
				a.triggered.connect(lambda _=False, t=t: self.setdatatf(t))
		i = self.tfcombo.findData(tf)
		if i >= 0:
			self.tfcombo.setCurrentIndex(i)
		self.tfcombo.blockSignals(False)
		for a in self.tfmenu.actions():
			a.setChecked(a.data() == tf)

	def setdatatf(self, tf):
		"""draw the charts of the data view in time frame tf"""
		if tf == self.datatf:
			return
		if self.adjuster is not None:
			self.adjuster.finish(False)
		self.datatf = tf
		self.settfs(None, tf)
		if self.datamode:
			self.showdata(self.datakey, force=True)

	def drawkey(self, k, tf=None):
		"""the name of the drawing of data chart k in pending"""
		return DRAWPFX + f"{k[0]}:{k[1].isoformat()}:{tf or self.datatf}"

	def addchart(self):
		"""add the chart of the data view, as drawn in its time frame, to the
		captures, with its drawing (which can still be edited there)"""
		k = self.datakey if self.datamode else None
		if k is None or self.journal is None or not self.datapath or not self.view.hasimage():
			QMessageBox.information(self, "Add Chart as Capture", "Show a day or week of the data first.")
			return
		self.view.commitedit()
		if self.datapending:	# the indicators as they are for this chart
			QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
			try:
				self.redrawdata(wait=True)
			finally:
				QApplication.restoreOverrideCursor()
		kind, d = k
		week = kind == "w"
		day = weekname(d) if week else d
		self.journal.load()
		name = self.journal.newname(day, week)
		if name is None:
			QMessageBox.warning(self, "Add Chart as Capture", f"No names left for {day:%d %b %Y}")
			return
		try:
			savecapture(self.journal, self.datapath, name)
			drawing = self.view.drawingdata()
			if drawing and drawing.get("shapes"):
				self.journal.savedrawing(self.journal.find(name), drawing)
		except OSError as x:
			QMessageBox.warning(self, "Add Chart as Capture", f"Can't add it: {x}")
			return
		self.applysearch()
		self.startocr()
		self.statusBar().showMessage(f"Added {name} to the captures", 5000)

	def choosedata(self):
		if self.journal is None:
			return
		path, _ = QFileDialog.getOpenFileName(self, "Import Data", os.path.expanduser("~"),
			"CSV or zip (*.csv *.zip);;All files (*)")
		if path:
			self.importdata([path])

	def importdata(self, paths):
		"""add the candles of the files at paths to the journal's data"""
		if self.journal is None:
			return
		if self.data is None:
			self.data = m15.Data(self.journal.dir)
		msgs = []
		for p in paths:
			self.statusBar().showMessage(f"Importing {os.path.basename(p)}…")
			QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
			QApplication.processEvents()
			try:
				offs = []
				done = m15.importfile(self.journal.dir, p, self.data, offs)
			except (OSError, ValueError) as x:
				QApplication.restoreOverrideCursor()
				QMessageBox.warning(self, "Import Data", f"Can't import {os.path.basename(p)}: {x}")
				continue
			QApplication.restoreOverrideCursor()
			msgs.append(f"{os.path.basename(p)}: " + ", ".join(f"{added} {m15.tfname(tf)} candles added"
				+ (f" ({skipped} already there)" if skipped else "") for tf, added, skipped in done)
				+ ("; prices moved " + ", ".join(f"{o:+g} from {d:%-d %b %Y}" for d, o in offs) + " to match the data there" if offs else ""))
		self.loaddata()
		if msgs:
			self.statusBar().showMessage("; ".join(msgs), 8000)
			if self.data is not None and len(self.data):
				self.setdatamode(True)
				keys = self.datapanel.keys()
				self.showdata(keys[-1] if keys else None, force=True)

	def datafor(self, e):
		"""the data row for capture e: its day, or its week"""
		keys = self.datapanel.keys()
		if not keys:
			return None
		if e is None:
			return keys[-1]
		if e.week:
			k = ("w", e.weekmonday())
			if k in keys:
				return k
		elif ("d", e.day) in keys:
			return ("d", e.day)
		d = e.weekmonday() if e.week else e.day
		days = [k for k in keys if k[0] == ("w" if e.week else "d")] or keys
		return min(days, key=lambda k: abs((k[1] - d).days))

	def capturefor(self, key):
		"""the capture for data row key: the week profile of its week, or the
		capture of its day, or the nearest one"""
		if self.journal is None or not self.shown or key is None:
			return None
		kind, d = key
		if kind == "w":
			l = [e for e in self.shown if e.week and e.weekmonday() == d]
		else:
			l = [e for e in self.shown if not e.week and e.day == d]
		return l[0] if l else self.journal.nearest(d, self.shown)

	def setdatamode(self, on):
		"""show the data view, at the day or week of the capture shown, or
		go back to the captures at the day or week shown"""
		on = bool(on) and self.journal is not None
		self.dataact.setText("&Capture View" if on else "&Data View")
		self.tfcomboact.setVisible(on)
		self.tfmenu.setEnabled(on)
		self.dataact.setIconText("Captures" if on else "Data")
		self.dataact.setToolTip("back to the captures, on this day or week" if on
			else "the weeks and days of the m15 data, drawn from the candles with their profiles")
		if on == self.datamode:
			return
		if on:
			if self.adjuster is not None:
				self.adjuster.finish(False)
			self.savenotes()
			self.view.commitedit()
			back = self.current
			self.datamode = True
			self.current = None	# no notes or drawings are saved for the data
			self.capturekey = back.name if back else None
			self.leftstack.setCurrentIndex(1)
			self.markcalendar()
			self.showdata(self.datafor(back), force=True)
		else:
			if self.adjuster is not None:
				self.adjuster.finish(False)
			self.savenotes()
			self.datamode = False
			self.leftstack.setCurrentIndex(0)
			self.markcalendar()
			e = self.capturefor(self.datakey)
			if e is None and getattr(self, "capturekey", None) and self.journal:
				e = self.journal.find(self.capturekey)
			self.show_(e, force=True)

	def showdata(self, key, force=False):
		"""show the chart of data row key, drawn from its candles"""
		if not self.datamode:
			return
		if self.adjuster is not None and key != self.datakey:
			self.adjuster.finish(False)	# leaving the chart drops the adjusting
		if key == self.datakey and not force and self.view.hasimage():
			self.datapanel.select(key)
			return
		if key != self.datakey:
			self.savenotes()
		self.datakey = key
		self.datanoteskey = None
		self.notes.blockSignals(True)
		self.notes.setPlainText("")
		self.notes.blockSignals(False)
		self.tagslabel.setText(f"<b>Data:</b> drawn from the candles, in New York time; the profile, sessions and summary from m15")
		if key is None or self.data is None:
			self.view.setimage(None)
			self.titlelabel.setText("No data: File ▸ Import Data…")
			self.updateactions()
			return
		kind, d = key
		tf = self.datatf
		low = self.getlow() if tf < 15 else None
		path = os.path.join(self.datadir, f"{kind}{d:%Y%m%d}-{m15.tfname(tf)}.png")
		if self.renderdata(kind, d, path, tf, low) is None and tf < 15:
			self.statusBar().showMessage(f"No {m15.tfname(tf)} data for this {'day' if kind == 'd' else 'week'}: "
				"drawn in m15", 5000)
			tf = 15
			path = os.path.join(self.datadir, f"{kind}{d:%Y%m%d}-m15.png")
			self.renderdata(kind, d, path, tf, None)
		self.datapath = path
		self.datashowntf = tf
		name = self.drawkey(key, tf)
		drawing = self.pending[name] if name in self.pending else self.data.readdrawing(kind, d, tf)
		g = self.datageom
		if g is not None:
			drawing = widened(drawing, g.unzoomed(), tf)
		self.view.setimage(path, mapdrawing(drawing, g.unzoomed(), g) if g is not None and g.mapped() else drawing)
		self.sharpchart()
		self.titlelabel.setText((f"Data {m15.tfname(tf)}: Week " + f"{d:%d %b} – {d + timedelta(days=4):%d %b %Y}") if kind == "w"
			else f"Data {m15.tfname(tf)}: {d:%a %d %b %Y}")
		self.titlelabel.setToolTip("drawn from the m15 candles, in New York time; its drawings are kept in the "
			f"journal's {m15.DRAWDIR} folder")
		news = self.journal.news if self.journal else None
		lines = [f"{day:%a %d} {int(h):02d}:{int(h % 1 * 60):02d} {n}" for day, h, n in
			([(d, h, n) for h, n in news.of(d)] if kind == "d" else news.inweek(d))] if news else []
		tags = self.dataentry(kind, d).tags
		links = " ".join(f'<a href="{html.escape(t)}" style="text-decoration:none">{html.escape(t)}</a>' for t in tags)
		self.tagslabel.setText((f"<b>Tags:</b> {links}<br>" if tags else "") + (f"<b>News:</b> {html.escape(', '.join(lines))}<br>" if lines else "")
			+ html.escape(self.data.summary(kind, d)))
		self.notes.blockSignals(True)
		self.notes.setPlainText(self.data.readnotes(kind, d))
		self.notes.blockSignals(False)
		self.datanoteskey = key
		self.notes.setEnabled(True)
		self.datapanel.select(key)
		self.calendar.blockSignals(True)
		self.calendar.setSelectedDate(QDate(d.year, d.month, d.day))
		self.calendar.blockSignals(False)
		self.updateactions()
		self.moved()

	def renderdata(self, kind, d, path, tf, low, wait=False):
		"""draw the chart of day or week d in tf at path, as zoomed, with or
		without its profile as the drawings are shown or not; its Geom
		goes in datageom. The indicators are drawn as their last runs of the
		chart while the runs for it are made in the background (and it is
		drawn again when they are done, see indicatorsdone), or as they are
		run now with wait"""
		view = self.datazooms.get((kind, d, tf))
		g = Geom(self.data, kind, d, tf, low, view)
		self.dataoverlay = None
		self.datapending = False
		if g.ok and indicators.enabled():
			moving = getattr(self, "datamoving", False) and not wait
			self.dataoverlay, self.datapending, bad = indicators.overlay(self.data, self.getlow, g, tf, wait=wait, run=not moving)
			if bad and not self.datapending:
				self.statusBar().showMessage("; ".join(bad), 10000)
		margin = 0
		far = getattr(self.dataoverlay, "reach", None)
		if far is not None and g.ok:	# room right of the last candle for what they draw there
			margin = max(0.0, g.tx(far / 1000) + 3 * g.cw - g.vt1)
			if margin:
				g = Geom(self.data, kind, d, tf, low, view, margin)
		img = render(self.data, kind, d, path, tf, low, view, self.profileshown(),
			self.journal.news if self.journal else None, self.dataoverlay, margin)
		self.datageom = g if img is not None else None
		return img

	def fillindicators(self):
		"""the Indicators menu: the scripts imported, on or off, and how to import more"""
		m = self.indmenu
		m.clear()
		on = set(indicators.enabled())
		have = indicators.scripts()
		for name, _ in have:
			a = m.addAction(name)
			a.setCheckable(True)
			a.setChecked(name in on)
			a.toggled.connect(lambda checked, n=name: self.setindicator(n, checked))
		if not have:
			a = m.addAction("No indicators yet")
			a.setEnabled(False)
		m.addSeparator()
		if have:
			st = m.addMenu("&Settings")
			for name, _ in have:
				st.addAction(name + "…", lambda n=name: self.indicatorinputs(n))
		m.addAction("&Import Indicators…", self.importindicators)
		own = [name for name, _ in have if indicators.imported(name)]
		if own:
			rm = m.addMenu("&Remove")
			for name in own:
				rm.addAction(name, lambda n=name: self.removeindicator(n))
		m.addAction("Indicator Fol&ders…", lambda: indicators.foldersdialog(self) and self.indicatorschanged())
		m.addAction("Show Indicators &Folder", lambda: (os.makedirs(indicators.DIR, exist_ok=True),
			QDesktopServices.openUrl(QUrl.fromLocalFile(indicators.DIR))))

	def indicatorinputs(self, name, accept=None):
		"""edit the inputs of indicator name, as TradingView does"""
		g = self.datageom if self.datamode else None
		QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
		try:
			specs, title = indicators.inputsof(name, self.data, self.getlow, g, self.datashowntf if g else 15)
		finally:
			QApplication.restoreOverrideCursor()
		if not specs and g is None:
			QMessageBox.information(self, "Indicator Settings", "Show a day or week of the data first.")
			return
		if indicators.inputsdialog(self, name, specs, title, accept):
			self.indicatorschanged()

	def setsessions(self, on):
		"""draw the session rectangles on the data charts or not, in every window"""
		settings().setValue("datasessions", bool(on))
		dataview.SHOWSESSIONS = bool(on)
		for w in QApplication.topLevelWidgets():
			if isinstance(w, MainWindow):
				w.sessionsact.setChecked(bool(on))
				if w.datamode and w.datakey is not None:
					w.showdata(w.datakey, force=True)

	def setprofilelines(self, on):
		"""draw the profile lines on the data charts or not, in every window"""
		settings().setValue("dataprofile", bool(on))
		dataview.SHOWPROFILE = bool(on)
		for w in QApplication.topLevelWidgets():
			if isinstance(w, MainWindow):
				w.profileact.setChecked(bool(on))
				if w.datamode and w.datakey is not None:
					w.showdata(w.datakey, force=True)

	def profileshown(self):
		"""whether the data chart draws its profile: with the drawings, when Profile Lines is on"""
		return dataview.SHOWPROFILE and not self.view.hidden

	def setindicator(self, name, on):
		indicators.toggle(name, on)
		self.indicatorschanged()

	def indicatorschanged(self):
		"""draw the data chart again with the indicators on now, in every window"""
		for w in QApplication.topLevelWidgets():
			if isinstance(w, MainWindow) and w.datamode and w.datakey is not None:
				w.showdata(w.datakey, force=True)

	def importindicators(self):
		paths, _ = QFileDialog.getOpenFileNames(self, "Import Indicators", os.path.expanduser("~"),
			"Pine scripts (*.txt *.pine);;All files (*)")
		if not paths:
			return
		try:
			names = indicators.importfiles(paths)
		except OSError as x:
			QMessageBox.warning(self, "Import Indicators", f"Can't import them: {x}")
			return
		self.statusBar().showMessage(f"Imported {', '.join(names)}", 5000)
		self.indicatorschanged()

	def removeindicator(self, name):
		if QMessageBox.question(self, "Remove Indicator", f"Remove {name} from the indicators?") != QMessageBox.StandardButton.Yes:
			return
		try:
			indicators.remove(name)
		except OSError as x:
			QMessageBox.warning(self, "Remove Indicator", f"Can't remove it: {x}")
			return
		self.indicatorschanged()

	def datahidden(self, hidden):
		"""the drawings were hidden or shown: the profile of the chart too"""
		if not self.datamode or self.datakey is None or self.datageom is None or self.datapath is None:
			return
		self.redrawdata()

	def redrawdata(self, wait=False):
		"""draw the data chart shown again, where it is (the drawings stay)"""
		if not self.datamode or self.datakey is None or self.datageom is None or self.datapath is None:
			return
		kind, d = self.datakey
		tf = self.datashowntf
		was = self.datageom.margin
		if self.renderdata(kind, d, self.datapath, tf, self.getlow() if tf < 15 else None, wait) is not None and self.view.pixitem is not None:
			if self.datageom.margin != was:	# the drawings are put where they go now
				self.showdata(self.datakey, force=True)
				return
			self.view.pixitem.setPixmap(QPixmap(self.datapath))
			self.sharpchart()

	def indicatorsdone(self):
		"""runs of the indicators were made: the chart drawn again if it waited for them"""
		if getattr(self, "datapending", False) and isValid(self):
			self.redrawdata()

	def sharpchart(self):
		"""the image of the data chart shown as a ChartItem, that draws the
		candles again, sharp, when zoomed in on"""
		old, g = self.view.pixitem, self.datageom
		if old is None or g is None or self.datakey is None:
			return
		args = (g, self.data, *self.datakey, self.datashowntf,
			self.profileshown(), self.journal.news if self.journal else None)
		if isinstance(old, ChartItem):
			old.args = args
			old.overlay = self.dataoverlay
			old.update()
			return
		it = ChartItem(old.pixmap(), args)
		it.overlay = self.dataoverlay
		it.setZValue(old.zValue())
		sc = self.view.scene()
		sc.removeItem(old)
		sc.addItem(it)
		self.view.pixitem = it

	BORDER = 70	# pixels of the window by the edges of a data chart where a scroll scales its axes

	def wheelzone(self, g, q):
		"""what a scroll at scene point q of the chart of g does: "p" scale
		the prices (on the price axis, or by the left or right edge), "t"
		the times (on the time axis, or by the top or bottom edge), "z"
		zoom (around the center), "s" scroll, None off the chart"""
		where = g.inplot(q.x(), q.y())
		if where != "c":
			return where
		s = self.view.transform().m11() or 1
		bx, by = min(self.BORDER / s, g.pw / 5), min(self.BORDER / s, g.ph / 5)
		dl, dr = q.x() - g.L, g.L + g.pw - q.x()
		dt, db = q.y() - g.T, g.T + g.ph - q.y()
		side, edge = min(dl, dr) / bx, min(dt, db) / by
		if min(side, edge) < 1:
			return "p" if side <= edge else "t"
		cx, cy = (q.x() - g.L) / g.pw - 0.5, (q.y() - g.T) / g.ph - 0.5
		return "z" if abs(cx) < 0.25 and abs(cy) < 0.25 else "s"

	def datazoom(self, factor, at=None):
		"""zoom the data chart by factor on both axes around viewport point
		at (the center without it), keeping its axes in the window; factor
		None shows all of it again. True when taken"""
		g = self.datageom
		if not self.datamode or g is None or self.datakey is None or self.adjuster is not None or not self.view.hasimage():
			return False
		if self.view.mode != "fit":
			self.view.fit()
		if at is None:
			q = QPointF(g.L + g.pw / 2, g.T + g.ph / 2)
		else:
			q = self.view.mapToScene(at)
			q = QPointF(min(max(q.x(), g.L), g.L + g.pw), min(max(q.y(), g.T), g.T + g.ph))
		v = None if factor is None else self.pendinggeom(g).zoomedat(g.t(q.x()), g.price(q.y()), 1 / factor)
		self.setdataview(v)
		return True

	def pendinggeom(self, g):
		"""g with the view the chart is to show (scrolls not drawn yet included)"""
		cur = copy.copy(g)
		v = self.datazooms.get((*self.datakey, self.datashowntf))
		cur.top, cur.bot, cur.t0, cur.vt1 = v or g.whole
		cur.t1 = cur.vt1
		return cur

	QUIET = 1000	# ms without scrolls or drags before the indicators are run on where the chart went

	def datamoved(self):
		"""the chart is being scrolled, scaled or dragged: its indicators are
		drawn as they were, runs going on are stopped, and they are run
		again once it is quiet for QUIET ms"""
		self.datamoving = True
		indicators.cancel()
		t = getattr(self, "quiettimer", None)
		if t is None:
			t = self.quiettimer = QTimer(self)
			t.setSingleShot(True)
			t.timeout.connect(self.dataquiet)
		t.start(self.QUIET)

	def dataquiet(self):
		self.datamoving = False
		if self.datamode and self.datakey is not None and indicators.enabled():
			self.redrawdata()

	def setdataview(self, v):
		"""show view v (see Geom) of the data chart, soon: a burst of
		scrolls or pinches is drawn once"""
		key = (*self.datakey, self.datashowntf)
		if v == (self.datazooms.get(key)):
			return
		self.datamoved()
		if v is None:
			self.datazooms.pop(key, None)
		else:
			self.datazooms[key] = v
		if getattr(self, "dataviewsoon", False):	# drawn when the last one is a moment old
			self.dataviewdirty = True
			return
		self.dataviewsoon, self.dataviewdirty = True, False
		self.showdata(self.datakey, force=True)
		QTimer.singleShot(15, self.dataviewnow)

	def dataviewnow(self):
		if not isValid(self):
			return
		self.dataviewsoon = False
		if self.dataviewdirty and self.datamode and self.datakey is not None:
			self.dataviewdirty = False
			self.showdata(self.datakey, force=True)

	def dataaxis(self, ev):
		"""a scroll on the price or time axis of a data chart, or by its
		edges, scales it there; around its center it zooms, and elsewhere
		it scrolls the chart; a double click on an axis shows all of it
		again; True when taken"""
		g = self.datageom
		if not self.datamode or g is None or self.datakey is None or self.adjuster is not None or not self.view.hasimage():
			return False
		q = self.view.mapToScene(ev.position().toPoint())
		if ev.type() == QEvent.Type.Wheel:
			if self.view.scaler is not None:
				return False
			axis = self.wheelzone(g, q)
			if axis is None:
				return False
			if self.view.mode != "fit":	# the axes stay in the window
				self.view.fit()
				q = self.view.mapToScene(ev.position().toPoint())
			ad, pd = ev.angleDelta(), ev.pixelDelta()
			if axis == "s":
				s = self.view.transform().m11() or 1
				dx, dy = (pd.x(), pd.y()) if not pd.isNull() else (ad.x() / 3, ad.y() / 3)
				if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier and not dx:
					dx, dy = dy, 0
				if not dx and not dy:
					return True
				cur = self.pendinggeom(g)
				dt = -dx / s / g.pw * (cur.vt1 - cur.t0)
				dp = dy / s / g.ph * (cur.top - cur.bot)
				self.setdataview(cur.panned(dt, dp))
				return True
			dy = ad.y() or ad.x()
			if not dy:
				return True
			f = 0.85 ** (dy / 120)
			at, price = g.t(min(q.x(), g.X(g.vt1))), g.price(q.y())	# where the mouse is, as drawn
			cur = self.pendinggeom(g)
			if axis == "z":
				self.setdataview(cur.zoomedat(at, price, f))
			else:
				self.setdataview(cur.zoomed(axis, price if axis == "p" else at, f))
			return True
		else:	# the whole of that axis again
			axis = g.inplot(q.x(), q.y())
			if axis not in ("p", "t"):
				return False
			v = g.view()
			if v is None:
				return True
			w = g.whole
			v = (w[0], w[1], v[2], v[3]) if axis == "p" else (v[0], v[1], w[2], w[3])
			if v == w:
				v = None
		if v == g.view():
			return True
		if v is None:
			self.datazooms.pop(key, None)
		else:
			self.datazooms[key] = v
		self.showdata(self.datakey, force=True)
		return True

	def datapan(self, ev):
		"""dragging a data chart scaled on its axes moves it over its data,
		in the directions the image itself can't be scrolled; True when taken"""
		t = ev.type()
		if t == QEvent.Type.MouseButtonPress:
			self.panning = None
			g = self.datageom
			if (not self.datamode or g is None or g.view() is None or ev.button() != Qt.MouseButton.LeftButton
					or self.view.tool != "select" or self.adjuster is not None):
				return False
			at = ev.position().toPoint()
			q = self.view.mapToScene(at)
			if g.inplot(q.x(), q.y()) != "c" or self.view.itemAt(at) not in (None, self.view.pixitem):
				return False
			self.panning = {"at": QPointF(at), "g": g, "key": (*self.datakey, self.datashowntf), "on": False, "view": None}
			return False	# the view sees the press, and the release
		p = self.panning
		if p is None:
			return False
		if t == QEvent.Type.MouseButtonRelease:
			self.panning = None
			return False
		if not ev.buttons() & Qt.MouseButton.LeftButton:
			self.panning = None
			return False
		d = ev.position() - p["at"]
		if not p["on"]:
			if abs(d.x()) + abs(d.y()) < 4:
				return False
			p["on"] = True
		g, s = p["g"], self.view.transform().m11() or 1
		h, v = self.view.horizontalScrollBar(), self.view.verticalScrollBar()
		dx = d.x() / s if h.maximum() == 0 else 0	# the image can't scroll that way: the data moves
		dy = d.y() / s if v.maximum() == 0 else 0
		if not dx and not dy:
			return False
		dt = -dx / g.pw * (g.t1 - g.t0)
		dp = dy / g.ph * (g.top - g.bot)
		p["view"] = g.panned(dt, dp)
		if not p.get("timer"):
			p["timer"] = True
			QTimer.singleShot(30, self.panapply)
		return True

	def panapply(self):
		"""show the chart where the drag took it"""
		p = self.panning
		if p is None:
			return
		p["timer"] = False
		v, key = p["view"], p["key"]
		if key != (*self.datakey, self.datashowntf) if self.datakey else True:
			return
		self.datamoved()
		if v is None:
			self.datazooms.pop(key, None)
		else:
			self.datazooms[key] = v
		self.showdata(self.datakey, force=True)

	def datastep(self, delta=None, last=None, week=False):
		"""move in the data view: delta rows, to the first or last, or
		between a day and its week"""
		keys = self.datapanel.keys()
		if not keys:
			return
		k = self.datakey
		if last is not None:
			to = keys[-1] if last else keys[0]
		elif week:
			if k is None:
				return
			if k[0] == "d":
				to = ("w", k[1] - timedelta(days=k[1].weekday()))
			else:
				days = [x for x in keys if x[0] == "d" and k[1] <= x[1] < k[1] + timedelta(days=7)]
				to = days[0] if days else None
		else:
			i = keys.index(k) + delta if k in keys else 0
			to = keys[i] if 0 <= i < len(keys) else None
		if to in keys:
			self.showdata(to)

	def navigate(self, what):
		{"prev": lambda: self.step(-1), "next": lambda: self.step(1),
			"first": lambda: self.jump(False), "last": lambda: self.jump(True),
			"week": self.toggleweek}[what]()

	def drawchanged(self):
		"""the drawing of the image shown changed: it is pending until saved"""
		if self.datamode:
			k = self.datakey
			if self.view.loading or k is None or self.data is None or not self.view.hasimage():
				return
			tf = getattr(self, "datashowntf", self.datatf)
			name = self.drawkey(k, tf)
			data = self.view.drawingdata()
			g = self.datageom
			if g is not None and g.mapped():	# kept as on the whole chart
				data = mapdrawing(data, g, g.unzoomed())
			saved = self.data.readdrawing(*k, tf)
			if data and tf < 15 and g is not None:	# so it isn't taken for one of the wider charts of before
				data = {**data, "width": g.W}
				if saved and "width" not in saved:
					saved = {**widened(saved, g.unzoomed(), tf), "width": g.W}
			if data == saved:
				self.pending.pop(name, None)
			else:
				self.pending[name] = data
			self.updatetitle()
			return
		e = self.current
		if self.view.loading or e is None or self.journal is None or not self.view.hasimage():
			return
		data = self.view.drawingdata()
		if data == self.journal.readdrawing(e):
			self.pending.pop(e.name, None)	# back as saved
		else:
			self.pending[e.name] = data
		setdrawing(e, data)
		self.refreshitem(e)
		self.updatetitle()

	def drawingof(self, e):
		"""the drawing of e: the one not saved yet, or the one in its file"""
		if e.name in self.pending:
			return self.pending[e.name]
		return self.journal.readdrawing(e)

	def savedrawings(self):
		"""write the drawings not saved yet; False if one could not be"""
		self.view.commitedit()
		ok = True
		for name, data in list(self.pending.items()):
			if name.startswith(DRAWPFX):	# a chart of the data view
				kind, d, tf = (name[len(DRAWPFX):].split(":") + ["15"])[:3]
				try:
					if self.data is not None:
						self.data.savedrawing(kind, date.fromisoformat(d), data, int(tf))
					self.pending.pop(name)
				except OSError as x:
					ok = False
					self.statusBar().showMessage(f"Can't save the drawing of {d}: {x}", 5000)
				continue
			e = self.journal.find(name) if self.journal else None
			if e is None:
				self.pending.pop(name)
				continue
			try:
				self.journal.savedrawing(e, data)
				self.pending.pop(name)
			except OSError as x:
				ok = False
				self.statusBar().showMessage(f"Can't save the drawing of {name}: {x}", 5000)
		if self.data is not None:
			self.datapanel.mark()
		if ok:
			self.statusBar().showMessage("Drawings saved", 1500)
		self.updatetitle()
		return ok

	def keepdrawings(self, why):
		"""ask what to do with the drawings not saved, before why.
		False if the user cancels"""
		self.view.commitedit()
		if not self.pending:
			return True
		n = len(self.pending)
		qm = QMessageBox
		r = qm.question(self, "Unsaved drawings",
			f"The drawings of {n} image{'s' if n > 1 else ''} are not saved. Save them before {why}?",
			qm.StandardButton.Save | qm.StandardButton.Discard | qm.StandardButton.Cancel, qm.StandardButton.Save)
		if r == qm.StandardButton.Cancel:
			return False
		if r == qm.StandardButton.Save:
			return self.savedrawings()
		self.pending = {}
		self.updatetitle()
		return True

	# ---- adding captures ----
	def droppedimages(self, ev):
		md = ev.mimeData()
		if not md.hasUrls():
			return []
		return [u.toLocalFile() for u in md.urls() if u.isLocalFile() and isimage(u.toLocalFile())]

	def owndrag(self, md):
		"""the capture of this journal dragged from a list, or None"""
		if self.journal is None or not md.hasFormat(DRAGMIME):
			return None
		try:
			c = json.loads(bytes(md.data(DRAGMIME)).decode())
		except ValueError:
			return None
		if os.path.realpath(c.get("dir", "")) != os.path.realpath(self.journal.dir):
			return None
		return self.journal.find(c.get("name", ""))

	def dragdata(self, what):
		"""what dragging a capture from the list carries: what is its name,
		or a row of the list, for the capture of it shown"""
		name = what if isinstance(what, str) or what is None else self.rowentry(what)
		e = self.journal.find(name) if name and self.journal else None
		if e is None:
			return None
		self.savenotes()
		md = QMimeData()
		md.setData(DRAGMIME, json.dumps({"dir": self.journal.dir, "name": e.name}).encode())
		md.setUrls([QUrl.fromLocalFile(self.journal.path(e))])	# to other programs and journals
		return md

	def eventFilter(self, obj, ev):
		if hasattr(self, "view") and obj is self.view.viewport():
			t = ev.type()
			if t in (QEvent.Type.MouseMove, QEvent.Type.Leave, QEvent.Type.HoverMove) and self.datamode:
				QTimer.singleShot(0, self.sendcross)	# once the view has moved its own
			if t in (QEvent.Type.Wheel, QEvent.Type.MouseButtonDblClick):
				return self.dataaxis(ev)
			if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease):
				return self.datapan(ev)
			return False
		if hasattr(self, "calview") and obj is self.calview.viewport():
			t = ev.type()
			if t in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
				e = self.owndrag(ev.mimeData())
				d = calendardate(self.calendar, ev.position().toPoint()) if e is not None else None
				if d is None:
					ev.ignore()
					return True
				self.calendar.blockSignals(True)
				self.calendar.setSelectedDate(QDate(d.year, d.month, d.day))	# where it goes
				self.calendar.blockSignals(False)
				ev.acceptProposedAction()
				return True
			if t == QEvent.Type.DragLeave:
				self.showcalendarday()
				return False
			if t == QEvent.Type.Drop:
				e = self.owndrag(ev.mimeData())
				d = calendardate(self.calendar, ev.position().toPoint()) if e is not None else None
				if d is None:
					ev.ignore()
					return True
				ev.acceptProposedAction()
				QTimer.singleShot(0, lambda: self.movetodate(e, d))	# after the drop is over
				return True
		return super().eventFilter(obj, ev)

	def showcalendarday(self):
		e = self.current
		if e is not None:
			self.calendar.blockSignals(True)
			self.calendar.setSelectedDate(QDate(e.day.year, e.day.month, e.day.day))
			self.calendar.blockSignals(False)

	def movetodate(self, e, d):
		"""move capture e to day d: a day goes to that day, a week profile to
		the week of d (named on the Sunday before it)"""
		self.savenotes()
		self.journal.load()
		e = self.journal.find(e.name)
		if e is None:
			return
		if e.week:
			d = weekname(d)
		if d == e.day:
			self.showcalendarday()
			return
		name = self.journal.newname(d, e.week, e)
		if name is None:
			QMessageBox.warning(self, "Move", f"No names left for {d:%d %b %Y}")
			self.showcalendarday()
			return
		self.renamecapture(e, name, "Move")

	def reorder(self, names, moved=None):
		"""rename the captures of a day so they go in the order of names,
		showing the one moved"""
		self.savenotes()
		self.view.commitedit()
		self.journal.load()
		try:
			new = self.journal.reorder(names)
		except OSError as x:
			QMessageBox.warning(self, "Reorder", f"Can't reorder: {x}")
			self.reload()
			return
		pend = {a: self.pending.pop(a) for a in new if a in self.pending}
		for a, v in pend.items():
			self.pending[new[a]] = v
		c = self.clipped()
		if c and c["name"] in new and new[c["name"]] != c["name"] \
				and os.path.realpath(c["dir"]) == os.path.realpath(self.journal.dir):
			QApplication.clipboard().clear()	# it names one that has another name now
		self.statusBar().showMessage("Reordered " + ", ".join(f"{a} → {b}" for a, b in new.items() if a != b), 4000)
		show = new.get(moved or names[0])
		self.current = None	# its notes were saved; don't save the ones shown into it
		self.applysearch()
		self.reveal(self.journal.find(show), force=True)

	def droppeddata(self, ev):
		"""the m15 CSV files (or zips) dropped"""
		md = ev.mimeData()
		if not md.hasUrls():
			return []
		return [u.toLocalFile() for u in md.urls() if u.isLocalFile()
			and u.toLocalFile().lower().endswith((".csv", ".zip"))]

	def dragEnterEvent(self, ev):
		if self.owndrag(ev.mimeData()) is not None:
			ev.ignore()	# from the list, to the calendar only
		elif self.journal is not None and (self.droppedimages(ev) or self.droppeddata(ev)):
			ev.acceptProposedAction()
		else:
			ev.ignore()

	def dragMoveEvent(self, ev):
		self.dragEnterEvent(ev)

	def dropEvent(self, ev):
		data = self.droppeddata(ev) if self.owndrag(ev.mimeData()) is None else []
		if data:
			ev.acceptProposedAction()
			QTimer.singleShot(0, lambda: self.importdata(data))
			return
		paths = self.droppedimages(ev) if self.owndrag(ev.mimeData()) is None else []
		if not paths:
			ev.ignore()
			return
		ev.acceptProposedAction()
		# after the drop is over, so the dialog doesn't hold the program it came from
		QTimer.singleShot(0, lambda: self.addcaptures(paths))

	def choosecaptures(self):
		if self.journal is None:
			return
		exts = " ".join("*" + x for x in IMAGEEXTS)
		paths, _ = QFileDialog.getOpenFileNames(self, "Add Capture", os.path.expanduser("~/Desktop"),
			f"Images ({exts})")
		self.addcaptures(paths)

	def addcaptures(self, paths):
		"""add the images at paths to the journal, asking the date of each"""
		if self.journal is None:
			return
		added = None
		for p in paths:
			if injournal(self.journal, p):
				QMessageBox.information(self, "Add Capture", f"{os.path.basename(p)} is already in the journal.")
				continue
			self.journal.load()	# the names in use now
			dlg = CaptureDialog(self.journal, p, self)
			if dlg.exec() != QDialog.DialogCode.Accepted:
				continue
			name = dlg.name()
			gone = dlg.replaced()
			try:
				savecapture(self.journal, p, name, gone)
				for x in gone:
					self.forget(x.name)
					if self.current is not None and self.current.name == x.name:
						self.current = None
			except OSError as x:
				QMessageBox.warning(self, "Add Capture", f"Can't add {os.path.basename(p)}: {x}")
				continue
			self.journal.load()
			e = self.journal.find(name)
			if e is not None and dlg.raw is not None:
				self.journal.settext(e, dlg.raw)	# no need to read it again
				self.savecache()
			added = name
			self.statusBar().showMessage(f"Added {name}", 3000)
		if added is not None:
			self.reload()
			self.reveal(self.journal.find(added))

	def reveal(self, e, force=False):
		"""show entry e, making sure the list shows it"""
		if e is None:
			return
		if e not in self.shown:
			(self.daysbox if not e.week else self.weeksbox).setChecked(True)
			if e not in self.shown:
				self.searchbox.clear()
				self.applysearch()
		self.show_(e, force=force)

	# ---- cut, copy and paste ----
	def listmenu(self, pos):
		n = self.list.captureat(pos)
		if n is not None:	# the capture the menu is for
			self.show_(self.journal.find(n))
		self.updateclipacts()
		m = QMenu(self)
		for a in (self.cutact, self.copyact, self.pasteact):
			m.addAction(a)
		m.addAction(self.copyimgact)
		m.addSeparator()
		m.addAction(self.delcapact)
		m.exec(self.list.viewport().mapToGlobal(pos))

	def listentry(self):
		"""the capture selected in the list, or None"""
		name = self.rowentry(self.list.currentItem())
		return self.journal.find(name) if name and self.journal else None

	def rowentry(self, it):
		"""the name of the capture of row it: the one shown when it is
		there, else its first; None for a group"""
		names = it.data(0, NAMESROLE) if it is not None else None
		if not names:
			return None
		if self.list.pick in names:
			return self.list.pick
		if self.current is not None and self.current.name in names:
			return self.current.name
		return names[0]

	def clipped(self):
		"""the capture cut or copied, as {"dir", "name", "cut"}, or None"""
		md = QApplication.clipboard().mimeData()
		if md is None or not md.hasFormat(CLIPMIME):
			return None
		try:
			c = json.loads(bytes(md.data(CLIPMIME)).decode())
			return c if isinstance(c, dict) and c.get("dir") and c.get("name") else None
		except ValueError:
			return None

	def clippedfiles(self):
		"""image files copied elsewhere (in the Finder), to add as captures"""
		md = QApplication.clipboard().mimeData()
		if md is None or not md.hasUrls() or md.hasFormat(CLIPMIME):
			return []
		return [u.toLocalFile() for u in md.urls() if u.isLocalFile() and isimage(u.toLocalFile())]

	def updateclipacts(self):
		on = self.listentry() is not None
		self.cutact.setEnabled(on)
		self.copyact.setEnabled(on)
		self.delcapact.setEnabled(on)
		self.pasteact.setEnabled(self.journal is not None and (self.clipped() is not None or bool(self.clippedfiles())))

	def clipcapture(self, cut):
		"""put the capture selected on the clipboard; a cut one is moved
		from its journal when pasted"""
		e = self.listentry()
		if e is None:
			return
		self.savenotes()
		if e.name in self.pending and not self.keepdrawings("copying it"):
			return
		md = QMimeData()
		md.setData(CLIPMIME, json.dumps({"dir": self.journal.dir, "name": e.name, "cut": cut}).encode())
		md.setUrls([QUrl.fromLocalFile(self.journal.path(e))])
		md.setText(self.journal.path(e))
		QApplication.clipboard().setMimeData(md)
		self.markcut()
		self.statusBar().showMessage(f"{'Cut' if cut else 'Copied'} {e.name}: paste it in "
			f"{'another' if cut else 'this or another'} journal", 4000)

	def markcut(self):
		"""show the capture cut in gray until it is pasted"""
		c = self.clipped()
		cut = c["name"] if c and c.get("cut") and self.journal and c["dir"] == self.journal.dir else None
		self.cutname = cut
		for name, it in self.items.items():
			if len(it.data(0, NAMESROLE) or []) < 2:
				it.setData(0, Qt.ItemDataRole.ForegroundRole, QBrush(QColor("gray")) if name == cut else None)
		self.list.viewport().update()

	def pastecapture(self):
		"""paste the capture cut or copied in this journal, keeping its date,
		with the next name free for it; image files copied elsewhere are added"""
		if self.journal is None:
			return
		c = self.clipped()
		if c is None:
			files = self.clippedfiles()
			if files:
				self.addcaptures(files)
			return
		same = os.path.realpath(c["dir"]) == os.path.realpath(self.journal.dir)
		if same and c.get("cut"):
			self.statusBar().showMessage(f"{c['name']} is already in this journal", 4000)
			return
		self.savenotes()
		try:
			src = self.journal if same else Journal(c["dir"])
			self.journal.load()	# the names in use now
			e = src.find(c["name"])
			if e is None:
				raise OSError(f"{c['name']} is not in {os.path.basename(c['dir'])} any more")
			name = self.journal.paste(src, e, move=bool(c.get("cut")))
		except OSError as x:
			QMessageBox.warning(self, "Paste", f"Can't paste {c['name']}: {x}")
			return
		if c.get("cut"):
			QApplication.clipboard().clear()	# it was moved; it can't be pasted again
		self.statusBar().showMessage(f"Pasted {c['name']} as {name}", 4000)
		self.reload()
		self.reveal(self.journal.find(name))

	def selectedentries(self):
		"""the capture selected in the list, or the ones shown in the
		group (year, month or week) selected"""
		it = self.list.currentItem()
		if it is None or self.journal is None:
			return []
		if it.data(0, NAMESROLE):	# a row: the capture shown of it
			e = self.listentry()
			return [e] if e is not None else []
		out, todo = [], [it]
		while todo:
			x = todo.pop(0)
			for name in x.data(0, NAMESROLE) or []:
				e = self.journal.find(name)
				if e is not None:
					out.append(e)
			todo[0:0] = [x.child(i) for i in range(x.childCount())]
		return out

	def export(self, every):
		"""save the captures shown (every) or selected as PNGs, with their
		drawings, in a zip file the user picks"""
		if self.journal is None:
			return
		self.view.commitedit()
		entries = list(self.shown) if every else self.selectedentries()
		if not entries:
			self.statusBar().showMessage("No captures to export", 3000)
			return
		name = os.path.basename(os.path.normpath(self.journal.dir)) or "journal"
		if not every and len(entries) == 1:
			name = entries[0].base()
		start = os.path.join(settings().value("exportdir", os.path.expanduser("~")), name + ".zip")
		path, _ = QFileDialog.getSaveFileName(self, "Export Captures", start, "Zip files (*.zip)")
		if not path:
			return
		if not path.lower().endswith(".zip"):
			path += ".zip"
		settings().setValue("exportdir", os.path.dirname(path))
		n, bad = self.exportto(path, entries)
		msg = f"{n} capture{'s' if n != 1 else ''} exported to {os.path.basename(path)}"
		if bad:
			msg += f"; can't read {', '.join(bad)}"
		self.statusBar().showMessage(msg, 5000)

	def exportto(self, path, entries):
		"""write entries as PNGs, drawings included, to the zip file path;
		(how many were written, names that could not be read)"""
		from PySide6.QtCore import QBuffer, QByteArray, QIODevice
		n, bad, used = 0, [], set()
		QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
		try:
			with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
				for i, e in enumerate(entries):
					if i % 5 == 0:
						self.statusBar().showMessage(f"Exporting {i + 1} of {len(entries)}…")
						QApplication.processEvents()
					src = self.journal.path(e)
					drawing = self.drawingof(e)
					if not (drawing or {}).get("shapes") and src.lower().endswith(".png") and os.path.isfile(src):
						with open(src, "rb") as f:
							data = f.read()
					else:
						img = renderfile(src, drawing)
						if img is None:
							bad.append(e.name)
							continue
						ba = QByteArray()
						buf = QBuffer(ba)
						buf.open(QIODevice.OpenModeFlag.WriteOnly)
						img.save(buf, "PNG")
						buf.close()
						data = bytes(ba.data())
					arc = e.base() + ".png"
					k = 2
					while arc in used:
						arc = f"{e.base()}-{k}.png"
						k += 1
					used.add(arc)
					z.writestr(arc, data)
					n += 1
		finally:
			QApplication.restoreOverrideCursor()
		return n, bad

	def deletecapture(self, e=None):
		"""delete capture e (the one selected in the list), with its notes
		and drawings, asking first unless told not to ask again"""
		e = e or self.listentry()
		if e is None:
			return
		self.savenotes()
		if settings().value("askdelete", True) not in (False, "false"):
			qm = QMessageBox(QMessageBox.Icon.Question, "Delete Capture",
				f"Delete {e.name}, {e.label()}, with its notes and drawings?",
				QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, self)
			qm.setDefaultButton(QMessageBox.StandardButton.Cancel)
			qm.button(QMessageBox.StandardButton.Yes).setText("Delete")
			dontask = QCheckBox("Don't ask again")
			qm.setCheckBox(dontask)
			self.deldlg = qm	# for the tests
			if qm.exec() != QMessageBox.StandardButton.Yes:
				return
			if dontask.isChecked():
				settings().setValue("askdelete", False)
		# where to go next: the one after it in the list, or the one before
		shown = [x.name for x in self.shown]
		i = shown.index(e.name) if e.name in shown else -1
		near = [n for n in shown[i + 1:] + shown[:i][::-1] if n != e.name] if i >= 0 else []
		try:
			self.journal.delete(e)
		except OSError as x:
			QMessageBox.warning(self, "Delete Capture", f"Can't delete {e.name}: {x}")
			return
		self.forget(e.name)
		self.statusBar().showMessage(f"Deleted {e.name}", 4000)
		gone = self.current is not None and self.current.name == e.name
		if gone:
			self.current = None
		self.reload()
		if gone:
			nxt = next((self.journal.find(n) for n in near if self.journal.find(n)), None)
			self.show_(nxt, force=True)

	def mouseon(self, w):
		"""whether the mouse is on widget w"""
		return w.isVisible() and w.rect().contains(w.mapFromGlobal(QCursor.pos()))

	def delpressed(self, onimage):
		"""Del with the focus on the image (onimage) or in the list: with the
		mouse on the list it deletes the capture; else the drawings selected,
		when the focus or the mouse is on the image. Whether it took it."""
		if self.mouseon(self.list):
			self.deletecapture()
			return True
		if onimage:
			return False	# the image deletes its drawings selected
		if self.view.scene().selectedItems() and self.mouseon(self.view):
			self.view.deleteselected()
		else:
			self.deletecapture()
		return True

	def forget(self, name):
		"""drop what is kept of a capture removed: its drawing not saved, and
		the clipboard if it has it"""
		if self.pending.pop(name, None) is not None:
			self.updatetitle()
		c = self.clipped()
		if c and c["name"] == name and os.path.realpath(c["dir"]) == os.path.realpath(self.journal.dir):
			QApplication.clipboard().clear()

	def showpanel(self, w, a, on=None, keep=True):
		"""show or hide panel w (the list or the notes), as action a says;
		keep makes it the default for the next windows"""
		on = a.isChecked() if on is None else on
		a.setChecked(on)
		w.setVisible(on)
		if keep and not self.child:
			settings().setValue("showlist" if w is self.left else "shownotes", on)
		f = QApplication.focusWidget()
		if not on and f is not None and w.isAncestorOf(f):
			self.view.setFocus()

	def find(self):
		if not self.left.isVisible():
			self.showpanel(self.left, self.listact, True)
		self.searchbox.setFocus()
		self.searchbox.selectAll()

	def editnotes(self):
		if not self.bottom.isVisible():
			self.showpanel(self.bottom, self.notespanelact, True)
		self.notes.setFocus()

	def itemdoubleclicked(self, item, _col):
		name = self.rowentry(item)
		e = self.journal.find(name) if name and self.journal else None
		if e is not None:
			QTimer.singleShot(0, lambda: self.changedate(e))	# after the click is over

	def changedate(self, e):
		"""ask for another date or kind for capture e, and rename it"""
		self.savenotes()
		self.journal.load()
		e = self.journal.find(e.name)
		if e is None:
			return
		dlg = CaptureDialog(self.journal, self.journal.path(e), self, entry=e)
		if dlg.exec() != QDialog.DialogCode.Accepted:
			return
		name = dlg.name()
		if name is None or name == e.name:
			return
		self.renamecapture(e, name, "Change Date")

	def renamecapture(self, e, name, what):
		"""rename capture e to name, with its notes, drawing and tags, and show it"""
		self.view.commitedit()
		try:
			self.journal.rename(e, name)
		except OSError as x:
			QMessageBox.warning(self, what, f"Can't rename {e.name}: {x}")
			self.showcalendarday()
			return
		if e.name in self.pending:
			self.pending[name] = self.pending.pop(e.name)
		self.statusBar().showMessage(f"{e.name} is now {name}", 3000)
		n = self.journal.find(name)
		self.current = None	# its notes were saved; don't save the ones shown into it
		self.applysearch()
		self.reveal(n, force=True)

	# ---- journals ----
	def startjournal(self):
		"""the last journal used, or the first one found"""
		for p in recentjournals() + defaultjournals():
			if os.path.isdir(p):
				return p
		return None

	def choosejournal(self):
		start = self.journal.dir if self.journal else (defaultjournals() or [None])[0]
		d = QFileDialog.getExistingDirectory(self, "Open Journal", os.path.dirname(start) if start else tradedir())
		if d:
			self.openjournal(d)

	def fillrecent(self):
		m = self.recentmenu
		m.clear()
		paths = recentjournals()
		for p in defaultjournals():
			if p not in paths:
				paths.append(p)
		for p in paths:
			a = m.addAction(f"{os.path.basename(p)}    {os.path.dirname(p)}")
			a.setEnabled(os.path.isdir(p))
			a.setCheckable(True)
			a.setChecked(self.journal is not None and self.journal.dir == p)
			a.triggered.connect(lambda _=False, p=p: self.openjournal(p))
		if not paths:
			m.addAction("No journals found").setEnabled(False)

	def openjournal(self, path):
		self.savenotes()
		if not self.keepdrawings("opening another journal"):
			return
		self.stopocr()
		try:
			j = Journal(path)
		except OSError as e:
			QMessageBox.warning(self, "Open Journal", f"Can't open {path}: {e}")
			return
		if self.watcher.directories():
			self.watcher.removePaths(self.watcher.directories())
		self.journal = j
		self.profiles = Profiles(j.dir)
		self.watcher.addPath(j.dir)
		addrecent(j.dir)
		self.current = None
		self.initialgroups()
		self.datamode = False
		self.datapanel.expanded = None	# the last month open
		self.loaddata()
		self.applysearch(keep=False)
		self.jump(True)
		self.updatetitle()
		self.startocr()

	def reload(self):
		if self.journal is None:
			return
		self.savenotes()
		cur = self.current.name if self.current else None
		before = self.journal.mtime(self.current) if self.current else None
		self.journal.load()
		for name, data in self.pending.items():
			e = self.journal.find(name)
			if e is not None:
				setdrawing(e, data)
		self.current = self.journal.find(cur) if cur else None
		self.applysearch()
		e = self.current
		if e is not None and (self.journal.mtime(e) != before or
				(e.name not in self.pending and self.journal.readdrawing(e) != self.view.drawingdata())):
			# the image or its drawing changed on disk (in another window);
			# otherwise keep its drawing and undo
			self.show_(e, force=True)
		elif e is not None and e.notes != self.notes.toPlainText():
			self.notes.blockSignals(True)	# written in another window
			self.notes.setPlainText(e.notes)
			self.notes.blockSignals(False)
		self.startocr()

	def filltfwindows(self):
		"""the New Window menu: a window in each time frame, in the data view"""
		m = self.newwinmenu
		m.clear()
		if not self.datamode:
			a = m.addAction("New windows in other time frames are for the data view")
			a.setEnabled(False)
			return
		for i in range(self.tfcombo.count()):
			t = self.tfcombo.itemData(i)
			a = m.addAction(f"New Window in {m15.tfname(t)}")
			a.triggered.connect(lambda _=False, t=t: self.tfwindow(t))

	def tfwindow(self, tf):
		"""a new window on this chart in time frame tf, and this window and
		those made so laid out together, when the screen has room"""
		w = self.newwindow(tf)
		self.tfkids = [k for k in getattr(self, "tfkids", []) if isValid(k) and k.isVisible()] + [w]
		scr = winlayout.screenof(self)
		group = [self] + self.tfkids
		if scr.width() < 1200 or scr.height() < 700:
			return w	# no room: they stay one over the other
		rects = winlayout.mainleft(scr, len(group)) if len(group) <= 4 else winlayout.grid(scr, len(group))
		for x, r in zip(group, rects):
			winlayout.place(x, r, scr)
		w.raise_()
		return w

	def newwindow(self, tf=None):
		"""another window, on the same journal and image, a bit lower and to
		the right; it can browse it or open another journal. In the data
		view, on the same chart, in time frame tf (or this one's)"""
		self.savenotes()
		self.view.commitedit()
		w = MainWindow(self.journal.dir if self.journal else None)
		w.child = True
		w.syncact.setVisible(True)
		for panel, a in ((w.left, w.listact), (w.bottom, w.notespanelact)):	# the image almost all the window
			w.showpanel(panel, a, False, keep=False)
		w.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
		windows.append(w)
		w.destroyed.connect(lambda _=None, w=w: windows.remove(w) if w in windows else None)
		w.resize(self.size())
		w.move(self.pos() + QPoint(40, 40))
		if self.journal is not None and w.journal is not None:
			w.pending = dict(self.pending)	# the drawings as they are now
			w.updatetitle()
			if self.current is not None:
				w.reveal(w.journal.find(self.current.name), force=True)
			if self.datamode:	# on the same chart, to look at it in another time frame
				w.datatf = tf or self.datatf
				w.settfs(None, w.datatf)
				w.setdatamode(True)
				w.showdata(self.datakey, force=True)
				w.syncact.setChecked(True)	# on the data, synced; on a capture, not
		w.show()
		return w

	def updatenews(self):
		"""fetch the news dates again, and show them in every window"""
		self.statusBar().showMessage("Reading the news calendars…")
		QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
		QApplication.processEvents()
		try:
			res = news.fetch()
		finally:
			QApplication.restoreOverrideCursor()
		self.statusBar().clearMessage()
		for w in QApplication.topLevelWidgets():
			if isinstance(w, MainWindow):
				w.newsread()
		ok = [f"{n}: {r} dates" for n, r in res.items() if isinstance(r, int)]
		bad = [f"{n}: {r}" for n, r in res.items() if not isinstance(r, int)]
		text = ("Read " + ", ".join(ok) + "." if ok else "Nothing read.") + (
			"\n\nCouldn't read " + "; ".join(bad) + ". The dates built in are still used." if bad else "")
		(QMessageBox.information if not bad else QMessageBox.warning)(self, "Update News Dates", text)

	def newsread(self):
		"""the news dates changed: their tags, list and charts again"""
		if self.journal is None:
			return
		self.journal.news = news.News(self.journal.dir)
		for e in self.journal.entries:
			e.tags = self.journal.tagsof(e)
		self.applysearch()
		if self.current is not None and not self.datamode:
			self.showtags(self.current)
		self.datapanel.mark()
		if self.datamode and self.datakey is not None:
			self.showdata(self.datakey, force=True)

	def dataentry(self, kind, d):
		"""the day or week d of the data as the search sees it: its news as
		tags, and its notes"""
		n = self.journal.news if self.journal else None
		tags = (n.names(d) if kind == "d" else list(dict.fromkeys(x for _, _, x in n.inweek(d)))) if n else []
		notes = self.data.readnotes(kind, d) if self.data is not None else ""
		return SimpleNamespace(tags=tags, notes=notes, drawtext="")

	def mainwindow(self):
		"""the main window, for the Window menu's layouts: one with its list
		and calendar shown, this one if it has them, else the first made"""
		ws = [w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow) and w.isVisible()]
		withlist = [w for w in ws if w.left.isVisible()]
		if self in withlist:
			return self
		withlist.sort(key=lambda w: w.child)
		return withlist[0] if withlist else self

	# ---- synced windows ----
	def insync(self):
		"""whether this window moves with the others: the main one, and
		those made with New Window that are synced"""
		return not self.child or self.syncact.isChecked()

	def syncgroup(self):
		"""the other windows that move with this one, on the same journal"""
		if not self.insync() or self.journal is None:
			return []
		return [w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow) and w is not self
			and w.insync() and w.journal is not None and w.journal.dir == self.journal.dir]

	def syncchanged(self):
		"""synced again: to the day or week of the main window"""
		if not self.syncact.isChecked():
			return
		main = next((w for w in self.syncgroup() if not w.child), None)
		if main is not None and main.shownkey() is not None:
			self.follow(*main.shownkey())

	def shownkey(self):
		"""("d" or "w", date) shown: the day or week of the chart or capture"""
		if self.datamode:
			return self.datakey
		e = self.current
		if e is None:
			return None
		return ("w", e.weekmonday()) if e.week else ("d", e.day)

	def moved(self):
		"""this window went to another day or week: the synced ones too"""
		global following
		if following or not self.isVisible():	# a window being made doesn't move the others
			return
		k = self.shownkey()
		group = self.syncgroup()
		if k is None or not group:
			return
		following = True
		try:
			for w in group:
				w.follow(*k)
		finally:
			following = False

	def follow(self, kind, d):
		"""go to day or week d as another window did, staying on days or
		weeks as this one shows them"""
		monday = d - timedelta(days=d.weekday())
		mine = self.shownkey()
		if self.datamode:
			keys = set(self.datapanel.keys())
			if mine is not None and mine[0] == "w" or kind == "w" and (mine is None or mine[0] == "w"):
				to = ("w", monday)
			elif kind == "d":
				to = ("d", d)
			else:	# a week, and this one is on a day: stay if it is in that week
				if mine is not None and mine[1] - timedelta(days=mine[1].weekday()) == monday:
					return
				to = next((k for k in sorted(keys) if k[0] == "d" and monday <= k[1] < monday + timedelta(days=5)), None)
			if to is not None and to in keys and to != self.datakey:
				self.showdata(to)
			return
		if self.journal is None:
			return
		week = mine is not None and mine[0] == "w" or kind == "w"
		if mine == (("w", monday) if week else ("d", d)):
			return
		if week:
			e = next((x for x in self.journal.entries if x.week and x.weekmonday() == monday), None)
		else:
			e = next((x for x in self.journal.entries if not x.week and x.day == d), None)
		if e is not None:
			self.reveal(e)

	def sendcross(self):
		"""the crosshair of this data chart on those of the synced windows,
		at the same time and price"""
		g = self.datageom
		group = [w for w in self.syncgroup() if w.datamode and w.datageom is not None and w.view.hasimage()]
		if not group:
			return
		p = self.view.cross if self.datamode and g is not None else None
		at = g.when(p.x(), p.y()) if p is not None else None
		for w in group:
			q = w.datageom.where(*at) if at is not None else None
			w.view.setcross(QPointF(*q) if q is not None else None)

	def updatetitle(self):
		if self.journal is None:
			self.setWindowTitle("DayJournal")
			return
		n = len(self.journal.entries)
		unsaved = " (unsaved)" if self.pending else ""
		self.setWindowTitle(f"DayJournal — {os.path.basename(self.journal.dir)} ({n} images){unsaved}")
		self.saveact.setEnabled(bool(self.pending))

	# ---- search and list ----
	def searchchanged(self, text):
		err = Search.error(text, self.aliases())
		self.searchbox.setStyleSheet("QLineEdit { color: #c62828; }" if err else "")
		self.searchbox.setToolTip(f"<p><b>{html.escape(err)}</b></p>{SEARCHTIP}" if err else SEARCHTIP)
		if err is None:
			self.searchtimer.start()
		else:
			self.searchtimer.stop()

	def aliases(self):
		return self.journal.aliases if self.journal is not None else {}

	def editaliases(self):
		"""edit the journal's aliases.txt"""
		if self.journal is None:
			return
		self.journal.load()	# edited in another window or by hand
		dlg = QDialog(self)
		dlg.setWindowTitle(f"Aliases — {os.path.basename(self.journal.dir)}")
		l = QVBoxLayout(dlg)
		help = QLabel(ALIASHELP)
		help.setWordWrap(True)
		l.addWidget(help)
		ed = QPlainTextEdit(self.journal.readaliases())
		ed.setPlaceholderText("news: NFP, PPI, CPI")
		ed.setMinimumSize(420, 260)
		l.addWidget(ed)
		bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
		bb.accepted.connect(dlg.accept)
		bb.rejected.connect(dlg.reject)
		l.addWidget(bb)
		self.aliasdlg = dlg	# for the tests
		if dlg.exec() != QDialog.DialogCode.Accepted:
			return
		try:
			self.journal.savealiases(ed.toPlainText())
		except OSError as x:
			QMessageBox.warning(self, "Aliases", f"Can't save the aliases: {x}")
			return
		if self.journal.badaliases:
			lines = ", ".join(str(n) for n in self.journal.badaliases)
			QMessageBox.information(self, "Aliases", f"Lines {lines} were ignored: they need a word, : and its aliases.")
		self.searchchanged(self.searchbox.text())
		self.applysearch()

	def applysearch(self, keep=True):
		if self.journal is None:
			return
		text = self.searchbox.text().strip()
		try:
			self.search = Search(text, self.aliases())
		except ValueError:
			return	# keep the last good search
		days, weeks = self.daysbox.isChecked(), self.weeksbox.isChecked()
		self.shown = [e for e in self.journal.entries
			if (weeks if e.week else days) and self.search.match(e)]
		if self.search.expr is not None:
			# show what was found
			for e in self.shown:
				self.expanded.update(k for k, _ in groupkeys(e))
		self.fillist()
		search = self.search
		self.datapanel.match = (lambda kind, d: search.match(self.dataentry(kind, d))) if search.expr is not None else None
		if self.data is not None:
			self.datapanel.refill()
		if keep and self.current is not None and self.current in self.shown:
			self.selectitem(self.current)
		elif keep and self.shown and self.current is not None:
			# the one shown went away: go to the nearest date
			self.show_(self.journal.nearest(self.current.day, self.shown))
		elif not self.shown:
			self.show_(None)
		self.markcalendar()

	def fillist(self):
		"""the entries shown, in year, month and week groups"""
		self.list.blockSignals(True)
		self.list.clear()
		self.items = {}
		self.groups = {}
		bold = QFont(self.list.font())
		bold.setBold(True)
		weeks = self.journal.weeks() if self.journal else []
		rows = {}
		for e in self.shown:
			parent = None
			for key, label in groupkeys(e):
				g = self.groups.get(key)
				if g is None:
					if key[0] == "w":	# numbered: 5. Week 26 Oct
						label = f"{weekno(key[3], weeks[0])}. {label}"
					g = QTreeWidgetItem([label])
					g.setData(0, Qt.ItemDataRole.UserRole, None)
					g.setFont(0, bold)
					g.setData(0, Qt.ItemDataRole.UserRole + 1, label)
					g.setData(0, Qt.ItemDataRole.UserRole + 2, 0)
					if parent is None:
						self.list.addTopLevelItem(g)
					else:
						parent.addChild(g)
					self.groups[key] = g
				g.setData(0, Qt.ItemDataRole.UserRole + 2, g.data(0, Qt.ItemDataRole.UserRole + 2) + 1)
				parent = g
			rk = (id(parent), e.day, e.week)
			it = rows.get(rk)
			if it is None:	# a row for the captures of the day (or the week profiles)
				it = QTreeWidgetItem([self.itemtext(e)])
				it.setData(0, Qt.ItemDataRole.UserRole, e.name)
				it.setData(0, NAMESROLE, [e.name])
				if e.week:
					it.setFont(0, bold)
				it.setToolTip(0, self.itemtip(e))
				parent.addChild(it)
				rows[rk] = it
			else:
				it.setData(0, NAMESROLE, it.data(0, NAMESROLE) + [e.name])
				it.setText(0, self.rowlabel(e))
				it.setToolTip(0, "")
			self.items[e.name] = it
		for key, g in self.groups.items():
			n = g.data(0, Qt.ItemDataRole.UserRole + 2)
			g.setText(0, f"{g.data(0, Qt.ItemDataRole.UserRole + 1)}   ({n})")
			g.setExpanded(key in self.expanded)
		self.list.blockSignals(False)
		self.markcut()
		self.updateallbtn()
		total = len(self.journal.entries) if self.journal else 0
		self.countlabel.setText(f"{len(self.shown)} of {total}, {len(weeks)} week{'s' if len(weeks) != 1 else ''}")
		self.countlabel.setToolTip("images shown of all the images, and the weeks with images")

	@staticmethod
	def rowlabel(e):
		"""the label of a row with several captures"""
		return "Week profile" if e.week else e.day.strftime("%a %d")

	@staticmethod
	def chiplabel(e):
		"""the compact name of a capture in its row: its letter (a for the
		first), marked when it has notes or drawings"""
		return (e.extra or "a") + ("✎" if e.notes.strip() or e.drawn else "")

	@staticmethod
	def itemtext(e):
		if e.week:
			s = "Week profile"
		else:
			s = e.day.strftime("%a %d") + e.extra	# Tue 26, Tue 26b
		return s + ("  ✎" if e.notes.strip() or e.drawn else "")	# notes or drawings

	@staticmethod
	def itemtip(e):
		tip = " ".join(e.tags[:30])
		if e.notes.strip():
			tip = e.notes.strip()[:300] + ("\n\n" + tip if tip else "")
		return tip

	def groupkey(self, g):
		for k, x in self.groups.items():
			if x is g:
				return k
		return None

	def groupexpanded(self, g, open):
		k = self.groupkey(g)
		if k is None:
			return
		if open:
			self.expanded.add(k)
		else:
			self.expanded.discard(k)
		self.updateallbtn()

	def groupclicked(self, item, _col):
		if item.data(0, Qt.ItemDataRole.UserRole) is None:
			item.setExpanded(not item.isExpanded())

	def initialgroups(self):
		"""open only the last year, month and week, and the week before
		when the last one has less than two days"""
		self.expanded = set()
		days = [e for e in self.journal.entries if not e.week] if self.journal else []
		if not days:
			days = list(self.journal.entries) if self.journal else []
		if not days:
			return
		weeks = []
		for e in reversed(days):
			k = groupkeys(e)[-1][0]
			if k not in weeks:
				weeks.append(k)
		last = [e for e in days if groupkeys(e)[-1][0] == weeks[0]]
		open = [last[-1]]
		if len(last) < 2 and len(weeks) > 1:
			open.append([e for e in days if groupkeys(e)[-1][0] == weeks[1]][-1])
		for e in open:
			for k, _ in groupkeys(e):
				self.expanded.add(k)
			if self.journal:
				w = self.journal.weekof(e)
				if w is not None:
					self.expanded.update(k for k, _ in groupkeys(w))

	def allcollapsed(self):
		return not any(g.isExpanded() for g in self.groups.values())

	def updateallbtn(self):
		c = self.allcollapsed()
		self.allbtn.setText("▸" if c else "▾")
		self.allbtn.setToolTip("expand all" if c else "collapse all")

	def toggleall(self):
		expand = self.allcollapsed()
		self.list.blockSignals(True)
		for k, g in self.groups.items():
			g.setExpanded(expand)
		self.list.blockSignals(False)
		self.expanded = set(self.groups) if expand else set()
		self.updateallbtn()
		if expand and self.current is not None:
			self.selectitem(self.current)

	def collapseto(self, level):
		"""collapse the list to months ("m") or weeks ("w"); the last month
		stays open with its last week, or the last week stays open"""
		keep = {k for k in self.groups if k[0] == "y" or (level == "w" and k[0] == "m")}
		if self.shown:
			keep.update(k for k, _ in groupkeys(self.shown[-1]))
		self.list.blockSignals(True)
		for k, g in self.groups.items():
			g.setExpanded(k in keep)
		self.list.blockSignals(False)
		self.expanded = keep
		self.updateallbtn()
		if self.current is not None and self.current.name in self.items:
			it = self.items[self.current.name]
			if it.parent() is not None and it.parent().isExpanded():
				self.list.scrollToItem(it)

	def selectitem(self, e):
		it = self.items.get(e.name) if e is not None else None
		self.list.blockSignals(True)
		if it is None:
			self.list.setCurrentItem(None)
			self.list.viewport().update()
		else:
			p = it.parent()
			while p is not None:	# open its groups
				p.setExpanded(True)
				k = self.groupkey(p)
				if k is not None:
					self.expanded.add(k)
				p = p.parent()
			self.list.setCurrentItem(it)
			self.list.scrollToItem(it)
			self.list.viewport().update()	# the chip of the one shown
		self.list.blockSignals(False)
		self.updateallbtn()

	def listchanged(self, item, _prev):
		if item is None or self.journal is None:
			return
		name = self.rowentry(item)
		if name is None:
			return	# a group
		e = self.journal.find(name)
		if e is not None:
			self.show_(e)

	def markcalendar(self):
		self.calendar.setDateTextFormat(QDate(), QTextCharFormat())	# clear
		if self.journal is None:
			return
		if self.datamode:
			has = QTextCharFormat()
			has.setFontWeight(QFont.Weight.Bold)
			has.setForeground(QColor("#089981"))
			for d in (self.data.days() if self.data is not None else []):
				self.calendar.setDateTextFormat(QDate(d.year, d.month, d.day), has)
			return
		shown = {e.day for e in self.shown if not e.week}
		other = QTextCharFormat()
		other.setForeground(Qt.GlobalColor.gray)
		has = QTextCharFormat()
		has.setFontWeight(QFont.Weight.Bold)
		has.setForeground(Qt.GlobalColor.darkBlue)
		for d in self.journal.days():
			self.calendar.setDateTextFormat(QDate(d.year, d.month, d.day), has if d in shown else other)

	def calendarclicked(self, qd):
		if self.datamode:
			d = qd.toPython()
			keys = [k for k in self.datapanel.keys() if k[0] == "d"]
			if keys:
				self.showdata(min(keys, key=lambda k: abs((k[1] - d).days)))
			return
		if self.journal is None or not self.shown:
			return
		d = qd.toPython()
		day = [e for e in self.shown if e.day == d and not e.week]
		self.show_(day[0] if day else self.journal.nearest(d, self.shown))

	def tagclicked(self, tag):
		t = self.searchbox.text().strip()
		self.searchbox.setText(f"{t} {tag}".strip() if t else tag)
		self.applysearch()

	# ---- showing ----
	def show_(self, e, force=False):
		if self.datamode:	# the captures come back where the data view leaves them
			self.capturekey = e.name if e is not None else None
			return
		if self.adjuster is not None and e is not self.current:
			self.adjuster.finish(False)	# leaving the capture drops the adjusting
		if e is self.current and not force:
			self.selectitem(e)
			return
		self.savenotes()
		self.view.commitedit()	# a text being written goes into the drawing
		self.current = e
		self.notes.blockSignals(True)
		if e is None:
			self.view.setimage(None)
			self.titlelabel.setText("No images" if self.journal else "No journal open")
			self.tagslabel.clear()
			self.notes.setPlainText("")
			self.notes.setEnabled(False)
		else:
			self.view.setimage(self.journal.path(e), self.drawingof(e))
			self.titlelabel.setText(e.label())
			self.titlelabel.setToolTip(self.journal.path(e))
			self.showtags(e)
			self.notes.setPlainText(e.notes)
			self.notes.setEnabled(True)
			self.selectitem(e)
			self.calendar.blockSignals(True)
			self.calendar.setSelectedDate(QDate(e.day.year, e.day.month, e.day.day))
			self.calendar.blockSignals(False)
		self.notes.blockSignals(False)
		self.updateactions()
		self.moved()

	def showtags(self, e):
		if e.tags:
			links = " ".join(f'<a href="{html.escape(t)}" style="text-decoration:none">{html.escape(t)}</a>'
				for t in e.tags)
			self.tagslabel.setText(f"<b>Tags:</b> {links}")
		elif self.journal.needsocr(e):
			self.tagslabel.setText("<i>Reading the tags…</i>")
		else:
			self.tagslabel.setText("<i>No tags found in the image</i>")

	def updateactions(self):
		if self.datamode:
			keys = self.datapanel.keys()
			i = keys.index(self.datakey) if self.datakey in keys else -1
			self.prevact.setEnabled(i > 0)
			self.nextact.setEnabled(0 <= i < len(keys) - 1)
			self.weekact.setEnabled(i >= 0)
			self.weekact.setText("Day" if i >= 0 and self.datakey[0] == "w" else "Week")
			for a in (self.retagact, self.osviewact):
				a.setEnabled(a is self.osviewact and i >= 0)
			return
		e = self.current
		i = self.shown.index(e) if e in self.shown else -1
		self.prevact.setEnabled(i > 0)
		self.nextact.setEnabled(0 <= i < len(self.shown) - 1)
		self.weekact.setEnabled(self.weektarget(e) is not None)
		self.weekact.setText("Day" if e is not None and e.week else "Week")
		for a in (self.retagact, self.osviewact):
			a.setEnabled(e is not None)

	def step(self, delta):
		if self.datamode:
			self.datastep(delta)
			return
		if not self.shown:
			return
		if self.current not in self.shown:
			self.show_(self.shown[0])
			return
		i = self.shown.index(self.current) + delta
		if 0 <= i < len(self.shown):
			self.show_(self.shown[i])

	def jump(self, last):
		if self.datamode:
			self.datastep(last=last)
			return
		if self.shown:
			self.show_(self.shown[-1] if last else self.shown[0])
		else:
			self.show_(None)

	def weektarget(self, e):
		"""the week profile of day e, or the first day of week profile e"""
		if e is None or self.journal is None:
			return None
		if e.week:
			days = self.journal.daysof(e)
			return days[0] if days else None
		return self.journal.weekof(e)

	def toggleweek(self):
		if self.datamode:
			self.datastep(week=True)
			return
		e = self.current
		if e is None:
			return
		to = self.weektarget(e)
		if to is None:
			self.statusBar().showMessage("No week profile for this day" if not e.week
				else "No days for this week", 3000)
			return
		if to not in self.shown:
			# make sure the list shows it
			(self.daysbox if not to.week else self.weeksbox).setChecked(True)
			if to not in self.shown:
				self.searchbox.clear()
				self.applysearch()
		self.show_(to)

	def matchweek(self):
		"""list the weeks whose profiles look like the one shown so far: the
		week profiles of the captures and the weeks of the m15 data without
		one; in the data view, the weeks of the data, to the end of the day
		shown"""
		e = self.current
		k = self.datakey if self.datamode else (("d", e.day) if e is not None and not e.week else None)
		if self.journal is None:
			return
		if k is not None:	# a day: its week up to the end of it, from the data
			monday = k[1] - timedelta(days=k[1].weekday())
			pts = self.data.profile("w", monday, upto=k[1] if k[0] == "d" else None) if self.data else None
			src = DATAPFX + monday.isoformat()
		elif e is not None and e.week:
			pts = self.profiles.get(e.name)
			monday, src = e.weekmonday(), e.name
		else:
			QMessageBox.information(self, "Match Week", "Show a week profile, a day, or a week or day of the data first.")
			return
		if not pts:
			QMessageBox.information(self, "Match Week", "No week profile found for this week"
				+ ("" if self.data else ": import m15 data to match a day") + ".")
			return
		# the week profiles of the captures and the weeks of the data, but this one
		others = {x.name: self.profiles.get(x.name) for x in self.journal.entries
			if x.week and x.weekmonday() != monday}
		if self.data is not None:
			for w in self.data.weeks():
				if w != monday:
					others[DATAPFX + w.isoformat()] = self.data.profile("w", w)
		others = {n: p for n, p in others.items() if p and not partial(p)}
		self.profsave.start()
		if getattr(self, "matchdlg", None) is not None:
			self.matchdlg.close()	# clears the last match
		found = matches(pts, others)
		self.matchsrc, self.matchend = src, pts[-1][0]
		self.matchpts = pts
		self.matching = dict((n, s) for s, n in found)
		self.list.viewport().update()
		self.datapanel.tree.viewport().update()
		self.matchdlg = MatchDialog(self, src, found[:8])
		self.matchdlg.show()

	def matchday(self):
		"""list the days of the data like the one shown, up to a time"""
		cap = None	# the profile of the day so far in the capture shown
		if self.datamode and self.datakey is not None and self.datakey[0] == "d":
			d = self.datakey[1]
		elif not self.datamode and self.current is not None and not self.current.week:
			d = self.current.day
			try:
				cap = dayprofile(self.journal.path(self.current))
			except Exception:
				cap = None
		else:
			QMessageBox.information(self, "Match Day", "Show a day, a capture or a day of the data, first.")
			return
		if self.data is None or not len(self.data):
			QMessageBox.information(self, "Match Day", "Match Day compares a day with the days of the m15 data: "
				"File ▸ Import Data… adds it.")
			return
		if cap is None and d not in self.data.days():
			QMessageBox.information(self, "Match Day", f"No m15 data for {d:%a %d %b %Y}, and the day can't be "
				"read from this capture: it takes an m15 chart in New York time with the dotted lines at midnight "
				"(and the one before, or the dashed one of the week).")
			return
		if getattr(self, "matchdaydlg", None) is not None:
			self.matchdaydlg.close()
		self.matchdaydlg = MatchDayDialog(self, d, cap)
		self.matchdaydlg.show()

	def showday(self, d):
		"""show day d from Match Day: its capture in the captures, or its chart"""
		if not self.datamode:
			e = [x for x in self.shown if not x.week and x.day == d]
			if e:
				self.show_(e[0])
				return
			self.setdatamode(True)
		self.showdata(("d", d))

	def matchmonday(self, name):
		"""the Monday of the week of a capture or a data week (DATAPFX)"""
		if name.startswith(DATAPFX):
			return date.fromisoformat(name[len(DATAPFX):])
		e = self.journal.find(name) if self.journal else None
		return e.weekmonday() if e else None

	def profileof(self, name):
		"""the week profile of a capture or a data week"""
		if name == self.matchsrc and getattr(self, "matchpts", None):
			return self.matchpts	# so far
		if name.startswith(DATAPFX):
			return self.data.profile("w", self.matchmonday(name)) if self.data else None
		return self.profiles.get(name) if self.profiles else None

	def showmatch(self, name):
		"""show a week of Match Week: its capture, or its chart from the data"""
		if name.startswith(DATAPFX):
			self.setdatamode(True)
			self.showdata(("w", self.matchmonday(name)))
			return
		e = self.journal.find(name) if self.journal else None
		if e is not None:
			self.setdatamode(False)
			self.show_(e)
			self.selectitem(e)

	def resetprofile(self):
		k = self.datakey if self.datamode else None
		if k is None or self.data is None:
			QMessageBox.information(self, "Find the Data Profile Again", "Show a day or week of the data first.")
			return
		if self.adjuster is not None:
			self.adjuster.finish(False)
		self.data.adjust(*k, None)
		self.datapanel.tree.viewport().update()
		self.showdata(k, force=True)

	def adjustprofile(self):
		"""adjust the profile of the week shown on its capture, or of the
		day or week of the data shown on its chart"""
		if self.datamode:
			k = self.datakey
			if k is None or self.data is None or self.view.pixitem is None or self.adjuster is not None:
				return
			if self.datageom is None or self.datageom.periods:
				self.statusBar().showMessage("Profiles are adjusted on the charts of m15 and lower", 5000)
				return
			pts = self.data.profile(*k, prices=True)
			g = self.datageom
			px = g.topx(pts) if pts else [[g.X(g.t0 + 0.05), g.Y((g.top + g.bot) / 2)], [g.X(g.t1 - 0.05), g.Y((g.top + g.bot) / 2)]]
			self.statusBar().showMessage("Drag the profile's points, click a segment to add one, right click one to remove it; "
				"double click or Return when done, Esc to cancel")
			def done(px, k=k, g=g):
				self.adjuster = None
				self.statusBar().clearMessage()
				if px and self.data is not None:
					try:
						self.data.adjust(*k, g.frompx(px))
					except OSError as x:
						self.statusBar().showMessage(f"Can't keep the profile: {x}", 5000)
					self.datapanel.tree.viewport().update()
					if self.datamode and self.datakey == k:
						self.showdata(k, force=True)
			self.adjuster = ProfileEditor(self.view, px, done)
			self.view.setFocus()
			return
		e = self.current
		if e is None or not e.week or self.journal is None or self.view.pixitem is None:
			QMessageBox.information(self, "Adjust Week Profile", "Show a week profile first.")
			return
		if self.adjuster is not None:
			return
		g = self.profiles.geom(e.name)
		if g and g.get("px"):
			px = g["px"]
		else:	# none found: a flat line across the image, to shape
			r = self.view.sceneRect()
			px = [[r.left() + r.width() * .05, r.center().y()], [r.right() - r.width() * .05, r.center().y()]]
		self.statusBar().showMessage("Drag the profile's points, click a segment to add one, right click one to remove it; "
			"double click or Return when done, Esc to cancel")
		self.adjuster = ProfileEditor(self.view, px, lambda px, name=e.name: self.adjusted(name, px))
		self.view.setFocus()

	def adjusted(self, name, px):
		"""the adjusting ended, with the new points or None"""
		self.adjuster = None
		self.statusBar().clearMessage()
		if px:
			self.profiles.adjust(name, px)
		self.list.viewport().update()

	def clearmatch(self):
		"""the match window closed: no more red profiles"""
		self.matchsrc, self.matchend, self.matching = None, None, {}
		self.matchdlg = None
		self.list.viewport().update()

	def scalepanel(self):
		"""scale a chart of the capture shown (see ImageView.startscale)"""
		if self.current is not None:
			self.view.startscale(self.panelscaled)

	def panelscaled(self, img, f, side):
		"""the panel was scaled: replace the capture with img if the user says so"""
		e = self.current
		if e is None or self.journal is None:
			self.view.endscale(False)
			return
		what = {"left": "the left chart", "right": "the right chart"}.get(side, "the image")
		ok = QMessageBox.question(self, "Scale Panel",
			f"Scale {what} ×{f:.3f} and replace {e.name} with the result?",
			QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
			QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
		drawing = self.view.scaledrawing() if ok else None	# its drawings follow the chart
		if ok and not img.save(self.journal.path(e), "PNG"):
			QMessageBox.warning(self, "Scale Panel", f"Can't write {e.name}")
			ok = False
		self.view.endscale(ok)
		if ok:
			if drawing:
				try:
					self.journal.savedrawing(e, drawing)
					self.pending.pop(e.name, None)
				except OSError as x:
					self.pending[e.name] = drawing
					self.statusBar().showMessage(f"Can't save the drawing of {e.name}: {x}", 5000)
				setdrawing(e, drawing)
				self.view.setimage(self.journal.path(e), drawing)
				self.refreshitem(e)
				self.updatetitle()
			self.statusBar().showMessage(f"{e.name} scaled", 3000)

	def osview(self):
		if self.current is not None or (self.datamode and self.view.hasimage()):
			self.view.osview()	# with its drawings

	# ---- notes ----
	def noteschanged(self):
		self.savetimer.start()

	def savenotes(self):
		self.savetimer.stop()
		if self.datamode:	# the notes of a day or week of the data
			k = getattr(self, "datanoteskey", None)
			if k is None or self.data is None:
				return
			text = self.notes.toPlainText()
			if text == self.data.readnotes(*k):
				return
			try:
				self.data.savenotes(*k, text)
			except OSError as x:
				self.statusBar().showMessage(f"Can't save the notes: {x}", 5000)
				return
			self.datapanel.mark()
			self.statusBar().showMessage("Notes saved", 1500)
			return
		e = self.current
		if e is None or self.journal is None:
			return
		text = self.notes.toPlainText()
		if text == e.notes:
			return
		try:
			self.journal.savenotes(e, text)
		except OSError as x:
			self.statusBar().showMessage(f"Can't save the notes: {x}", 5000)
			return
		self.refreshitem(e)
		self.statusBar().showMessage("Notes saved", 1500)

	def refreshitem(self, e):
		"""show e's mark in the list as it is now"""
		it = self.items.get(e.name)
		if it is not None:
			if len(it.data(0, NAMESROLE) or []) < 2:
				it.setText(0, self.itemtext(e))
				it.setToolTip(0, self.itemtip(e))
			self.list.viewport().update()

	# ---- tags ----
	def startocr(self, entries=None):
		if self.journal is None:
			return
		if entries is None:
			entries = [e for e in self.journal.entries if self.journal.needsocr(e)]
			entries.reverse()	# the newest first
		todo = [(e.name, self.journal.path(e)) for e in entries]
		if not todo:
			return
		if self.ocrworker is not None:
			self.ocrpending += [t for t in todo if t not in self.ocrpending]
			return
		self.ocrbar.setRange(0, len(todo))
		self.ocrbar.setValue(0)
		self.ocrbar.show()
		self.ocrlabel.setText("Starting the OCR…")
		self.ocrcount = 0
		self.ocrworker = startocr(self, self.journal.dir, todo,
			self.tagged, self.ocrprogress, self.ocrdone)

	def ocrprogress(self, done, total):
		self.ocrbar.setRange(0, total)
		self.ocrbar.setValue(done)
		self.ocrlabel.setText(f"Reading tags: {done} of {total} done…" if done < total else "")

	def tagged(self, dir, name, raw):
		j = self.journal
		if j is None or dir != j.dir:
			return	# another journal was opened meanwhile
		e = j.find(name)
		if e is None:
			return
		j.settext(e, raw)
		self.ocrcount += 1
		if self.ocrcount % 5 == 0:
			self.savecache()
		if e is self.current:
			self.showtags(e)
		if self.search.expr is not None:
			self.applysearch()
		else:
			it = self.items.get(e.name)
			if it is not None and len(it.data(0, NAMESROLE) or []) < 2:
				it.setToolTip(0, self.itemtip(e))

	def ocrdone(self):
		if self.ocrworker is not None:
			self.ocrworker.deleteLater()
		self.ocrworker = None
		self.ocrbar.hide()
		self.ocrlabel.setText("")
		self.savecache()
		if self.current is not None:
			self.showtags(self.current)
		if self.ocrpending:
			names = [n for n, _ in self.ocrpending]
			self.ocrpending = []
			if self.journal:
				self.startocr([e for e in self.journal.entries if e.name in names])

	def stopocr(self):
		self.ocrpending = []
		if self.ocrworker is not None:
			self.ocrworker.stop()
			self.ocrworker.deleteLater()
			self.savecache()
		self.ocrworker = None
		self.ocrbar.hide()
		self.ocrlabel.setText("")

	def savecache(self):
		if self.journal is None:
			return
		try:
			self.journal.savecache()
		except OSError as e:
			self.statusBar().showMessage(f"Can't save the tags: {e}", 5000)

	def retag(self):
		if self.current is None:
			return
		self.journal.forget(self.current)
		self.showtags(self.current)
		self.startocr([self.current])

	def retagall(self):
		if self.journal is None:
			return
		if QMessageBox.question(self, "Read All Tags Again",
				f"Read the text of all {len(self.journal.entries)} images again? It takes a while.") \
				!= QMessageBox.StandardButton.Yes:
			return
		for e in self.journal.entries:
			self.journal.forget(e)
		self.startocr()

	def about(self):
		QMessageBox.about(self, "About DayJournal",
			"<b>DayJournal</b><p>Browse the day and week chart snapshots of a journal, "
			"search them by the words read from each image, and keep notes for each one.</p>"
			f"<p>Version {VERSION}</p>")

	def closeEvent(self, ev):
		self.savenotes()
		if not self.keepdrawings("quitting"):
			ev.ignore()
			return
		self.stopocr()
		self.savecache()
		super().closeEvent(ev)
