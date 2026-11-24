#
# the data view: the weeks and days of the m15 data (m15.py) in a list,
# each with its profile, and a chart of the one picked drawn from the
# candles, with its sessions and its profile, shown in the window's image
# view instead of a capture.
#
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import (
	QCheckBox, QHBoxLayout, QLabel, QStyle, QStyledItemDelegate, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
)

import m15

KEYROLE = Qt.ItemDataRole.UserRole + 10	# ("w" or "d", date) of a row

UP, DOWN = QColor("#089981"), QColor("#f23645")
PROFCOLOR = QColor("#26c6da")
DAYLINE = QColor(41, 100, 249)	# the days' and the week's lines, as in the week captures

def trange(kind):
	"""the times a chart or profile of kind spans: hours of a day, days of a week"""
	return (m15.DAYSTART, m15.DAYEND) if kind == "d" else (-0.25, 4 + 17/24)

def nicestep(span, n):
	"""a round step to cut span in about n parts"""
	raw = span / max(1, n)
	p = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 1
	for k in (1, 2, 2.5, 5, 10):
		if raw <= k * p:
			return k * p
	return 10 * p

def title(data, kind, d):
	if kind == "w":
		return f"{data.symbol} m15 · Week {d:%d %b} – {d + timedelta(days=4):%d %b %Y}"
	return f"{data.symbol} m15 · {d:%a %d %b %Y}"

def render(data, kind, d, path=None):
	"""the chart of day d or week d (its Monday) as a QImage, saved at path
	when given; None without candles"""
	i, j, zero = data.span(kind, d)
	if j <= i:
		return None
	W, H = (1800, 1000) if kind == "d" else (2400, 1100)
	L, R, T, B = 16, 100, 44, 40
	pw, ph = W - L - R, H - T - B
	t0, t1 = trange(kind)
	hi, lo = float(data.h[i:j].max()), float(data.l[i:j].min())
	pad = (hi - lo) * 0.04 or 1
	top, bot = hi + pad, lo - pad
	X = lambda t: L + (t - t0) / (t1 - t0) * pw
	Y = lambda p: T + (top - p) / (top - bot) * ph
	unit = 3600 if kind == "d" else 86400
	slot = 900 / unit / (t1 - t0) * pw	# pixels per candle

	img = QImage(W, H, QImage.Format.Format_RGB32)
	img.fill(QColor("white"))
	p = QPainter(img)
	p.setRenderHint(QPainter.RenderHint.Antialiasing)
	f = QFont()
	f.setPixelSize(15)
	p.setFont(f)
	grid = QColor(235, 237, 240)
	axis = QColor(120, 123, 134)

	# price levels
	step = nicestep(top - bot, 10)
	v = (bot // step + 1) * step
	while v < top:
		y = Y(v)
		p.setPen(QPen(grid, 1))
		p.drawLine(QPointF(L, y), QPointF(L + pw, y))
		p.setPen(axis)
		p.drawText(QRectF(L + pw + 6, y - 10, R - 10, 20), Qt.AlignmentFlag.AlignVCenter, m15.price(v))
		v += step

	# time: the hours of a day, the days of a week
	if kind == "d":
		for h in range(m15.DAYSTART, m15.DAYEND + 1, 2):
			x = X(h)
			p.setPen(QPen(grid, 1))
			p.drawLine(QPointF(x, T), QPointF(x, T + ph))
			p.setPen(axis)
			p.drawText(QRectF(x - 30, T + ph + 6, 60, 20), Qt.AlignmentFlag.AlignCenter, f"{h % 24:02d}:00")
		p.setPen(QPen(DAYLINE, 2, Qt.PenStyle.DotLine))
		p.drawLine(QPointF(X(0), T), QPointF(X(0), T + ph))
	else:
		p.setPen(QPen(DAYLINE, 2, Qt.PenStyle.DashLine))
		p.drawLine(QPointF(X(-0.25), T), QPointF(X(-0.25), T + ph))
		for k in range(5):
			p.setPen(QPen(DAYLINE, 2, Qt.PenStyle.DotLine))
			p.drawLine(QPointF(X(k), T), QPointF(X(k), T + ph))
			p.setPen(axis)
			day = d + timedelta(days=k)
			p.drawText(QRectF(X(k), T + ph + 6, X(k + 0.7) - X(k), 20), Qt.AlignmentFlag.AlignCenter, f"{day:%a %d}")

	# the sessions of a day, as boxes from their high to their low
	if kind == "d":
		for name, a, b, sh, sl, _, _, color in data.sessions(d):
			c = QColor(color)
			fill = QColor(c)
			fill.setAlpha(38)
			edge = QColor(c)
			edge.setAlpha(150)
			r = QRectF(QPointF(X(a), Y(sh)), QPointF(X(b), Y(sl)))
			p.setPen(QPen(edge, 1))
			p.setBrush(fill)
			p.drawRect(r)
			p.setPen(edge)
			p.drawText(QRectF(r.left() + 4, r.top() - 20, 200, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, name)
		p.setBrush(Qt.BrushStyle.NoBrush)

	# the candles
	bw = max(1.0, slot * 0.7)
	for k in range(i, j):
		x = X(data.tof(kind, k, zero)) + slot / 2
		o, h, l, c = data.o[k], data.h[k], data.l[k], data.c[k]
		col = UP if c >= o else DOWN
		p.setPen(QPen(col, 1 if slot < 6 else 1.4))
		p.drawLine(QPointF(x, Y(h)), QPointF(x, Y(l)))
		y0, y1 = Y(max(o, c)), Y(min(o, c))
		p.fillRect(QRectF(x - bw / 2, y0, bw, max(1.0, y1 - y0)), col)

	# the profile
	pts = data.profile(kind, d, prices=True)
	if pts:
		line = QPolygonF([QPointF(X(t), Y(v)) for t, v in pts])
		p.setPen(QPen(PROFCOLOR, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
		p.drawPolyline(line)
		p.setBrush(QColor("white"))
		p.setPen(QPen(PROFCOLOR.darker(130), 2))
		for q in list(line)[1:-1]:
			p.drawEllipse(q, 6, 6)
		p.setBrush(Qt.BrushStyle.NoBrush)

	# the title
	f.setPixelSize(20)
	f.setBold(True)
	p.setFont(f)
	p.setPen(QColor(40, 40, 40))
	p.drawText(QRectF(L, 8, pw, 30), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title(data, kind, d) + "   (New York time)")
	p.end()
	if path:
		img.save(path)
	return img

def drawpts(painter, box, kind, pts, pal, selected=False, upto=None):
	"""draw profile pts of kind in box: the midnights faint behind it, and
	the sessions of a day; the part before upto (a match) in red"""
	t0, t1 = trange(kind)
	x = lambda t: box.left() + (t - t0) / (t1 - t0) * box.width()
	y = lambda v: box.bottom() - v * box.height()
	painter.save()
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	if kind == "d":
		for name, a, b, color in m15.SESSIONS:
			c = QColor(color)
			c.setAlpha(45)
			painter.fillRect(QRectF(x(a), box.top(), x(b) - x(a), box.height()), c)
	painter.setPen(QPen(pal.color(QPalette.ColorRole.Mid), 0.5, Qt.PenStyle.DotLine))
	for t in ([0] if kind == "d" else range(6)):
		painter.drawLine(QPointF(x(t), box.top()), QPointF(x(t), box.bottom()))
	line = QPolygonF([QPointF(x(t), y(v)) for t, v in pts])
	painter.setPen(QPen(pal.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Highlight), 1.5))
	if upto is None:
		painter.drawPolyline(line)
	else:	# the rest, then the part matched over it in red
		painter.save()
		painter.setClipRect(QRectF(x(upto), box.top() - 2, box.right() - x(upto) + 4, box.height() + 4))
		painter.drawPolyline(line)
		painter.restore()
		painter.setClipRect(QRectF(box.left() - 4, box.top() - 2, x(upto) - box.left() + 4, box.height() + 4))
		painter.setPen(QPen(QColor("#e53935"), 2))
		painter.drawPolyline(line)
	painter.restore()

class DataDelegate(QStyledItemDelegate):
	"""a row of the data list, with its profile at the right"""
	def __init__(self, panel):
		super().__init__(panel.tree)
		self.panel = panel

	def sizeHint(self, option, index):
		s = super().sizeHint(option, index)
		s.setHeight(max(s.height(), 2 * option.fontMetrics.height() + 4))
		return s

	def paint(self, painter, option, index):
		super().paint(painter, option, index)
		key = index.data(KEYROLE)
		data = self.panel.data
		if not key or data is None:
			return
		kind, d = key
		pts = data.profile(kind, d)
		r = option.rect
		w = min(110, r.width() // 2)
		box = QRectF(r.right() - w - 4, r.top() + 3, w, r.height() - 6)
		if pts and box.height() >= 6:
			drawpts(painter, box, kind, pts, option.palette, bool(option.state & QStyle.StateFlag.State_Selected))

GROUPROLE = Qt.ItemDataRole.UserRole + 11	# ("m", year, month) of a month group

class DataPanel(QWidget):
	"""the weeks of the data, each with its days, in month groups, and
	their profiles; the Weeks and Days boxes leave out either, and the
	groups open and close as in the list of captures"""
	picked = Signal(str, object)	# kind, date

	def __init__(self, win):
		super().__init__()
		self.win = win
		self.data = None
		self.rows = {}	# (kind, date) -> its row
		self.groups = {}	# ("m", y, m) and ("w", date) -> the item that holds others
		self.expanded = None	# keys of the groups open; None: the last ones
		lay = QVBoxLayout(self)
		lay.setContentsMargins(0, 0, 0, 0)
		top = QHBoxLayout()
		self.info = QLabel()
		self.info.setWordWrap(True)
		top.addWidget(self.info, 1)
		self.importbtn = QToolButton()
		self.importbtn.setText("Import…")
		self.importbtn.setAutoRaise(True)
		top.addWidget(self.importbtn)
		self.backbtn = QToolButton()
		self.backbtn.setText("Captures")
		self.backbtn.setAutoRaise(True)
		self.backbtn.setToolTip("back to the captures, on this day or week")
		top.addWidget(self.backbtn)
		lay.addLayout(top)
		kinds = QHBoxLayout()
		self.allbtn = QToolButton()
		self.allbtn.setAutoRaise(True)
		self.allbtn.clicked.connect(self.toggleall)
		kinds.addWidget(self.allbtn)
		for text, level, tip in (("m", "m", "collapse to months, showing the weeks of the last month and the days of its last week"),
				("w", "w", "collapse to weeks, showing the days of the last week")):
			b = QToolButton()
			b.setText(text)
			b.setAutoRaise(True)
			b.setToolTip(tip)
			b.clicked.connect(lambda _=False, l=level: self.collapseto(l))
			kinds.addWidget(b)
		self.daysbox = QCheckBox("Days")
		self.weeksbox = QCheckBox("Weeks")
		for b in (self.daysbox, self.weeksbox):
			b.setChecked(True)
			b.toggled.connect(lambda _=False: self.refill())
			kinds.addWidget(b)
		kinds.addStretch()
		lay.addLayout(kinds)
		self.tree = QTreeWidget()
		self.tree.setHeaderHidden(True)
		self.tree.setIndentation(14)
		self.tree.setUniformRowHeights(True)
		self.tree.setItemDelegate(DataDelegate(self))
		self.tree.currentItemChanged.connect(self.changed)
		self.tree.itemExpanded.connect(lambda it: self.groupopen(it, True))
		self.tree.itemCollapsed.connect(lambda it: self.groupopen(it, False))
		lay.addWidget(self.tree, 1)
		self.updateallbtn()

	def refill(self):
		cur = self.tree.currentItem()
		key = cur.data(0, KEYROLE) if cur is not None else None
		self.fill(self.data)
		if key in self.rows:
			self.select(key)

	def groupkey(self, it):
		return it.data(0, GROUPROLE) if it is not None else None

	def groupopen(self, it, open):
		k = self.groupkey(it)
		if k is None or self.expanded is None:
			return
		(self.expanded.add if open else self.expanded.discard)(k)
		self.updateallbtn()

	def fill(self, data):
		"""the weeks and days of data in month groups"""
		self.data = data
		self.tree.blockSignals(True)
		self.tree.clear()
		self.rows = {}
		self.groups = {}
		bold = QFont(self.tree.font())
		bold.setBold(True)
		weeks, days = self.weeksbox.isChecked(), self.daysbox.isChecked()
		if data is None or not len(data):
			self.info.setText("No m15 data in this journal. Import a CSV exported from TradingView "
				"(time, open, high, low, close), or a zip with it.")
		else:
			allweeks = data.weeks()
			self.info.setText(f"<b>{data.symbol}</b> m15, {data.first():%d %b %Y} – {data.last():%d %b %Y}, "
				f"{len(allweeks)} weeks, {len(data.days())} days")
			def month(d):
				mk = ("m", d.year, d.month)
				m = self.groups.get(mk)
				if m is None:
					m = QTreeWidgetItem([f"{d:%B %Y}"])
					m.setFont(0, bold)
					m.setData(0, GROUPROLE, mk)
					m.setFlags(m.flags() & ~Qt.ItemFlag.ItemIsSelectable)
					self.tree.addTopLevelItem(m)
					self.groups[mk] = m
				return m
			for w in allweeks:
				parent = None
				if weeks:	# a week goes in the month of its Monday
					wi = QTreeWidgetItem([""])
					wi.setFont(0, bold)
					wi.setData(0, KEYROLE, ("w", w))
					month(w).addChild(wi)
					self.rows[("w", w)] = wi
					if days:
						wi.setData(0, GROUPROLE, ("w", w))
						self.groups[("w", w)] = wi
						parent = wi
				if days:
					for d in data.daysof(w):
						di = QTreeWidgetItem([""])
						di.setData(0, KEYROLE, ("d", d))
						(parent or month(d)).addChild(di)
						self.rows[("d", d)] = di
			if self.expanded is None:	# the last month and its last week open
				self.expanded = set()
				self.lastopen("m")
			for k, g in self.groups.items():
				g.setExpanded(k in self.expanded)
		self.tree.blockSignals(False)
		self.mark()
		self.updateallbtn()

	def lastopen(self, level):
		"""open the last month, and its last week"""
		if not self.data or not len(self.data):
			return
		w = self.data.weeks()[-1]
		last = self.data.days()[-1]
		self.expanded.add(("m", w.year, w.month))
		self.expanded.add(("m", last.year, last.month))
		self.expanded.add(("w", w))

	def setopen(self, keys):
		self.expanded = set(keys)
		self.tree.blockSignals(True)
		for k, g in self.groups.items():
			g.setExpanded(k in self.expanded)
		self.tree.blockSignals(False)
		self.updateallbtn()
		cur = self.tree.currentItem()
		if cur is not None:
			self.tree.scrollToItem(cur)

	def collapseto(self, level):
		"""collapse to months ("m") or weeks ("w"), the last ones open"""
		keep = {k for k in self.groups if level == "w" and k[0] == "m"}
		self.expanded = keep
		self.lastopen(level)
		self.setopen(self.expanded)

	def allcollapsed(self):
		return not any(g.isExpanded() for g in self.groups.values())

	def toggleall(self):
		self.setopen(set(self.groups) if self.allcollapsed() else set())

	def updateallbtn(self):
		self.allbtn.setText("+" if self.allcollapsed() else "−")
		self.allbtn.setToolTip("expand all the groups" if self.allcollapsed() else "collapse all the groups")

	def mark(self):
		"""the labels of the rows, with ✎ on those drawn on"""
		for (kind, d), it in self.rows.items():
			text = f"Week {d:%d %b %Y}" if kind == "w" else f"{d:%a %d}"
			if kind == "d" and not self.weeksbox.isChecked():
				text = f"{d:%a %d %b}"
			it.setText(0, text + ("  ✎" if self.data.drawn(kind, d) else ""))
		kind = "w" if self.weeksbox.isChecked() else "d"
		def count(it):
			k = it.data(0, KEYROLE)
			return (1 if k and k[0] == kind else 0) + sum(count(it.child(n)) for n in range(it.childCount()))
		for k, g in self.groups.items():
			if k[0] == "m":
				g.setText(0, f"{date(k[1], k[2], 1):%B %Y}   ({count(g)})")

	def keys(self):
		"""the rows in order, as the list shows them"""
		out = []
		def walk(it):
			k = it.data(0, KEYROLE)
			if k:
				out.append(k)
			for n in range(it.childCount()):
				walk(it.child(n))
		for n in range(self.tree.topLevelItemCount()):
			walk(self.tree.topLevelItem(n))
		return out

	def select(self, key):
		it = self.rows.get(key)
		self.tree.blockSignals(True)
		if it is None:
			self.tree.setCurrentItem(None)
		else:
			p = it.parent()
			while p is not None:
				p.setExpanded(True)
				k = self.groupkey(p)
				if k is not None and self.expanded is not None:
					self.expanded.add(k)
				p = p.parent()
			self.tree.setCurrentItem(it)
			self.tree.scrollToItem(it)
		self.tree.blockSignals(False)
		self.updateallbtn()

	def changed(self, it, _prev):
		key = it.data(0, KEYROLE) if it is not None else None
		if key:
			self.picked.emit(*key)
