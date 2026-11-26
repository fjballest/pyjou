"""What a run drew (a pine.Result) painted on a chart of dataview.Geom."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainterPath, QPen, QPolygonF

import m15
from . import runtime as R

SIZES = {"tiny": 11, "small": 13, "normal": 15, "large": 20, "huge": 27, "auto": 13}
WIDTH = 1.3	# pixels of a Pine line width of 1
STYLES = {"solid": Qt.PenStyle.SolidLine, "dashed": Qt.PenStyle.DashLine, "dotted": Qt.PenStyle.DotLine}

def qcolor(c, default=None):
	if c is None or R.isna(c):
		return default
	r, g, b, t = c
	return QColor(int(r), int(g), int(b), max(0, min(255, int(round(255 * (1 - t / 100))))))

class Mapper:
	"""chart points of bar indexes and times of the run's bars"""
	def __init__(self, g, S, tf):
		self.g, self.S, self.tf = g, S, tf
		self.unit = 3600 if g.kind == "d" else 86400
		self.zero = g.bars[5]
		self.half = tf * 60 / self.unit / 2
		self.tfms = tf * 60000

	def ms(self, x, xloc):
		if x is None or R.isna(x):
			return None
		if xloc == "bt":
			return x
		S = self.S
		k = int(round(x))
		if 0 <= k < S.n:
			return S.t[k]
		if k >= S.n:
			return S.t[-1] + (k - S.n + 1) * self.tfms
		return S.t[0] + k * self.tfms

	def X(self, x, xloc):
		t = self.ms(x, xloc)
		if t is None:
			return None
		s = t / 1000
		wall = s + m15.nyoffset(s)
		return self.g.X((wall - self.zero) / self.unit + self.half)

	def Y(self, p):
		if p is None or R.isna(p):
			return None
		return self.g.Y(p)

def pen(c, w, style="solid"):
	q = QPen(c, max(1.0, (w or 1) * WIDTH))
	q.setStyle(STYLES.get(style, Qt.PenStyle.SolidLine))
	q.setCapStyle(Qt.PenCapStyle.FlatCap)
	return q

def font(size, formatting="none"):
	f = QFont()
	f.setPixelSize(SIZES.get(size, 13) if isinstance(size, str) else max(8, int(size)))
	if formatting and "bold" in str(formatting):
		f.setBold(True)
	if formatting and "italic" in str(formatting):
		f.setItalic(True)
	return f

def extended(x1, y1, x2, y2, ext, big):
	dx, dy = x2 - x1, y2 - y1
	if dx == 0 and dy == 0:
		return x1, y1, x2, y2
	n = math.hypot(dx, dy)
	ux, uy = dx / n * big, dy / n * big
	if ext in ("r", "b"):
		x2, y2 = x2 + ux, y2 + uy
	if ext in ("l", "b"):
		x1, y1 = x1 - ux, y1 - uy
	return x1, y1, x2, y2

def paint(p, g, res, tf):
	"""paint res on painter p over the chart of geometry g in tf minutes"""
	if res is None or res.S is None or not res.S.n:
		return
	m = Mapper(g, res.S, tf)
	plot = QRectF(g.L, g.T, g.pw, g.ph)
	p.save()
	p.setClipRect(plot)
	p.setRenderHint(p.RenderHint.Antialiasing)
	big = 4 * (g.W + g.H)
	slot = tf * 60 / m.unit / (g.t1 - g.t0) * g.pw
	bgcolors(p, g, m, res, slot)
	for b in res.boxes:
		box(p, g, m, b, big)
	for lf in res.linefills:
		linefill(p, m, lf, big)
	for ln in res.lines:
		line(p, m, ln, big)
	plots(p, g, m, res, slot)
	for lb in res.labels:
		label(p, g, m, res, lb)
	p.restore()
	for t in res.tables:
		table(p, g, t)

def line(p, m, ln, big):
	x1, x2 = m.X(ln.x1, ln.xloc), m.X(ln.x2, ln.xloc)
	y1, y2 = m.Y(ln.y1), m.Y(ln.y2)
	if None in (x1, x2, y1, y2):
		return
	c = qcolor(ln.color)
	if c is None or c.alpha() == 0:
		return
	x1, y1, x2, y2 = extended(x1, y1, x2, y2, ln.extend, big)
	p.setPen(pen(c, ln.width, ln.style))
	p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
	if ln.style in ("arrow_right", "arrow_both", "arrow_left"):
		for (ax, ay, bx, by), on in (((x1, y1, x2, y2), ln.style != "arrow_left"), ((x2, y2, x1, y1), ln.style != "arrow_right")):
			if not on:
				continue
			a = math.atan2(by - ay, bx - ax)
			for d in (2.6, -2.6):
				p.drawLine(QPointF(bx, by), QPointF(bx + 10 * math.cos(a + d), by + 10 * math.sin(a + d)))

def linefill(p, m, lf, big):
	pts = []
	for ln in (lf.l1, lf.l2):
		if not ln.alive:
			return
		x1, x2, y1, y2 = m.X(ln.x1, ln.xloc), m.X(ln.x2, ln.xloc), m.Y(ln.y1), m.Y(ln.y2)
		if None in (x1, x2, y1, y2):
			return
		pts.append(extended(x1, y1, x2, y2, ln.extend, big))
	c = qcolor(lf.color)
	if c is None:
		return
	a, b = pts
	poly = QPolygonF([QPointF(a[0], a[1]), QPointF(a[2], a[3]), QPointF(b[2], b[3]), QPointF(b[0], b[1])])
	p.setPen(Qt.PenStyle.NoPen)
	p.setBrush(c)
	p.drawPolygon(poly)
	p.setBrush(Qt.BrushStyle.NoBrush)

def aligned(halign, valign):
	h = {"left": Qt.AlignmentFlag.AlignLeft, "right": Qt.AlignmentFlag.AlignRight}.get(halign, Qt.AlignmentFlag.AlignHCenter)
	v = {"top": Qt.AlignmentFlag.AlignTop, "bottom": Qt.AlignmentFlag.AlignBottom}.get(valign, Qt.AlignmentFlag.AlignVCenter)
	return h | v

def box(p, g, m, b, big):
	x1, x2 = m.X(b.left, b.xloc), m.X(b.right, b.xloc)
	y1, y2 = m.Y(b.top), m.Y(b.bottom)
	if None in (x1, x2, y1, y2):
		return
	if b.extend in ("r", "b"):
		x2 = max(x1, x2) + big
	if b.extend in ("l", "b"):
		x1 = min(x1, x2) - big
	r = QRectF(QPointF(min(x1, x2), min(y1, y2)), QPointF(max(x1, x2), max(y1, y2)))
	fill = qcolor(b.bgcolor)
	edge = qcolor(b.border_color)
	if fill is not None and fill.alpha():
		p.fillRect(r, fill)
	if edge is not None and edge.alpha() and (b.border_width or 0) > 0:
		p.setPen(pen(edge, b.border_width, b.border_style))
		p.drawRect(r)
	if b.text:
		c = qcolor(b.text_color, QColor("black"))
		p.setPen(c)
		p.setFont(font(b.text_size if b.text_size != "auto" else "small", b.formatting))
		vis = r.intersected(QRectF(g.L, g.T, g.pw, g.ph))
		p.drawText(vis.adjusted(4, 2, -4, -2), int(aligned(b.text_halign, b.text_valign)), str(b.text))

def label(p, g, m, res, lb):
	x = m.X(lb.x, lb.xloc)
	if x is None:
		return
	y = None
	if lb.yloc == "abovebar" or lb.yloc == "belowbar":
		k = int(round(lb.x)) if lb.xloc == "bi" else res.S.find(lb.x)
		if 0 <= k < res.S.n:
			y = m.Y(res.S.h[k]) - 6 if lb.yloc == "abovebar" else m.Y(res.S.l[k]) + 6
	else:
		y = m.Y(lb.y)
	if y is None:
		return
	text = "" if R.isna(lb.text) else str(lb.text)
	f = font(lb.size, lb.formatting)
	p.setFont(f)
	fm = QFontMetricsF(f)
	lines = text.split("\n") if text else [""]
	w = max(fm.horizontalAdvance(s) for s in lines) + (10 if text else 0)
	h = fm.height() * len(lines) + (4 if text else 0)
	style = lb.style or "label_down"
	bg = qcolor(lb.color)
	plain = style in ("none", "text_outline") or bg is None or bg.alpha() == 0
	gap = 0 if plain else 6
	if style in ("label_down",):
		r = QRectF(x - w / 2, y - gap - h, w, h)
	elif style in ("label_up",):
		r = QRectF(x - w / 2, y + gap, w, h)
	elif style in ("label_left",):
		r = QRectF(x + gap, y - h / 2, w, h)
	elif style in ("label_right",):
		r = QRectF(x - gap - w, y - h / 2, w, h)
	elif style == "label_lower_left":
		r = QRectF(x + gap, y - gap - h, w, h)
	elif style == "label_lower_right":
		r = QRectF(x - gap - w, y - gap - h, w, h)
	elif style == "label_upper_left":
		r = QRectF(x + gap, y + gap, w, h)
	elif style == "label_upper_right":
		r = QRectF(x - gap - w, y + gap, w, h)
	else:
		r = QRectF(x - w / 2, y - h / 2, w, h)
	right = g.L + g.pw
	if r.right() > right and x >= m.X(res.S.n - 1, "bi"):	# past the last bar: kept in sight
		dx = r.right() - right + 2
		r.translate(-dx, 0)
		x -= dx
	if not plain and style.startswith("label_"):
		path = QPainterPath()
		path.addRoundedRect(r, 3, 3)
		tip = QPolygonF()
		if style == "label_down":
			tip = QPolygonF([QPointF(x - 5, r.bottom()), QPointF(x + 5, r.bottom()), QPointF(x, y)])
		elif style == "label_up":
			tip = QPolygonF([QPointF(x - 5, r.top()), QPointF(x + 5, r.top()), QPointF(x, y)])
		elif style == "label_left":
			tip = QPolygonF([QPointF(r.left(), y - 5), QPointF(r.left(), y + 5), QPointF(x, y)])
		elif style == "label_right":
			tip = QPolygonF([QPointF(r.right(), y - 5), QPointF(r.right(), y + 5), QPointF(x, y)])
		if not tip.isEmpty():
			path.addPolygon(tip)
		p.setPen(Qt.PenStyle.NoPen)
		p.setBrush(bg)
		p.drawPath(path.simplified())
		p.setBrush(Qt.BrushStyle.NoBrush)
	elif not plain:
		shape(p, style, QPointF(x, y), bg, lb.size)
	if text:
		p.setPen(qcolor(lb.textcolor, QColor("black")))
		al = {"left": Qt.AlignmentFlag.AlignLeft, "right": Qt.AlignmentFlag.AlignRight}.get(lb.textalign, Qt.AlignmentFlag.AlignHCenter)
		p.drawText(r.adjusted(5, 2, -5, -2), int(al | Qt.AlignmentFlag.AlignVCenter), text)

def shape(p, style, at, c, size="normal"):
	s = {"tiny": 4, "small": 6, "normal": 8, "large": 12, "huge": 16, "auto": 6}.get(size, 7)
	x, y = at.x(), at.y()
	p.setPen(QPen(c, 1.5))
	p.setBrush(c)
	if style in ("triangleup", "arrowup"):
		p.drawPolygon(QPolygonF([QPointF(x, y - s), QPointF(x - s, y + s * 0.7), QPointF(x + s, y + s * 0.7)]))
	elif style in ("triangledown", "arrowdown"):
		p.drawPolygon(QPolygonF([QPointF(x, y + s), QPointF(x - s, y - s * 0.7), QPointF(x + s, y - s * 0.7)]))
	elif style == "diamond":
		p.drawPolygon(QPolygonF([QPointF(x, y - s), QPointF(x + s, y), QPointF(x, y + s), QPointF(x - s, y)]))
	elif style == "circle":
		p.drawEllipse(at, s * 0.8, s * 0.8)
	elif style == "square":
		p.drawRect(QRectF(x - s * 0.7, y - s * 0.7, s * 1.4, s * 1.4))
	elif style in ("cross", "xcross"):
		p.setBrush(Qt.BrushStyle.NoBrush)
		if style == "cross":
			p.drawLine(QPointF(x - s, y), QPointF(x + s, y))
			p.drawLine(QPointF(x, y - s), QPointF(x, y + s))
		else:
			p.drawLine(QPointF(x - s, y - s), QPointF(x + s, y + s))
			p.drawLine(QPointF(x - s, y + s), QPointF(x + s, y - s))
	elif style == "flag":
		p.drawRect(QRectF(x, y - s, s * 1.2, s * 0.8))
		p.drawLine(QPointF(x, y - s), QPointF(x, y + s))
	else:
		p.drawEllipse(at, s * 0.6, s * 0.6)
	p.setBrush(Qt.BrushStyle.NoBrush)

def visible(g, m, S):
	"""the bar indexes of S on the chart"""
	lo = hi = None
	for k in range(S.n):
		x = m.X(k, "bi")
		if g.L - 20 <= x <= g.L + g.pw + 20:
			if lo is None:
				lo = k
			hi = k
	return (lo, hi) if lo is not None else (0, -1)

def bgcolors(p, g, m, res, slot):
	lo, hi = None, None
	for site, (kind, vals, title) in res.plots.items():
		if kind != "bgcolor":
			continue
		if lo is None:
			lo, hi = visible(g, m, res.S)
		for k in range(lo, hi + 1):
			v = vals.get(k)
			if v is None:
				continue
			c = qcolor(v[0])
			if c is None or not c.alpha():
				continue
			x = m.X(k, "bi")
			p.fillRect(QRectF(x - slot / 2, g.T, slot, g.ph), c)

def plots(p, g, m, res, slot):
	lo, hi = None, None
	S = res.S
	for site, (kind, vals, title) in res.plots.items():
		if kind not in ("plot", "shape", "char"):
			continue
		if lo is None:
			lo, hi = visible(g, m, S)
		if kind == "plot":
			path = []
			for k in range(lo, hi + 1):
				v = vals.get(k)
				if v is None or R.isna(v[0]):
					if len(path) > 1:
						p.drawPolyline(QPolygonF(path))
					path = []
					continue
				val, a, kw = v
				c = qcolor(kw.get("color", a[2] if len(a) > 2 else R.COLOR_BLUE), QColor("blue"))
				p.setPen(pen(c, kw.get("linewidth", 1)))
				path.append(QPointF(m.X(k, "bi"), m.Y(val)))
			if len(path) > 1:
				p.drawPolyline(QPolygonF(path))
			continue
		for k in range(lo, hi + 1):
			v = vals.get(k)
			if v is None:
				continue
			val, a, kw = v
			if val is False or R.isna(val):
				continue
			args = dict(zip(("series", "title", "style" if kind == "shape" else "char", "location", "color", "offset",
				"text", "textcolor"), a))
			args.update(kw)
			loc = args.get("location", "abovebar")
			x = m.X(k + int(args.get("offset", 0) or 0), "bi")
			if loc == "abovebar":
				y = m.Y(S.h[k]) - 12
			elif loc == "belowbar":
				y = m.Y(S.l[k]) + 12
			elif loc == "top":
				y = g.T + 10
			elif loc == "bottom":
				y = g.T + g.ph - 10
			else:
				y = m.Y(val if not isinstance(val, bool) else S.c[k])
			c = qcolor(args.get("color"), QColor(41, 98, 255))
			if kind == "shape":
				style = args.get("style", "xcross")
				style = {"labelup": "triangleup", "labeldown": "triangledown"}.get(style, style)
				shape(p, style, QPointF(x, y), c, args.get("size", "small"))
			else:
				p.setPen(c)
				p.setFont(font(args.get("size", "small")))
				p.drawText(QRectF(x - 20, y - 10, 40, 20), int(Qt.AlignmentFlag.AlignCenter), str(args.get("char", "★"))[:1])
			text = args.get("text")
			if text and not R.isna(text):
				p.setPen(qcolor(args.get("textcolor"), c))
				p.setFont(font("small"))
				dy = -26 if loc == "abovebar" else 14
				p.drawText(QRectF(x - 60, y + dy, 120, 14), int(Qt.AlignmentFlag.AlignCenter), str(text))

def table(p, g, t):
	if not t.cells:
		return
	cols = max(k[0] for k in t.cells) + 1
	rows = max(k[1] for k in t.cells) + 1
	widths = [0.0] * cols
	heights = [0.0] * rows
	for (c, r), cell in t.cells.items():
		f = font(cell["text_size"], cell.get("formatting"))
		fm = QFontMetricsF(f)
		lines = str(cell["text"] or "").split("\n")
		widths[c] = max(widths[c], max(fm.horizontalAdvance(s) for s in lines) + 10)
		heights[r] = max(heights[r], fm.height() * len(lines) + 4)
	W, H = sum(widths), sum(heights)
	pos = t.position or "top_right"
	vert, horiz = pos.split("_")
	x = {"left": g.L + 4, "center": g.L + (g.pw - W) / 2, "right": g.L + g.pw - W - 4}[horiz]
	y = {"top": g.T + 4, "middle": g.T + (g.ph - H) / 2, "bottom": g.T + g.ph - H - 4}[vert]
	bg = qcolor(t.bgcolor)
	if bg is not None and bg.alpha():
		p.fillRect(QRectF(x, y, W, H), bg)
	yy = y
	for r in range(rows):
		xx = x
		for c in range(cols):
			cell = t.cells.get((c, r))
			rect = QRectF(xx, yy, widths[c], heights[r])
			if cell:
				cb = qcolor(cell["bgcolor"])
				if cb is not None and cb.alpha():
					p.fillRect(rect, cb)
				if cell["text"]:
					p.setFont(font(cell["text_size"], cell.get("formatting")))
					p.setPen(qcolor(cell["text_color"], QColor("black")))
					p.drawText(rect.adjusted(5, 2, -5, -2), int(aligned(cell["text_halign"], cell["text_valign"])), str(cell["text"]))
			xx += widths[c]
		yy += heights[r]
	edge = qcolor(t.frame_color)
	if edge is not None and (t.frame_width or 0) > 0:
		p.setPen(QPen(edge, t.frame_width))
		p.drawRect(QRectF(x, y, W, H))
