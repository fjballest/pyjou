#
# the data view: the weeks and days of the m15 data (m15.py) in a list,
# each with its profile, and a chart of the one picked drawn from the
# candles, with its sessions and its profile, shown in the window's image
# view instead of a capture.
#
from datetime import timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import (
	QHBoxLayout, QLabel, QStyle, QStyledItemDelegate, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
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

def drawpts(painter, box, kind, pts, pal, selected=False, data=None, d=None):
	"""draw profile pts of kind in box: the midnights faint behind it, and
	the sessions of a day"""
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
	painter.setPen(QPen(pal.color(QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Highlight), 1.5))
	painter.drawPolyline(QPolygonF([QPointF(x(t), y(v)) for t, v in pts]))
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

class DataPanel(QWidget):
	"""the weeks of the data, each with its days, and their profiles"""
	picked = Signal(str, object)	# kind, date

	def __init__(self, win):
		super().__init__()
		self.win = win
		self.data = None
		self.rows = {}	# (kind, date) -> its row
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
		self.tree = QTreeWidget()
		self.tree.setHeaderHidden(True)
		self.tree.setIndentation(14)
		self.tree.setUniformRowHeights(True)
		self.tree.setItemDelegate(DataDelegate(self))
		self.tree.currentItemChanged.connect(self.changed)
		lay.addWidget(self.tree, 1)

	def fill(self, data):
		"""the weeks of data, last first collapsed but the one selected"""
		self.data = data
		self.tree.blockSignals(True)
		self.tree.clear()
		self.rows = {}
		bold = QFont(self.tree.font())
		bold.setBold(True)
		if data is None or not len(data):
			self.info.setText("No m15 data in this journal. Import a CSV exported from TradingView "
				"(time, open, high, low, close), or a zip with it.")
		else:
			weeks = data.weeks()
			self.info.setText(f"<b>{data.symbol}</b> m15, {data.first():%d %b %Y} – {data.last():%d %b %Y}, "
				f"{len(weeks)} weeks, {len(data.days())} days")
			for w in weeks:
				wi = QTreeWidgetItem([f"Week {w:%d %b %Y}"])
				wi.setFont(0, bold)
				wi.setData(0, KEYROLE, ("w", w))
				self.tree.addTopLevelItem(wi)
				self.rows[("w", w)] = wi
				for d in data.daysof(w):
					di = QTreeWidgetItem([f"{d:%a %d}"])
					di.setData(0, KEYROLE, ("d", d))
					wi.addChild(di)
					self.rows[("d", d)] = di
		self.tree.blockSignals(False)

	def keys(self):
		"""the rows in order: each week, then its days"""
		out = []
		for k in range(self.tree.topLevelItemCount()):
			w = self.tree.topLevelItem(k)
			out.append(w.data(0, KEYROLE))
			out += [w.child(n).data(0, KEYROLE) for n in range(w.childCount())]
		return out

	def select(self, key):
		it = self.rows.get(key)
		self.tree.blockSignals(True)
		if it is not None:
			if it.parent() is not None:
				it.parent().setExpanded(True)
			self.tree.setCurrentItem(it)
			self.tree.scrollToItem(it)
		self.tree.blockSignals(False)

	def changed(self, it, _prev):
		key = it.data(0, KEYROLE) if it is not None else None
		if key:
			self.picked.emit(*key)
