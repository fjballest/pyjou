#
# View ▸ Queries: the window to ask the journal's data with the language
# of query.py, and see the answer as a table and a chart. The queries saved
# are kept in the journal's queries.txt, a line each: name: query.
#
import os

from PySide6.QtCore import QEvent, QPointF, QRectF, QStringListModel, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QCompleter, QDialog, QHBoxLayout, QHeaderView,
	QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTableWidget,
	QTableWidgetItem, QToolTip, QVBoxLayout, QWidget)

import m15
import query

# the words the line offers as they are typed
ATTRWORDS = sorted(set(query.ATTRS) | {"hour", "time", "day", "session", "date", "minute", "ce", "dq", "uq",
	"size", "settle", "q1", "q2", "q3", "q4", "fvg", "fvgs", "bullfvg", "bearfvg", "lastfvg", "lastbullfvg",
	"lastbearfvg", "rthog", "ndog", "nwog"} | set(query.SESSIONS) | set(query.WEEKDAYS))
WORDS = sorted(set(query.STATS) | query.KEYWORDS | set(query.UNITS) | set(query.WEEKDAYS) | set(query.MONTHS)
	| set(query.SESSIONS) | set(query.CONDS) | set(query.GROUPS) | set(query.GAPS)
	| {"session", "macro", "prev", "next", "weekday", "hour", "above", "below", "inside", "consolidation", "q1", "q2", "q3", "q4"})

QUERYFILE = "queries.txt"
BAR = "#257de0"
EXAMPLES = [
	("High of the week, Monday up", "dist week.high.day where mon is uptrend"),
	("London when Asia consolidates", "dist london.cond where asia is consolidation"),
	("Days by month", "dist day.cond by monthname in 2025"),
	("Consolidating weekdays", "share day is consolidation by weekday"),
	("Asia low, then its high", "share day takes asia.low then asia.high by weekday tf 5"),
	("When the Asia low goes", "dist (when day takes asia.low).session tf 5"),
	("Turtle soups of the Asia low", "share day soups asia.low by weekday tf 5"),
	("Hour of the day's high", "dist day.high.hour"),
	("NY AM range by weekday", "avg nyam.range by weekday in last 12 months"),
	("Where days close, from the RTH gap", "dist day.close.rthog"),
	("RTH gap CE filled in the morning", "share nyam touches rthog.ce by weekday"),
	("NWOG CE touched in the week", "share week touches nwog.ce by year"),
	("Back to London's last bull FVG", "share nyam touches london.lastbullfvg5.ce tf 5"),
	("RTH gap CE rejected", "share nyam rejects rthog.ce by weekday"),
	("RTH gap filled", "share day fills rthog by weekday"),
]

def readqueries(dir):
	"""[(name, query)] saved in the journal"""
	out = []
	try:
		with open(os.path.join(dir, QUERYFILE), encoding="utf-8") as f:
			for line in f:
				line = line.rstrip("\n")
				if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
					continue
				name, q = line.split(":", 1)
				out.append((name.strip(), q.strip()))
	except OSError:
		pass
	return out

def writequeries(dir, qs):
	p = os.path.join(dir, QUERYFILE)
	tmp = p + ".tmp"
	with open(tmp, "w", encoding="utf-8") as f:
		f.write("# the queries of View ▸ Queries: name: query\n")
		for name, q in qs:
			f.write(f"{name.replace(':', ' ')}: {q}\n")
	os.replace(tmp, p)

class Chart(QWidget):
	"""the chart of a query.Result: bars, or a grid of shares"""
	def __init__(self, parent=None):
		super().__init__(parent)
		self.res = None
		self.boxes = []
		self.setMouseTracking(True)
		self.setMinimumSize(420, 220)

	def set(self, res):
		self.res = res
		self.update()

	def paintEvent(self, ev):
		p = QPainter(self)
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		pal = self.palette()
		p.fillRect(self.rect(), pal.base())
		text = pal.text().color()
		faint = QColor(text)
		faint.setAlpha(120)
		grid = QColor(text)
		grid.setAlpha(30)
		f = QFont(self.font())
		f.setPointSizeF(max(8.0, f.pointSizeF() - 1))
		p.setFont(f)
		self.boxes = []
		r = self.res
		if r is None or r.chart is None or not getattr(r, "series", None):
			p.setPen(faint)
			msg = "" if r is None else ("The table has the answer" if r.n else "Nothing counted")
			p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, msg)
			return
		if r.chart == "grid":
			self.paintgrid(p, r, text, faint)
		else:
			self.paintbars(p, r, text, faint, grid)

	def fmt(self, r, v):
		return f"{v:.0f}%" if r.pct else query.show(round(v, 2))

	def paintbars(self, p, r, text, faint, grid):
		vals = list(r.series.values())[0]
		names = r.cats
		W, H = self.width(), self.height()
		fm = QFontMetricsF(p.font())
		L, R, T, B = 50, 12, 16, 40
		pw, ph = W - L - R, H - T - B
		lo = min(0.0, min(vals))
		top = max(vals) if max(vals) > 0 else 1.0
		step = nicestep(top - lo)
		top = step * -(-top // step)
		lo = step * (lo // step) if lo < 0 else 0.0
		span = top - lo or 1
		y = lambda v: T + ph - (v - lo) / span * ph
		v = lo
		while v <= top + 1e-9:
			p.setPen(QPen(grid, 1))
			p.drawLine(QPointF(L, y(v)), QPointF(L + pw, y(v)))
			p.setPen(faint)
			p.drawText(QRectF(0, y(v) - 8, L - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
				self.fmt(r, v))
			v += step
		n = len(vals)
		cw = pw / max(1, n)
		bw = max(2.0, min(40.0, cw * 0.7))
		widest = max((fm.horizontalAdvance(str(x)) for x in names), default=10)
		every = max(1, int(-(-(widest + 8) // cw)))
		for k, (name, val) in enumerate(zip(names, vals)):
			x = L + k * cw + cw / 2
			a, b = y(max(val, 0)), y(min(val, 0))
			p.fillRect(QRectF(x - bw / 2, a, bw, max(0.5, b - a)), QColor(BAR))
			self.boxes.append((QRectF(L + k * cw, T, cw, ph), f"{name}: {self.fmt(r, val)}"))
			if k % every == 0:
				p.setPen(faint)
				p.drawText(QRectF(x - cw * every / 2, T + ph + 4, cw * every, 16), Qt.AlignmentFlag.AlignCenter, str(name))
		p.setPen(QPen(faint, 1))
		p.drawLine(QPointF(L, y(0)), QPointF(L + pw, y(0)))
		p.setPen(faint)
		p.drawText(QRectF(L, H - 20, pw, 16), Qt.AlignmentFlag.AlignCenter, r.headers[0])

	def paintgrid(self, p, r, text, faint):
		rows = list(r.series)
		cols = r.cats
		W, H = self.width(), self.height()
		fm = QFontMetricsF(p.font())
		L = min(W / 3, max(fm.horizontalAdvance(str(x)) for x in rows) + 12)
		T, R, B = 8, 8, 34
		cw = (W - L - R) / max(1, len(cols))
		rh = min(28.0, (H - T - B) / max(1, len(rows)))
		top = max((max(v) for v in r.series.values() if v), default=1) or 1
		base = QColor(BAR)
		every = max(1, int(-(-(max(fm.horizontalAdvance(str(c)) for c in cols) + 6) // cw)))
		for i, name in enumerate(rows):
			y0 = T + i * rh
			p.setPen(faint)
			p.drawText(QRectF(0, y0, L - 6, rh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(name))
			for k, v in enumerate(r.series[name]):
				box = QRectF(L + k * cw + 1, y0 + 1, cw - 2, rh - 2)
				col = QColor(base)
				col.setAlphaF(0.05 + 0.95 * max(0.0, v) / top)
				p.fillRect(box, col)
				if cw > fm.horizontalAdvance("100%") + 4 and rh >= fm.height():
					p.setPen(text if v / top < 0.6 else QColor("white"))
					p.drawText(box, Qt.AlignmentFlag.AlignCenter, self.fmt(r, v))
				self.boxes.append((box, f"{name}, {cols[k]}: {self.fmt(r, v)}"))
		p.setPen(faint)
		y = T + len(rows) * rh + 2
		for k, c in enumerate(cols):
			if k % every == 0:
				p.drawText(QRectF(L + k * cw - cw * (every - 1) / 2, y, cw * every, 16), Qt.AlignmentFlag.AlignCenter, str(c))

	def mouseMoveEvent(self, ev):
		at = ev.position()
		for box, tip in self.boxes:
			if box.contains(at):
				QToolTip.showText(ev.globalPosition().toPoint(), tip, self)
				return
		QToolTip.hideText()

def nicestep(span):
	for s in (1, 2, 2.5, 5):
		for e in range(-3, 7):
			st = s * 10 ** e
			if span / st <= 6:
				return st
	return span / 5

class QueryWindow(QDialog):
	"""View ▸ Queries"""
	def __init__(self, win):
		super().__init__(win)
		self.win = win
		self.dir = win.journal.dir
		self.jour = query.Journal(self.dir)
		self.res = None
		self.setWindowTitle(f"Queries · {getattr(win.data, 'symbol', None) or ''}")
		self.resize(1150, 680)
		lay = QVBoxLayout(self)
		row = QHBoxLayout()
		self.edit = QComboBox()
		self.edit.setEditable(True)
		self.edit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
		self.edit.lineEdit().setPlaceholderText("dist week.high.day where mon is uptrend")
		self.edit.lineEdit().returnPressed.connect(self.enter)
		self.edit.setCompleter(None)
		self.words = QCompleter(self)
		self.words.setModel(QStringListModel(WORDS, self.words))
		self.words.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
		self.words.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
		self.words.setWidget(self.edit.lineEdit())
		self.words.activated[str].connect(self.complete)
		self.edit.lineEdit().textEdited.connect(self.prompt)
		self.edit.lineEdit().installEventFilter(self)	# Tab completes
		self.words.popup().installEventFilter(self)
		self.edit.setToolTip("a query: count, share, dist, avg, median, min, max or list, what, and then by, "
			"where, in and tf; Help ▸ Manual, Queries, has it all")
		row.addWidget(self.edit, 1)
		self.tfbox = QComboBox()
		self.tfbox.setToolTip("the time frame of the candles, when the query says no tf: highs, lows and "
			"what was taken are found in it")
		for tf in [1, 2, 3, 5, 15, 30, 60]:
			self.tfbox.addItem(m15.tfname(tf), tf)
		self.tfbox.setCurrentIndex(4)
		row.addWidget(self.tfbox)
		runb = QPushButton("Run")
		runb.setDefault(True)
		runb.clicked.connect(self.run)
		row.addWidget(runb)
		lay.addLayout(row)
		self.error = QLabel()
		self.error.setStyleSheet("color: #e0453a")
		self.error.setWordWrap(True)
		self.error.hide()
		lay.addWidget(self.error)
		split = QSplitter(Qt.Orientation.Horizontal)
		side = QWidget()
		sl = QVBoxLayout(side)
		sl.setContentsMargins(0, 0, 0, 0)
		sl.addWidget(QLabel("Saved queries"))
		self.saved = QListWidget()
		self.saved.itemClicked.connect(self.pick)
		self.saved.itemActivated.connect(self.pick)
		sl.addWidget(self.saved, 1)
		bl = QHBoxLayout()
		self.savebtn = QPushButton("Save…")
		self.savebtn.setToolTip("keep the query in the journal, with a name")
		self.savebtn.clicked.connect(self.save)
		self.delbtn = QPushButton("Remove")
		self.delbtn.clicked.connect(self.remove)
		bl.addWidget(self.savebtn)
		bl.addWidget(self.delbtn)
		sl.addLayout(bl)
		split.addWidget(side)
		right = QSplitter(Qt.Orientation.Vertical)
		self.chart = Chart()
		right.addWidget(self.chart)
		self.table = QTableWidget()
		self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
		self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
		self.table.verticalHeader().hide()
		self.table.cellClicked.connect(self.showperiod)
		right.addWidget(self.table)
		right.setSizes([380, 260])
		split.addWidget(right)
		split.setSizes([230, 920])
		lay.addWidget(split, 1)
		self.summary = QLabel()
		self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
		lay.addWidget(self.summary)
		bottom = QHBoxLayout()
		cond = QPushButton("Conditions…")
		cond.setToolTip("the thresholds of trend, consolidation and reversal, as parts of the range of the period, in the journal's conditions.txt")
		cond.clicked.connect(self.conditions)
		bottom.addWidget(cond)
		bottom.addStretch(1)
		close = QPushButton("Close")
		close.setAutoDefault(False)
		close.clicked.connect(self.close)
		bottom.addWidget(close)
		lay.addLayout(bottom)
		self.fillsaved()

	def fillsaved(self):
		self.saved.clear()
		qs = readqueries(self.dir)
		self.examples = not qs
		for name, q in qs or EXAMPLES:
			it = QListWidgetItem(name)
			it.setToolTip(q)
			it.setData(Qt.ItemDataRole.UserRole, q)
			self.saved.addItem(it)
		self.delbtn.setEnabled(not self.examples)

	def pick(self, it):
		self.edit.setEditText(it.data(Qt.ItemDataRole.UserRole))
		self.run()

	def save(self):
		text = self.edit.currentText().strip()
		if not text:
			return
		name, ok = QInputDialog.getText(self, "Save Query", "Name:", text=self.saved.currentItem().text()
			if self.saved.currentItem() and not self.examples else "")
		if not ok or not name.strip():
			return
		qs = [] if self.examples else readqueries(self.dir)
		qs = [(n, q) for n, q in qs if n != name.strip()] + [(name.strip(), text)]
		writequeries(self.dir, qs)
		self.fillsaved()

	def remove(self):
		it = self.saved.currentItem()
		if it is None or self.examples:
			return
		writequeries(self.dir, [(n, q) for n, q in readqueries(self.dir) if n != it.text()])
		self.fillsaved()

	def conditions(self):
		p = query.writedefaults(self.dir)
		from PySide6.QtGui import QDesktopServices
		from PySide6.QtCore import QUrl
		QDesktopServices.openUrl(QUrl.fromLocalFile(p))

	def filter(self):
		w = self.win
		return w.filtered() if hasattr(w, "filtered") else None

	def wordat(self):
		"""the word being typed: (start, prefix, after a dot)"""
		le = self.edit.lineEdit()
		text, pos = le.text(), le.cursorPosition()
		a = pos
		while a > 0 and (text[a - 1].isalnum() or text[a - 1] in "_:"):
			a -= 1
		return a, text[a:pos], a > 0 and text[a - 1] == "."

	def wordlist(self, dot):
		"""the words offered: after a dot, what things have; else the words of
		the language and the names defined in the journal"""
		if dot:
			return ATTRWORDS
		return sorted(set(WORDS) | set(self.jour.defs()))

	def candidates(self):
		"""the words the one being typed may be"""
		a, pre, dot = self.wordat()
		if not pre or pre[0].isdigit():
			return []
		return [w for w in self.wordlist(dot) if w.lower().startswith(pre.lower())]

	def eventFilter(self, obj, ev):
		if ev.type() == QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_Tab \
				and ev.modifiers() in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.KeypadModifier):
			self.tab()
			return True
		return super().eventFilter(obj, ev)

	def tab(self):
		"""Tab: the word picked in the list offered, the only one there is, or
		as much as all of them share, offering them; with several and none
		picked, it only shows them"""
		pop = self.words.popup()
		if pop.isVisible():
			i = pop.currentIndex()
			if i.isValid() and pop.selectionModel().isSelected(i):
				pop.hide()
				self.complete(i.data())
				return
		ws = self.candidates()
		if not ws:
			return
		if len(ws) == 1:
			self.complete(ws[0])
			return
		common = os.path.commonprefix([w.lower() for w in ws])
		_, pre, _ = self.wordat()
		if len(common) > len(pre):
			self.complete(ws[0][:len(common)])
		self.prompt(None, force=True)

	def prompt(self, _, force=False):
		"""offers the words starting as the one being typed"""
		a, pre, dot = self.wordat()
		if len(pre) < 1 or pre[0].isdigit():
			self.words.popup().hide()
			return
		self.words.model().setStringList(self.wordlist(dot))
		self.words.setCompletionPrefix(pre)
		if self.words.completionCount() == 0 or (not force and self.words.completionCount() == 1 and self.words.currentCompletion() == pre):
			self.words.popup().hide()
			return
		r = self.edit.lineEdit().cursorRect()
		r.setWidth(self.words.popup().sizeHintForColumn(0) + self.words.popup().verticalScrollBar().sizeHint().width() + 8)
		self.words.complete(r)

	def complete(self, word):
		le = self.edit.lineEdit()
		a, pre, _ = self.wordat()
		text, pos = le.text(), le.cursorPosition()
		le.setText(text[:a] + word + text[pos:])
		le.setCursorPosition(a + len(word))

	def enter(self):
		if self.words.popup().isVisible():
			return	# the completer takes it
		self.run()

	def run(self):
		text = self.edit.currentText().strip()
		if not text:
			return
		if self.edit.findText(text) < 0:
			self.edit.insertItem(0, text)
		self.error.hide()
		try:
			said = self.jour.define(text)	# name := what it stands for
		except query.QueryError as e:
			self.error.setText(str(e))
			self.error.show()
			return
		if said is not None:
			self.summary.setText(said + ", in the journal's definitions.txt")
			return
		QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
		try:
			only = self.filter()
			self.res = self.jour.run(text, self.tfbox.currentData(), only)
		except query.QueryError as e:
			self.res = None
			at = f" (at “{text[e.pos:e.pos + 12]}”)" if e.pos is not None and e.pos < len(text) else ""
			self.error.setText(f"{e}{at}")
			self.error.show()
			self.chart.set(None)
			return
		finally:
			QApplication.restoreOverrideCursor()
		self.show_(self.res, only is not None)

	def show_(self, r, filtered=False):
		self.chart.set(r)
		t = self.table
		t.clear()
		t.setColumnCount(len(r.headers))
		t.setRowCount(len(r.rows))
		t.setHorizontalHeaderLabels([str(h) for h in r.headers])
		for i, row in enumerate(r.rows):
			for k, v in enumerate(row):
				it = QTableWidgetItem(str(v))
				if k:
					it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
				t.setItem(i, k, it)
		t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
		self.summary.setText(r.summary().capitalize() + (", of those the search leaves in the list" if filtered else "")
			+ (". Click one to see it." if r.q["stat"] == "list" else ""))

	def showperiod(self, row, _col=0):
		"""a period of a list, shown in the data view"""
		r = self.res
		if r is None or r.q["stat"] != "list" or row >= len(r.periods):
			return
		w = self.win
		p = r.periods[row]
		if not hasattr(w, "setdatamode"):
			return
		if not w.datamode:
			w.setdatamode(True)
		if not w.datamode:
			return
		key = ("w", p.date()) if p.kind == "week" else ("d", p.date())
		w.showdata(key, force=True)
		w.raise_()
