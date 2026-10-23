#
# the main window: the images of a journal on the left, found by a search
# and a calendar, and the image with its tags and notes on the right
#
import html
import os
import subprocess
import sys

from PySide6.QtCore import QDate, QFileSystemWatcher, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QKeySequence, QShortcut, QTextCharFormat
from PySide6.QtWidgets import (
	QCalendarWidget, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
	QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
	QProgressBar, QSplitter, QStyle, QToolBar, QToolButton, QVBoxLayout, QWidget
)

from journal import Journal, defaultjournals
from ocrworker import startocr
from search import Search
from viewer import ImageView

RECENTMAX = 10
SAVEDELAY = 800		# ms after the last key before notes are saved
SEARCHTIP = ("<p>Show the images whose tags or notes have these words, ignoring case.</p>"
	"<p>Words one after another must all be there, <b>|</b> means or, <b>!</b> means not, "
	"and parentheses group: <code>(a b) | !(c d)</code>.</p>"
	"<p>A final lowercase s is optional (EQL finds EQLs) and <b>*</b> matches any letters "
	"within a word (EQ*). Esc empties the search.</p>")

def settings():
	return QSettings("pyjou", "DayJournal")

def recentjournals():
	v = settings().value("recent", [])
	if isinstance(v, str):
		v = [v]
	return [p for p in (v or []) if p]

def addrecent(path):
	path = os.path.abspath(path)
	l = [path] + [p for p in recentjournals() if p != path]
	settings().setValue("recent", l[:RECENTMAX])

class SearchEdit(QLineEdit):
	def keyPressEvent(self, ev):
		if ev.key() == Qt.Key.Key_Escape and self.text():
			self.clear()
			return
		super().keyPressEvent(ev)

class MainWindow(QMainWindow):
	def __init__(self, path=None):
		super().__init__()
		self.journal = None
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

		self.mkactions()
		self.mktoolbar()
		self.mkmenus()
		self.mkwidgets()
		self.mkshortcuts()
		self.resize(1500, 950)
		self.updatetitle()

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

	def mkactions(self):
		S = QStyle.StandardPixmap
		self.openact = self.mkaction("&Open Journal…", self.choosejournal, S.SP_DirOpenIcon,
			QKeySequence.StandardKey.Open, "open a journal directory")
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
		self.fitact = self.mkaction("Fit", lambda: self.view.fit(), None, "Ctrl+0", "fit the image in the window")
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
		self.findact = self.mkaction("&Search", lambda: (self.searchbox.setFocus(), self.searchbox.selectAll()),
			None, QKeySequence.StandardKey.Find, "search the tags and notes")
		self.notesact = self.mkaction("Edit &Notes", lambda: self.notes.setFocus(), None, "Ctrl+N",
			"write notes for this image")
		self.quitact = self.mkaction("&Quit", self.close, None, QKeySequence.StandardKey.Quit)
		self.quitact.setMenuRole(QAction.MenuRole.QuitRole)
		self.recentmenu = QMenu("Open &Recent", self)
		self.recentmenu.aboutToShow.connect(self.fillrecent)

	def mktoolbar(self):
		tb = QToolBar("Journal", self)
		tb.setObjectName("journaltoolbar")
		tb.setMovable(False)
		tb.setIconSize(QSize(18, 18))
		tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
		ob = QToolButton(tb)
		ob.setDefaultAction(self.openact)
		self.openact.setIconText("Open")
		ob.setMenu(self.recentmenu)
		ob.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
		ob.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
		tb.addWidget(ob)
		tb.addAction(self.reloadact)
		tb.addSeparator()
		for a in (self.firstact, self.prevact, self.nextact, self.todayact, self.weekact):
			tb.addAction(a)
		tb.addSeparator()
		for a in (self.fitact, self.realact, self.zoominact, self.zoomoutact):
			tb.addAction(a)
		self.addToolBar(tb)

	def mkmenus(self):
		mb = self.menuBar()
		f = mb.addMenu("&File")
		f.addAction(self.openact)
		f.addMenu(self.recentmenu)
		f.addAction(self.reloadact)
		f.addSeparator()
		f.addAction(self.quitact)
		e = mb.addMenu("&Edit")
		e.addAction(self.findact)
		e.addAction(self.notesact)
		e.addSeparator()
		e.addAction(self.retagact)
		e.addAction(self.retagallact)
		g = mb.addMenu("&Go")
		for a in (self.firstact, self.prevact, self.nextact, self.todayact, self.weekact):
			g.addAction(a)
		v = mb.addMenu("&View")
		for a in (self.fitact, self.realact, self.zoominact, self.zoomoutact):
			v.addAction(a)
		v.addSeparator()
		v.addAction(self.osviewact)
		h = mb.addMenu("&Help")
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
		kinds = QHBoxLayout()
		kinds.addWidget(self.daysbox)
		kinds.addWidget(self.weeksbox)
		kinds.addStretch()
		kinds.addWidget(self.countlabel)
		self.list = QListWidget()
		self.list.currentItemChanged.connect(self.listchanged)
		self.calendar = QCalendarWidget()
		self.calendar.setGridVisible(False)
		self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
		self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
		self.calendar.clicked.connect(self.calendarclicked)
		left = QWidget()
		ll = QVBoxLayout(left)
		ll.setContentsMargins(4, 4, 4, 4)
		ll.addWidget(self.searchbox)
		ll.addLayout(kinds)
		ll.addWidget(self.list, 1)
		ll.addWidget(self.calendar)

		# right: title, image, tags, notes
		self.titlelabel = QLabel()
		f = self.titlelabel.font()
		f.setBold(True)
		f.setPointSizeF(f.pointSizeF() * 1.2)
		self.titlelabel.setFont(f)
		self.view = ImageView()
		self.tagslabel = QLabel()
		self.tagslabel.setWordWrap(True)
		self.tagslabel.setTextFormat(Qt.TextFormat.RichText)
		self.tagslabel.setToolTip("tags read from the image; click one to search it")
		self.tagslabel.linkActivated.connect(self.tagclicked)
		self.notes = QPlainTextEdit()
		self.notes.setPlaceholderText("Notes for this image. They are saved as you type, "
			"in a .txt file next to it.")
		self.notes.textChanged.connect(self.noteschanged)
		bottom = QWidget()
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
		rl.addWidget(self.titlelabel)
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

	def mkshortcuts(self):
		# arrows move through the images while the image has the focus
		ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
		for key, fn in ((Qt.Key.Key_Left, lambda: self.step(-1)), (Qt.Key.Key_Right, lambda: self.step(1)),
				(Qt.Key.Key_Up, lambda: self.step(-1)), (Qt.Key.Key_Down, lambda: self.step(1)),
				(Qt.Key.Key_Home, lambda: self.jump(False)), (Qt.Key.Key_End, lambda: self.jump(True)),
				(Qt.Key.Key_W, self.toggleweek)):
			s = QShortcut(QKeySequence(key), self.view, fn)
			s.setContext(ctx)
		self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

	# ---- journals ----
	def startjournal(self):
		"""the last journal used, or the first one found"""
		for p in recentjournals() + defaultjournals():
			if os.path.isdir(p):
				return p
		return None

	def choosejournal(self):
		start = self.journal.dir if self.journal else (defaultjournals() or [os.path.expanduser("~")])[0]
		d = QFileDialog.getExistingDirectory(self, "Open Journal", os.path.dirname(start))
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
		self.stopocr()
		try:
			j = Journal(path)
		except OSError as e:
			QMessageBox.warning(self, "Open Journal", f"Can't open {path}: {e}")
			return
		if self.watcher.directories():
			self.watcher.removePaths(self.watcher.directories())
		self.journal = j
		self.watcher.addPath(j.dir)
		addrecent(j.dir)
		self.current = None
		self.applysearch(keep=False)
		self.jump(True)
		self.updatetitle()
		self.startocr()

	def reload(self):
		if self.journal is None:
			return
		self.savenotes()
		cur = self.current.name if self.current else None
		self.journal.load()
		self.current = self.journal.find(cur) if cur else None
		self.applysearch()
		if self.current is not None:
			self.show_(self.current, force=True)
		self.startocr()

	def updatetitle(self):
		if self.journal is None:
			self.setWindowTitle("DayJournal")
			return
		n = len(self.journal.entries)
		self.setWindowTitle(f"DayJournal — {os.path.basename(self.journal.dir)} ({n} images)")

	# ---- search and list ----
	def searchchanged(self, text):
		err = Search.error(text)
		self.searchbox.setStyleSheet("QLineEdit { color: #c62828; }" if err else "")
		self.searchbox.setToolTip(f"<p><b>{html.escape(err)}</b></p>{SEARCHTIP}" if err else SEARCHTIP)
		if err is None:
			self.searchtimer.start()
		else:
			self.searchtimer.stop()

	def applysearch(self, keep=True):
		if self.journal is None:
			return
		text = self.searchbox.text().strip()
		try:
			self.search = Search(text)
		except ValueError:
			return	# keep the last good search
		days, weeks = self.daysbox.isChecked(), self.weeksbox.isChecked()
		self.shown = [e for e in self.journal.entries
			if (weeks if e.week else days) and self.search.match(e)]
		self.fillist()
		if keep and self.current is not None and self.current in self.shown:
			self.selectitem(self.current)
		elif keep and self.shown and self.current is not None:
			# the one shown went away: go to the nearest date
			self.show_(self.journal.nearest(self.current.day, self.shown))
		elif not self.shown:
			self.show_(None)
		self.markcalendar()

	def fillist(self):
		self.list.blockSignals(True)
		self.list.clear()
		bold = QFont(self.list.font())
		bold.setBold(True)
		for e in self.shown:
			it = QListWidgetItem(e.label())
			it.setData(Qt.ItemDataRole.UserRole, e.name)
			if e.week:
				it.setFont(bold)
			tip = " ".join(e.tags[:30])
			if e.notes.strip():
				it.setText(e.label() + "  ✎")
				tip = e.notes.strip()[:300] + ("\n\n" + tip if tip else "")
			it.setToolTip(tip)
			self.list.addItem(it)
		self.list.blockSignals(False)
		total = len(self.journal.entries) if self.journal else 0
		self.countlabel.setText(f"{len(self.shown)} of {total}")

	def selectitem(self, e):
		i = self.shown.index(e) if e in self.shown else -1
		self.list.blockSignals(True)
		self.list.setCurrentRow(i)
		self.list.blockSignals(False)
		if i >= 0:
			self.list.scrollToItem(self.list.item(i))

	def listchanged(self, item, _prev):
		if item is None or self.journal is None:
			return
		e = self.journal.find(item.data(Qt.ItemDataRole.UserRole))
		if e is not None:
			self.show_(e)

	def markcalendar(self):
		self.calendar.setDateTextFormat(QDate(), QTextCharFormat())	# clear
		if self.journal is None:
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
		if e is self.current and not force:
			self.selectitem(e)
			return
		self.savenotes()
		self.current = e
		self.notes.blockSignals(True)
		if e is None:
			self.view.setimage(None)
			self.titlelabel.setText("No images" if self.journal else "No journal open")
			self.tagslabel.clear()
			self.notes.setPlainText("")
			self.notes.setEnabled(False)
		else:
			self.view.setimage(self.journal.path(e))
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
		e = self.current
		i = self.shown.index(e) if e in self.shown else -1
		self.prevact.setEnabled(i > 0)
		self.nextact.setEnabled(0 <= i < len(self.shown) - 1)
		self.weekact.setEnabled(self.weektarget(e) is not None)
		self.weekact.setText("Day" if e is not None and e.week else "Week")
		for a in (self.retagact, self.osviewact):
			a.setEnabled(e is not None)

	def step(self, delta):
		if not self.shown:
			return
		if self.current not in self.shown:
			self.show_(self.shown[0])
			return
		i = self.shown.index(self.current) + delta
		if 0 <= i < len(self.shown):
			self.show_(self.shown[i])

	def jump(self, last):
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

	def osview(self):
		if self.current is None:
			return
		p = self.journal.path(self.current)
		if sys.platform == "darwin":
			subprocess.Popen(["open", p])
		elif sys.platform.startswith("win"):
			os.startfile(p)
		else:
			subprocess.Popen(["xdg-open", p])

	# ---- notes ----
	def noteschanged(self):
		self.savetimer.start()

	def savenotes(self):
		self.savetimer.stop()
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
		i = self.shown.index(e) if e in self.shown else -1
		if i >= 0:
			it = self.list.item(i)
			it.setText(e.label() + ("  ✎" if text.strip() else ""))
		self.statusBar().showMessage("Notes saved", 1500)

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
			i = self.shown.index(e) if e in self.shown else -1
			if i >= 0:
				self.list.item(i).setToolTip(" ".join(e.tags[:30]))

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
			"search them by the words read from each image, and keep notes for each one.</p>")

	def closeEvent(self, ev):
		self.savenotes()
		self.stopocr()
		self.savecache()
		super().closeEvent(ev)
