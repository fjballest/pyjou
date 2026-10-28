#
# the main window: the images of a journal on the left, found by a search
# and a calendar, and the image with its tags and notes on the right
#
import html
import json
import os
import subprocess
import sys

from PySide6.QtCore import QDate, QFileSystemWatcher, QMimeData, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QKeySequence, QTextCharFormat
from PySide6.QtWidgets import (
	QApplication, QCalendarWidget, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
	QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
	QProgressBar, QSplitter, QStyle, QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem,
	QVBoxLayout, QWidget
)

from capture import IMAGEEXTS, CaptureDialog, injournal, isimage, savecapture
from journal import Journal, defaultjournals, drawtext, groupkeys
from ocrworker import startocr
from search import Search
from drawbar import DrawBar
from viewer import ImageView

RECENTMAX = 10
CLIPMIME = "application/x-pyjou-capture"	# {"dir", "name", "cut"} of a capture cut or copied
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

	def mkactions(self):
		S = QStyle.StandardPixmap
		self.openact = self.mkaction("&Open Journal…", self.choosejournal, S.SP_DirOpenIcon,
			QKeySequence.StandardKey.Open, "open a journal directory")
		self.saveact = self.mkaction("&Save Drawings", self.savedrawings, S.SP_DialogSaveButton,
			QKeySequence.StandardKey.Save, "save the drawings made")
		self.saveact.setIconText("Save")
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
		self.quitact = self.mkaction("&Quit", self.close, None, QKeySequence.StandardKey.Quit)
		self.quitact.setMenuRole(QAction.MenuRole.QuitRole)
		# cut, copy and paste captures in the list, between journals too
		self.cutact = self.mkaction("Cu&t", lambda: self.clipcapture(True), None,
			QKeySequence.StandardKey.Cut, "cut this capture, to paste it in another journal")
		self.copyact = self.mkaction("&Copy", lambda: self.clipcapture(False), None,
			QKeySequence.StandardKey.Copy, "copy this capture, to paste it in this or another journal")
		self.pasteact = self.mkaction("&Paste", self.pastecapture, None,
			QKeySequence.StandardKey.Paste, "paste the capture cut or copied here, keeping its date")
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
		f.addAction(self.saveact)
		f.addAction(self.addact)
		f.addAction(self.reloadact)
		f.addSeparator()
		f.addAction(self.quitact)
		e = mb.addMenu("&Edit")
		e.addAction(self.undoact)
		e.addAction(self.redoact)
		e.addAction(self.delact)
		e.addSeparator()
		e.addAction(self.findact)
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
		v.addSeparator()
		for a in (self.fitact, self.realact, self.zoominact, self.zoomoutact):
			v.addAction(a)
		v.addSeparator()
		tools = v.addMenu("&Draw")
		for a in self.toolacts.values():
			tools.addAction(a)
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
		self.allbtn = QToolButton()
		self.allbtn.setAutoRaise(True)
		self.allbtn.clicked.connect(self.toggleall)
		kinds = QHBoxLayout()
		kinds.addWidget(self.allbtn)
		kinds.addWidget(self.daysbox)
		kinds.addWidget(self.weeksbox)
		kinds.addStretch()
		kinds.addWidget(self.countlabel)
		self.list = QTreeWidget()
		self.list.setHeaderHidden(True)
		self.list.setIndentation(14)
		self.list.setUniformRowHeights(True)
		self.list.currentItemChanged.connect(self.listchanged)
		self.list.itemClicked.connect(self.groupclicked)
		self.list.itemDoubleClicked.connect(self.itemdoubleclicked)
		self.list.itemExpanded.connect(lambda it: self.groupexpanded(it, True))
		self.list.itemCollapsed.connect(lambda it: self.groupexpanded(it, False))
		self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
		self.list.customContextMenuRequested.connect(self.listmenu)
		for a in (self.cutact, self.copyact, self.pasteact):
			a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)	# not in the notes
			self.list.addAction(a)
		self.items = {}			# entry name -> its tree item
		self.groups = {}		# group key -> its tree item
		self.expanded = set()	# keys of the groups open
		self.calendar = QCalendarWidget()
		self.calendar.setGridVisible(False)
		self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
		self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
		self.calendar.clicked.connect(self.calendarclicked)
		left = self.left = QWidget()
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
		self.view.dclickzoom = False	# a double tap zooms; double clicks are for the drawings
		self.view.navigate.connect(self.navigate)
		self.view.drawchanged.connect(self.drawchanged)
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
		self.setcolor = tb.setcolor
		return tb

	def navigate(self, what):
		{"prev": lambda: self.step(-1), "next": lambda: self.step(1),
			"first": lambda: self.jump(False), "last": lambda: self.jump(True),
			"week": self.toggleweek}[what]()

	def drawchanged(self):
		"""the drawing of the image shown changed: it is pending until saved"""
		e = self.current
		if self.view.loading or e is None or self.journal is None or not self.view.hasimage():
			return
		data = self.view.drawingdata()
		if data == self.journal.readdrawing(e):
			self.pending.pop(e.name, None)	# back as saved
		else:
			self.pending[e.name] = data
		e.drawtext = drawtext(data)
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

	def dragEnterEvent(self, ev):
		if self.journal is not None and self.droppedimages(ev):
			ev.acceptProposedAction()
		else:
			ev.ignore()

	def dragMoveEvent(self, ev):
		self.dragEnterEvent(ev)

	def dropEvent(self, ev):
		paths = self.droppedimages(ev)
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
			try:
				savecapture(self.journal, p, name)
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
		it = self.list.itemAt(pos)
		if it is not None and it.data(0, Qt.ItemDataRole.UserRole) is not None:
			self.list.setCurrentItem(it)	# the capture the menu is for
		self.updateclipacts()
		m = QMenu(self)
		for a in (self.cutact, self.copyact, self.pasteact):
			m.addAction(a)
		m.exec(self.list.viewport().mapToGlobal(pos))

	def listentry(self):
		"""the capture selected in the list, or None"""
		it = self.list.currentItem()
		name = it.data(0, Qt.ItemDataRole.UserRole) if it is not None else None
		return self.journal.find(name) if name and self.journal else None

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
		for name, it in self.items.items():
			it.setData(0, Qt.ItemDataRole.ForegroundRole, QBrush(QColor("gray")) if name == cut else None)

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
		same = os.path.realpath(c["dir"]) == self.journal.dir
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

	def showpanel(self, w, a, on=None):
		"""show or hide panel w (the list or the notes), as action a says"""
		on = a.isChecked() if on is None else on
		a.setChecked(on)
		w.setVisible(on)
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
		name = item.data(0, Qt.ItemDataRole.UserRole)
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
		self.view.commitedit()
		try:
			self.journal.rename(e, name)
		except OSError as x:
			QMessageBox.warning(self, "Change Date", f"Can't rename {e.name}: {x}")
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
		self.watcher.addPath(j.dir)
		addrecent(j.dir)
		self.current = None
		self.initialgroups()
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
				e.drawtext = drawtext(data)
		self.current = self.journal.find(cur) if cur else None
		self.applysearch()
		if self.current is not None and self.journal.mtime(self.current) != before:
			# the image shown changed on disk; otherwise keep its drawing and undo
			self.show_(self.current, force=True)
		self.startocr()

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
		if self.search.expr is not None:
			# show what was found
			for e in self.shown:
				self.expanded.update(k for k, _ in groupkeys(e))
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
		"""the entries shown, in year, month and week groups"""
		self.list.blockSignals(True)
		self.list.clear()
		self.items = {}
		self.groups = {}
		bold = QFont(self.list.font())
		bold.setBold(True)
		for e in self.shown:
			parent = None
			for key, label in groupkeys(e):
				g = self.groups.get(key)
				if g is None:
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
			it = QTreeWidgetItem([self.itemtext(e)])
			it.setData(0, Qt.ItemDataRole.UserRole, e.name)
			if e.week:
				it.setFont(0, bold)
			it.setToolTip(0, self.itemtip(e))
			parent.addChild(it)
			self.items[e.name] = it
		for key, g in self.groups.items():
			n = g.data(0, Qt.ItemDataRole.UserRole + 2)
			g.setText(0, f"{g.data(0, Qt.ItemDataRole.UserRole + 1)}   ({n})")
			g.setExpanded(key in self.expanded)
		self.list.blockSignals(False)
		self.markcut()
		self.updateallbtn()
		total = len(self.journal.entries) if self.journal else 0
		self.countlabel.setText(f"{len(self.shown)} of {total}")

	@staticmethod
	def itemtext(e):
		if e.week:
			s = "Week profile"
		else:
			s = e.day.strftime("%a %d")
			if e.extra:
				s += f" ({e.extra})"
		return s + ("  ✎" if e.notes.strip() else "")

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

	def selectitem(self, e):
		it = self.items.get(e.name) if e is not None else None
		self.list.blockSignals(True)
		if it is None:
			self.list.setCurrentItem(None)
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
		self.list.blockSignals(False)
		self.updateallbtn()

	def listchanged(self, item, _prev):
		if item is None or self.journal is None:
			return
		name = item.data(0, Qt.ItemDataRole.UserRole)
		if name is None:
			return	# a group
		e = self.journal.find(name)
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
		it = self.items.get(e.name)
		if it is not None:
			it.setText(0, self.itemtext(e))
			it.setToolTip(0, self.itemtip(e))
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
			it = self.items.get(e.name)
			if it is not None:
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
			"search them by the words read from each image, and keep notes for each one.</p>")

	def closeEvent(self, ev):
		self.savenotes()
		if not self.keepdrawings("quitting"):
			ev.ignore()
			return
		self.stopocr()
		self.savecache()
		super().closeEvent(ev)
