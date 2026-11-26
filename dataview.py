#
# the data view: the weeks and days of the m15 data (m15.py) in a list,
# each with its profile, and a chart of the one picked drawn from the
# candles, with its sessions and its profile, shown in the window's image
# view instead of a capture.
#
import copy
import os
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import (
	QGraphicsPixmapItem, QStyleOptionGraphicsItem, QCheckBox, QComboBox, QHBoxLayout, QLabel, QStyle, QStyledItemDelegate, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
)

import numpy as np

import m15
from rail import withrail

EPOCH1 = date(1970, 1, 1).toordinal()

KEYROLE = Qt.ItemDataRole.UserRole + 10	# ("w" or "d", date) of a row

UP, DOWN = QColor("#089981"), QColor("#2a2e39")	# green up, black down, as the charts
PROFCOLOR = QColor("#26c6da")
NEWSCOLOR = QColor("#ff9800")	# the lines of the news releases
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

SHOWSESSIONS = True	# the session rectangles of the days are drawn (View ▸ Session Rectangles)
SHOWPROFILE = True	# the profile lines are drawn, with the drawings (View ▸ Profile Lines)
MAXMARGIN = 0.25	# of the times shown, at most, kept right of the last candle for what indicators draw there

def title(data, kind, d, tf=15):
	if tf in m15.PERIODS:
		end = d + timedelta(days=4) if kind == "w" else d
		return f"{data.symbol} {m15.tfname(tf)} · to {end:%a %d %b %Y}"
	if kind == "w":
		return f"{data.symbol} {m15.tfname(tf)} · Week {d:%d %b} – {d + timedelta(days=4):%d %b %Y}"
	return f"{data.symbol} {m15.tfname(tf)} · {d:%a %d %b %Y}"

def source(data, low, tf):
	"""the data a chart in tf is made from: the lower time frame low when tf is under m15"""
	return low if tf < 15 and low is not None and tf % low.tf == 0 else data

class Geom:
	"""where the chart of day or week d in time frame tf puts times and
	prices: the same size in every time frame (the lower ones are seen
	zooming in, on the image or its time axis)"""
	def __init__(self, data, kind, d, tf=15, low=None, view=None, margin=0):
		"""view, when given, is the (top, bottom, t0, t1) shown instead of
		the whole day or week (see zoomed); margin, in t, is room right of
		t1 for what indicators draw past the last candle: t1 moves right
		by it, and the candles, profile and sessions end at vt1"""
		self.kind, self.d, self.tf = kind, d, tf
		self.periods = tf in m15.PERIODS	# candles of days, weeks or months, up to d: t counts them
		if self.periods:
			st, o, h, l, c, en = data.periodbars(kind, d, tf)
			self.starts, self.ends = st, en	# UTC seconds
			self.bars = (np.arange(len(st), dtype=float), o, h, l, c, 0)
			self.unit, self.cw = 1, 1
		else:
			self.bars = source(data, low, tf).bars(kind, d, tf)
			self.unit = 3600 if kind == "d" else 86400
			self.cw = tf * 60 / self.unit	# a candle's width in t
		wall, o, h, l, c, zero = self.bars
		self.ok = len(wall) > 0
		self.W, self.H = (2000, 1000) if self.periods else (1800, 1000) if kind == "d" else (2400, 1100)
		self.L, self.R, self.T, self.B = 16, 100, 44, 40
		self.pw, self.ph = self.W - self.L - self.R, self.H - self.T - self.B
		self.t0, self.t1 = (-0.5, len(wall) + 2.5) if self.periods else trange(kind)
		hi, lo = (float(h.max()), float(l.min())) if self.ok else (1, 0)
		pad = (hi - lo) * 0.04 or 1
		self.top, self.bot = hi + pad, lo - pad
		self.whole = (self.top, self.bot, self.t0, self.t1)
		if view:
			self.top, self.bot, self.t0, self.t1 = view
		self.margin = 0
		self.vt1 = self.t1
		if margin > 0:
			self.margin = min(float(margin), MAXMARGIN * (self.t1 - self.t0))
			self.t1 = self.vt1 + self.margin

	def view(self):
		"""the prices and times shown: None for the whole day or week"""
		v = (self.top, self.bot, self.t0, self.vt1)
		return None if v == self.whole else v

	def mapped(self):
		"""whether its points aren't those of the whole day or week"""
		return self.view() is not None or self.margin > 0

	def when(self, x, y):
		"""the time (hours since day 1, New York clock) and price at point x, y"""
		t = self.t(x)
		if self.periods:
			s = self.utc(t)
			return EPOCH1 * 24 + (s + m15.nyoffset(s)) / 3600, self.price(y)
		return self.d.toordinal() * 24 + (t if self.kind == "d" else t * 24), self.price(y)

	def utc(self, t):
		"""the UTC time (s) at t of a chart of periods"""
		n = len(self.starts)
		k = int(min(max(t // 1, 0), n - 1))
		return int(self.starts[k] + (t - k) * (self.ends[k] - self.starts[k]))

	def tx(self, s):
		"""the t of UTC time s (seconds), where candles start at their time"""
		if not self.periods:
			return (s + m15.nyoffset(s) - self.bars[5]) / self.unit
		st, en = self.starts, self.ends
		n = len(st)
		if not n:
			return 0
		k = int(np.searchsorted(st, s, "right")) - 1
		if k < 0:
			return (s - st[0]) / max(1, en[0] - st[0])
		if k == n - 1 and s >= en[-1]:	# past the last: a period a candle
			return k + 1 + (s - en[-1]) / {m15.DAILY: 86400, m15.WEEKLY: 7 * 86400}.get(self.tf, 30.4 * 86400)
		return k + min(1.0, (s - st[k]) / max(1, en[k] - st[k]))

	def lastend(self):
		"""the UTC time (s) where the last candle shown ends, or None"""
		wall = self.bars[0]
		if not len(wall):
			return None
		t = (wall - self.bars[5]) / self.unit
		k = int(np.searchsorted(t, self.vt1, "left")) - 1	# the last starting before the right edge
		if k < 0:
			return None
		if self.periods:
			return int(self.ends[k])
		start = int(wall[k])
		return start - m15.nyoffset(start + 5 * 3600) + self.tf * 60

	def where(self, hours, price):
		"""the point of time hours (see when) and price, or None off the chart"""
		if self.periods:
			wall = (hours - EPOCH1 * 24) * 3600
			t = self.tx(wall - m15.nyoffset(wall + 5 * 3600))
			if not self.t0 <= t <= self.t1:
				return None
			return self.X(t), self.Y(price)
		t = hours - self.d.toordinal() * 24
		if self.kind == "w":
			t /= 24
		if not self.t0 <= t <= self.t1:
			return None
		return self.X(t), self.Y(price)

	def unzoomed(self):
		"""this geometry for the whole day or week"""
		g = copy.copy(self)
		g.top, g.bot, g.t0, g.t1 = self.whole
		g.vt1, g.margin = g.t1, 0
		return g

	def zoomed(self, axis, at, factor):
		"""the view with the prices (axis "p") or the times ("t") scaled by
		factor around at, a price or a time: under 1 shows less of them"""
		top, bot, t0, t1 = self.top, self.bot, self.t0, self.vt1
		if axis == "p":
			span = (top - bot) * factor
			if span < 1 or span > 20 * (self.whole[0] - self.whole[1]):
				return self.view()
			k = (top - at) / (top - bot)
			top = at + k * span
			bot = top - span
		else:
			span = (t1 - t0) * factor
			w0, w1 = self.whole[2], self.whole[3]
			least = 10 if self.periods else (0.5 if self.kind == "d" else 2 / 24)	# ten candles, half an hour, two hours
			span = max(least, min(span, w1 - w0))
			k = (at - t0) / (t1 - t0)
			t0 = at - k * span
			t0 = min(max(t0, w0), w1 - span)
			t1 = t0 + span
		v = (top, bot, t0, t1)
		return None if all(abs(a - b) < 1e-9 for a, b in zip(v, self.whole)) else v

	def zoomedat(self, at, price, factor):
		"""the view scaled by factor on both axes around time at and price"""
		v = self.zoomed("t", at, factor)
		g = copy.copy(self)
		g.top, g.bot, g.t0, g.vt1 = v or self.whole
		return g.zoomed("p", price, factor)

	def panned(self, dt, dp):
		"""the view moved dt in time and dp in price: the times stay in
		the day or week"""
		top, bot, t0, t1 = self.top + dp, self.bot + dp, self.t0 + dt, self.vt1 + dt
		w0, w1 = self.whole[2], self.whole[3]
		span = t1 - t0
		t0 = min(max(t0, w0), w1 - span)
		v = (top, bot, t0, t0 + span)
		return None if all(abs(a - b) < 1e-9 for a, b in zip(v, self.whole)) else v

	def inplot(self, x, y):
		"""where scene point x, y is: "p" over the price axis, "t" over the
		time axis, "c" in the chart, None elsewhere"""
		if self.T <= y <= self.T + self.ph and x > self.L + self.pw:
			return "p"
		if self.L <= x <= self.L + self.pw and y > self.T + self.ph:
			return "t"
		if self.L <= x <= self.L + self.pw and self.T <= y <= self.T + self.ph:
			return "c"
		return None

	def X(self, t):
		return self.L + (t - self.t0) / (self.t1 - self.t0) * self.pw

	def Y(self, p):
		return self.T + (self.top - p) / (self.top - self.bot) * self.ph

	def t(self, x):
		return self.t0 + (x - self.L) / self.pw * (self.t1 - self.t0)

	def price(self, y):
		return self.top - (y - self.T) / self.ph * (self.top - self.bot)

	def topx(self, pts):
		"""profile [(t, price)] as points [x, y] of the image"""
		return [[self.X(t), self.Y(p)] for t, p in pts]

	def frompx(self, px):
		return [(round(self.t(x), 4), round(self.price(y), 2)) for x, y in px]

def render(data, kind, d, path=None, tf=15, low=None, view=None, profile=True, news=None, overlay=None, margin=0):
	"""the chart of day d or week d (its Monday) in time frame tf (from
	low, the data of a lower time frame, under m15) as a QImage, saved at
	path when given; None without candles. view is the part shown (see
	Geom), profile whether its profile is drawn, news a news.News whose
	releases are marked, overlay a function painting more on it (painter,
	geometry), margin room right of the last candle (see Geom)"""
	g = Geom(data, kind, d, tf, low, view, margin)
	if not g.ok:
		return None
	img = QImage(g.W, g.H, QImage.Format.Format_RGB32)
	img.fill(QColor("white"))
	p = QPainter(img)
	paintchart(p, g, data, kind, d, tf, profile, news, overlay=overlay)
	p.end()
	if path:
		img.save(path)
	return img

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

def periodaxis(p, g, grid, axis):
	"""the time axis of a chart of days, weeks or months: their months, or years"""
	n = len(g.starts)
	if not n:
		return
	days = m15.daynos(g.starts + 7 * 3600)	# the trading day each starts
	dd = days.astype("datetime64[D]")
	months = dd.astype("datetime64[M]").astype(np.int64)
	px = g.pw / (g.t1 - g.t0)	# pixels a candle
	every = next((k for k in (1, 3, 6, 12, 24, 60) if 30 / (g.tf / 1440) * k * px >= 70 or k == 60), 12)
	if g.tf == m15.DAILY and 7 * px >= 70:	# weeks, when there is room
		marks = [(k, f"{dd[k].astype(object):%d}" if months[k] == months[k - 1] else MONTHS[months[k] % 12])
			for k in range(1, n) if (days[k] - 4) // 7 != (days[k - 1] - 4) // 7]
	else:
		marks = []
		for k in range(1, n):
			if months[k] != months[k - 1] and months[k] % every == 0:
				m = int(months[k])
				marks.append((k, str(1970 + m // 12) if m % 12 == 0 else MONTHS[m % 12]))
	for k, label in marks:
		x = g.X(k)
		if x < g.L + 20 or x > g.L + g.pw:
			continue
		year = label.isdigit()
		p.setPen(QPen(grid.darker(108) if year else grid, 1))
		p.drawLine(QPointF(x, g.T), QPointF(x, g.T + g.ph))
		p.setPen(axis)
		f = p.font()
		f.setBold(year)
		p.setFont(f)
		p.drawText(QRectF(x - 40, g.T + g.ph + 6, 80, 20), Qt.AlignmentFlag.AlignCenter, label)
	f = p.font()
	f.setBold(False)
	p.setFont(f)

def paintchart(p, g, data, kind, d, tf=15, profile=True, news=None, clip=None, overlay=None):
	"""paint the chart of geometry g with painter p, in its coordinates
	(the image's pixels); clip, a QRectF, leaves out the candles off it;
	overlay(p, g), when given, paints over the candles (the indicators)"""
	p.setRenderHint(QPainter.RenderHint.Antialiasing)
	wall, bo, bh, bl, bc, zero = g.bars
	W, H, L, R, T, B, pw, ph = g.W, g.H, g.L, g.R, g.T, g.B, g.pw, g.ph
	t0, t1, top, bot = g.t0, g.t1, g.top, g.bot
	X, Y = g.X, g.Y
	unit = g.unit
	slot = g.cw / (t1 - t0) * pw	# pixels per candle

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

	# time: the hours of a day, the days of a week, or their hours when zoomed in
	p.save()
	p.setClipRect(QRectF(L, T, pw, ph + B))
	hours = (t1 - t0) * (1 if kind == "d" else 24)	# hours shown
	step = next((h for h in (0.25, 0.5, 1, 2, 3, 4, 6, 12) if hours / h <= 14), 24)
	if g.periods:
		periodaxis(p, g, grid, axis)
	elif kind == "d" or hours <= 60:
		perh = 1 if kind == "d" else 1 / 24	# chart units an hour
		h = (t0 / perh // step) * step
		while h * perh <= t1:
			x = X(h * perh)
			if x >= L + 20:	# a label cut by the left edge isn't drawn
				p.setPen(QPen(grid, 1))
				p.drawLine(QPointF(x, T), QPointF(x, T + ph))
				p.setPen(axis)
				hh = h % 24
				label = f"{int(hh):02d}:{int(round(hh % 1 * 60)):02d}"
				if kind == "w" and hh == 0:
					label = f"{d + timedelta(days=int(h // 24)):%a %d}"
				p.drawText(QRectF(x - 40, T + ph + 6, 80, 20), Qt.AlignmentFlag.AlignCenter, label)
			h += step
	if g.periods:
		pass
	elif kind == "d":
		p.setPen(QPen(DAYLINE, 2, Qt.PenStyle.DotLine))
		p.drawLine(QPointF(X(0), T), QPointF(X(0), T + ph))
	else:
		p.setPen(QPen(DAYLINE, 2, Qt.PenStyle.DashLine))
		p.drawLine(QPointF(X(-0.25), T), QPointF(X(-0.25), T + ph))
		for k in range(5):
			p.setPen(QPen(DAYLINE, 2, Qt.PenStyle.DotLine))
			p.drawLine(QPointF(X(k), T), QPointF(X(k), T + ph))
			if hours > 60:	# the names of the days, in what shows of them
				a, b = max(X(k), L), min(X(k + 0.7), L + pw)
				if b - a > 30:
					p.setPen(axis)
					day = d + timedelta(days=k)
					p.drawText(QRectF(a, T + ph + 6, b - a, 20), Qt.AlignmentFlag.AlignCenter, f"{day:%a %d}")
	p.restore()

	p.save()
	p.setClipRect(QRectF(L, T, min(pw, X(g.vt1) - L), ph))	# levels of the m15 data may be off a lower time frame's; none in the margin
	# the sessions of a day, as boxes from their high to their low
	if kind == "d" and SHOWSESSIONS and not g.periods:
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
	xlo, xhi = (clip.left() - slot, clip.right() + slot) if clip is not None else (-1e9, 1e9)
	for x, o, h, l, c in zip(((wall - zero) / unit).tolist(), bo.tolist(), bh.tolist(), bl.tolist(), bc.tolist()):
		x = X(x) + slot / 2
		if not xlo <= x <= xhi:
			continue
		col = UP if c >= o else DOWN
		p.setPen(QPen(col, 1 if slot < 6 else 1.4))
		p.drawLine(QPointF(x, Y(h)), QPointF(x, Y(l)))
		y0, y1 = Y(max(o, c)), Y(min(o, c))
		p.fillRect(QRectF(x - bw / 2, y0, bw, max(1.0, y1 - y0)), col)

	# the news: a line at the time of each release
	if news is not None and not g.periods:
		f.setPixelSize(14)
		f.setBold(True)
		p.setFont(f)
		days = [(d, 0)] if kind == "d" else [(d + timedelta(days=k), k) for k in range(5)]
		for day, k in days:
			for n, (h, name) in enumerate(news.of(day)):
				x = X(h if kind == "d" else k + h / 24)
				p.setPen(QPen(NEWSCOLOR, 2, Qt.PenStyle.DashLine))
				p.drawLine(QPointF(x, T), QPointF(x, T + ph))
				p.setPen(NEWSCOLOR.darker(120))
				p.drawText(QRectF(x + 4, T + 2 + 18 * n, 120, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
		f.setBold(False)
		f.setPixelSize(15)
		p.setFont(f)

	# the profile
	pts = data.profile(kind, d, prices=True) if profile and not g.periods else None
	if pts:
		line = QPolygonF([QPointF(X(t), Y(v)) for t, v in pts])
		p.setPen(QPen(PROFCOLOR, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
		p.drawPolyline(line)
		p.setBrush(QColor("white"))
		p.setPen(QPen(PROFCOLOR.darker(130), 2))
		for q in list(line)[1:-1]:
			p.drawEllipse(q, 6, 6)
		p.setBrush(Qt.BrushStyle.NoBrush)

	p.restore()
	if overlay is not None:
		overlay(p, g)
	# the title
	f.setPixelSize(20)
	f.setBold(True)
	p.setFont(f)
	p.setPen(QColor(40, 40, 40))
	hol = ""
	if news is not None and hasattr(news, "holiday") and not g.periods:
		days = [d] if kind == "d" else [d + timedelta(days=k) for k in range(5)]
		hs = [(day, news.holiday(day)) for day in days if news.holiday(day)]
		hol = "   · " + ", ".join(h if kind == "d" else f"{day:%a} {h}" for day, h in hs) if hs else ""
	p.drawText(QRectF(L, 8, pw, 30), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title(data, kind, d, tf) + "   (New York time)" + hol)

class ChartItem(QGraphicsPixmapItem):
	"""the image of a data chart in the view, that paints the chart again,
	sharp, instead of its image when the view zooms in on it"""
	def __init__(self, pixmap, args):
		super().__init__(pixmap)
		self.args = args	# for paintchart: (geom, data, kind, d, tf, profile, news)
		self.overlay = None	# and its overlay
		self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

	def paint(self, painter, option, widget=None):
		lod = QStyleOptionGraphicsItem.levelOfDetailFromTransform(painter.worldTransform())
		if lod <= 1.05 or self.args is None:
			super().paint(painter, option, widget)
			return
		r = option.exposedRect
		painter.save()
		painter.setClipRect(r)
		painter.fillRect(r, QColor("white"))
		paintchart(painter, *self.args, clip=r, overlay=self.overlay)
		painter.restore()

def oldwidth(kind, tf):
	"""the width of the charts of the lower time frames before they were all
	the same size: what is drawn on them is moved from it (see widened)"""
	W, L, R = (1800 if kind == "d" else 2400), 16, 100
	n = (m15.DAYEND - m15.DAYSTART) * 60 / tf * (1 if kind == "d" else 5)
	return int(min(9000, max(W, L + R + n * (4 if kind == "d" else 2))))

def widened(data, g, tf):
	"""a drawing saved on a chart of time frame tf that was wider (see
	oldwidth), moved to the chart of g; as it is when it says its width"""
	if not data or not data.get("shapes") or "width" in data:
		return data
	W = oldwidth(g.kind, tf)
	if W == g.W:
		return data
	old = copy.copy(g)
	old.W, old.pw = W, W - g.L - g.R
	return mapdrawing(data, old, g)

def mapdrawing(data, g1, g2):
	"""drawing data (see viewer.drawingdata) on the chart of geometry g1
	moved to the same prices and times on that of g2"""
	if not data or not data.get("shapes"):
		return data
	def mp(q):
		return [round(g2.X(g1.t(q[0])), 1), round(g2.Y(g1.price(q[1])), 1)]
	shapes = []
	for sh in data["shapes"]:
		sh = dict(sh)
		for k in ("p1", "p2", "pos"):
			if k in sh:
				sh[k] = mp(sh[k])
		if "points" in sh:
			sh["points"] = [mp(q) for q in sh["points"]]
		if "rect" in sh:
			x, y, w, h = sh["rect"]
			a, b = mp((x, y)), mp((x + w, y + h))
			sh["rect"] = [min(a[0], b[0]), min(a[1], b[1]), round(abs(b[0] - a[0]), 1), round(abs(b[1] - a[1]), 1)]
		if "right" in sh:
			sh["right"] = round(g2.X(g1.t(sh["right"])), 1)
		shapes.append(sh)
	return {**data, "shapes": shapes}

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
		self.match = None	# fn(kind, date) of the rows the search shows; None: all
		lay = QVBoxLayout(self)
		lay.setContentsMargins(0, 0, 0, 0)
		self.info = QLabel()
		self.info.setWordWrap(True)
		lay.addWidget(self.info)
		top = QHBoxLayout()
		self.importbtn = QToolButton()
		self.importbtn.setText("Import…")
		self.importbtn.setAutoRaise(True)
		top.addWidget(self.importbtn)
		self.tfbox = QComboBox()
		self.tfbox.setToolTip("the time frame of the charts; a lower one than m15 takes data of it "
			"(File ▸ Import Data… with an m1 CSV)")
		top.addWidget(self.tfbox)
		self.capbtn = QToolButton()
		self.capbtn.setText("Capture")
		self.capbtn.setAutoRaise(True)
		self.capbtn.setToolTip("add this chart, in its time frame and with its drawings, to the captures (⇧⌘K)")
		top.addWidget(self.capbtn)
		self.backbtn = QToolButton()
		self.backbtn.setText("Captures")
		self.backbtn.setAutoRaise(True)
		self.backbtn.setToolTip("back to the captures, on this day or week")
		top.addStretch()
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
		lay.addWidget(withrail(self.tree), 1)
		self.updateallbtn()

	def settfs(self, tfs, tf):
		"""the time frames in the box (None keeps them), tf the one picked"""
		self.tfbox.blockSignals(True)
		if tfs is not None:
			self.tfbox.clear()
			for t in tfs:
				self.tfbox.addItem(m15.tfname(t), t)
		i = self.tfbox.findData(tf)
		if i >= 0:
			self.tfbox.setCurrentIndex(i)
		self.tfbox.blockSignals(False)

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
			ok = lambda kind, d: self.match is None or self.match(kind, d)
			found = set()	# the groups with something found, opened
			for w in allweeks:
				parent = None
				wdays = [d for d in data.daysof(w) if ok("d", d)] if days else []
				if self.match is not None:
					if not (weeks and ok("w", w)) and not wdays:
						continue
					found.update({("m", w.year, w.month), ("w", w)} | {("m", d.year, d.month) for d in wdays})
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
					for d in wdays:
						di = QTreeWidgetItem([""])
						di.setData(0, KEYROLE, ("d", d))
						(parent or month(d)).addChild(di)
						self.rows[("d", d)] = di
			if self.expanded is None:	# the last month and its last week open
				self.expanded = set()
				self.lastopen("m")
			self.expanded |= found
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
		"""the labels of the rows, with their news, ✎ on those drawn on and
		¶ on those with notes"""
		for (kind, d), it in self.rows.items():
			text = f"Week {d:%d %b %Y}" if kind == "w" else f"{d:%a %d}"
			if kind == "d" and not self.weeksbox.isChecked():
				text = f"{d:%a %d %b}"
			news = self.newsof(kind, d)
			notes = os.path.exists(self.data.notespath(kind, d))
			it.setText(0, text + (f"  · {news}" if news else "") + ("  ✎" if self.data.drawn(kind, d) else "") + ("  ¶" if notes else ""))
		kind = "w" if self.weeksbox.isChecked() else "d"
		def count(it):
			k = it.data(0, KEYROLE)
			return (1 if k and k[0] == kind else 0) + sum(count(it.child(n)) for n in range(it.childCount()))
		for k, g in self.groups.items():
			if k[0] == "m":
				g.setText(0, f"{date(k[1], k[2], 1):%B %Y}   ({count(g)})")

	def newsof(self, kind, d):
		"""the names of the news of day d, or of the week of d, and their holidays abbreviated"""
		n = getattr(getattr(self.win, "journal", None), "news", None)
		if n is None:
			return ""
		return n.marks(d, kind == "w")

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
