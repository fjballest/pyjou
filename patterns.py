#
# when swings and retracements start, from the history of the data: the
# times of the trading day, the hours of the week and the days of the month
# with the probability that a significant swing, or a retracement inside
# one, started then.
#
# A swing is a leg of a zigzag of the candles whose reversals are at least
# a fraction of the average range (of the 20 days before, for the days; of
# the 8 weeks before, for the weeks; of the 6 months before, for the
# months). Each turn of the zigzag is where a swing starts. A retracement
# starts at a turn of a finer zigzag that goes against the swing it is in
# (a pullback that is not the swing's end).
#
import numpy as np
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QTabWidget,
	QToolTip, QVBoxLayout, QWidget)

import m15

SWING = "#257de0"	# the categorical palette's first two slots
RETR = "#f47230"
DAYSTART = m15.DAYSTART	# 18:00 New York

def zigzag(h, l, thr):
	"""the turns of the zigzag of candles h, l whose reversals are at
	least thr (an array, one a candle): [(index, +1 a high / -1 a low)]"""
	n = len(h)
	out = []
	if n == 0:
		return out
	d = 0	# 0 not known yet, 1 going up (looking for a high), -1 going down
	hi, hix, lo, lox = h[0], 0, l[0], 0
	for i in range(1, n):
		t = thr[i]
		if d >= 0 and h[i] > hi:
			hi, hix = h[i], i
		if d <= 0 and l[i] < lo:
			lo, lox = l[i], i
		if d == 0:
			if hi - l[i] >= t and hix < i:
				out.append((hix, 1))
				d, lo, lox = -1, l[i], i
			elif h[i] - lo >= t and lox < i:
				out.append((lox, -1))
				d, hi, hix = 1, h[i], i
		elif d == 1:
			if hi - l[i] >= t:
				out.append((hix, 1))
				d, lo, lox = -1, l[i], i
		else:
			if h[i] - lo >= t:
				out.append((lox, -1))
				d, hi, hix = 1, h[i], i
	return out

def retracements(big, small):
	"""the turns of small that start a pullback inside a leg of big: a high
	in a leg going up (or a low in one going down) that is not its end"""
	if len(big) < 2:
		return []
	ends = [i for i, _ in big]
	out = []
	k = 0
	for i, s in small:
		while k + 1 < len(big) and ends[k + 1] <= i:
			k += 1
		if k + 1 >= len(big) or i <= ends[k]:
			continue
		up = big[k][1] < 0	# the leg starts at a low: it goes up, to a high
		if (up and s > 0) or (not up and s < 0):
			out.append((i, s))
	return out

def dailyranges(data):
	"""{trading day number: high - low} of the days of data"""
	dn = data.dayno
	starts = np.flatnonzero(np.r_[True, dn[1:] != dn[:-1]])
	hi = np.maximum.reduceat(data.h, starts)
	lo = np.minimum.reduceat(data.l, starts)
	return dn[starts], hi - lo

def avgbefore(keys, ranges, n):
	"""the mean of the n ranges before each one (the first ones: of those there are)"""
	c = np.r_[0, np.cumsum(ranges)]
	k = np.arange(len(ranges))
	a = np.maximum(0, k - n)
	cnt = k - a
	out = np.where(cnt > 0, (c[k] - c[a]) / np.maximum(cnt, 1), ranges)
	return out

class Result:
	"""the probability of a start in each slot: swing[k], retr[k] (0..1),
	how many periods were looked at (n), the names of the slots, and the
	mean size of the swings started in each (in points)"""
	def __init__(self, kind, names, swing, retr, n, size, rows=1):
		self.kind, self.names, self.swing, self.retr, self.n, self.size, self.rows = kind, names, swing, retr, n, size, rows

	def top(self, k=5, which="swing"):
		"""the k slots most likely to start one: [(name, probability)]"""
		p = self.swing if which == "swing" else self.retr
		order = np.argsort(-p, kind="stable")[:k]
		return [(self.names[i], float(p[i])) for i in order if p[i] > 0]

def select(data, first=None, last=None):
	"""the indexes [i, j) of the candles of the trading days first to last"""
	lo = data.dayn(first) if first else -10 ** 9
	hi = data.dayn(last) + 1 if last else 10 ** 9
	i, j = np.searchsorted(data.dayno, [lo, hi])
	return int(i), int(j)

def legsize(h, l, turns):
	"""the size of the leg each turn starts (to the next turn), or nan for the last"""
	out = []
	for k, (i, s) in enumerate(turns):
		if k + 1 < len(turns):
			j = turns[k + 1][0]
			out.append(abs((h[i] if s > 0 else l[i]) - (h[j] if s < 0 else l[j])))
		else:
			out.append(np.nan)
	return out

def byday(data, swing=0.3, retr=0.12, slot=30, first=None, last=None):
	"""the times of the trading day (18:00 to 17:00 New York, slots of slot
	minutes) where swings of swing x the average daily range, and
	retracements of retr x it, started"""
	keys, ranges = dailyranges(data)
	adr = dict(zip(keys.tolist(), avgbefore(keys, ranges, 20).tolist()))
	i0, j0 = select(data, first, last)
	if j0 - i0 < 3:
		return None
	h, l, dn = data.h[i0:j0], data.l[i0:j0], data.dayno[i0:j0]
	a = np.array([adr[int(x)] for x in dn])
	big = zigzag(h, l, swing * a)
	small = zigzag(h, l, retr * a)
	rets = retracements(big, small)
	tod = ((data.wall[i0:j0] - DAYSTART * 3600) % 86400) // 60	# minutes since 18:00
	nslots = 24 * 60 // slot
	days = sorted({int(x) for x in dn if m15.Data.daydate(int(x)).weekday() < 5})
	n = len(days)
	sw, rt = np.zeros(nslots), np.zeros(nslots)
	size, cnt = np.zeros(nslots), np.zeros(nslots)
	seen = set()
	for (i, s), z in zip(big, legsize(h, l, big)):
		k = int(tod[i] // slot)
		if (int(dn[i]), k) not in seen:
			seen.add((int(dn[i]), k))
			sw[k] += 1
		if not np.isnan(z):
			size[k] += z
			cnt[k] += 1
	seen = set()
	for i, s in rets:
		k = int(tod[i] // slot)
		if (int(dn[i]), k) not in seen:
			seen.add((int(dn[i]), k))
			rt[k] += 1
	names = []
	for k in range(nslots):
		m = (DAYSTART * 60 + k * slot) % 1440
		names.append(f"{m // 60:02d}:{m % 60:02d}")
	keep = nslots - 60 // slot	# 17:00 to 18:00: no trading
	return Result("day", names[:keep], sw[:keep] / max(n, 1), rt[:keep] / max(n, 1), n,
		(size / np.maximum(cnt, 1))[:keep])

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

def byweek(data, swing=0.3, retr=0.12, first=None, last=None):
	"""the hours of the week (its trading days, Sunday 18:00 to Friday
	17:00, by hour) where swings of swing x the average weekly range, and
	retracements of retr x it, started"""
	dn = data.dayno
	wk = (dn - 4) // 7	# weeks from Monday (day 4 since 1970 was a Monday)
	starts = np.flatnonzero(np.r_[True, wk[1:] != wk[:-1]])
	wr = np.maximum.reduceat(data.h, starts) - np.minimum.reduceat(data.l, starts)
	awr = dict(zip(wk[starts].tolist(), avgbefore(wk[starts], wr, 8).tolist()))
	i0, j0 = select(data, first, last)
	if j0 - i0 < 3:
		return None
	h, l = data.h[i0:j0], data.l[i0:j0]
	w = wk[i0:j0]
	a = np.array([awr[int(x)] for x in w])
	big = zigzag(h, l, swing * a)
	small = zigzag(h, l, retr * a)
	rets = retracements(big, small)
	wd = (dn[i0:j0] - 4) % 7	# 0 Monday
	hour = ((data.wall[i0:j0] - DAYSTART * 3600) % 86400) // 3600	# hours since 18:00
	n = len(set(w.tolist()))
	sw, rt = np.zeros((5, 23)), np.zeros((5, 23))
	size, cnt = np.zeros((5, 23)), np.zeros((5, 23))
	for turns, arr, sized in ((big, sw, True), (rets, rt, False)):
		seen = set()
		zs = legsize(h, l, turns) if sized else [np.nan] * len(turns)
		for (i, s), z in zip(turns, zs):
			if wd[i] > 4 or hour[i] > 22:
				continue
			key = (int(w[i]), int(wd[i]), int(hour[i]))
			if key not in seen:
				seen.add(key)
				arr[wd[i], hour[i]] += 1
			if sized and not np.isnan(z):
				size[wd[i], hour[i]] += z
				cnt[wd[i], hour[i]] += 1
	names = [f"{WEEKDAYS[d]} {(DAYSTART + k) % 24:02d}:00" for d in range(5) for k in range(23)]
	return Result("week", names, (sw / max(n, 1)).ravel(), (rt / max(n, 1)).ravel(), n,
		(size / np.maximum(cnt, 1)).ravel(), rows=5)

def bymonth(data, swing=0.3, retr=0.12, first=None, last=None):
	"""the trading days of the month (1st, 2nd...) where swings of swing x
	the average monthly range, and retracements of retr x it, started, from
	the daily candles"""
	keys, _ = dailyranges(data)
	dn = data.dayno
	starts = np.flatnonzero(np.r_[True, dn[1:] != dn[:-1]])
	dh = np.maximum.reduceat(data.h, starts)
	dl = np.minimum.reduceat(data.l, starts)
	days = dn[starts]
	wdays = np.array([m15.Data.daydate(int(x)).weekday() < 5 for x in days])
	days, dh, dl = days[wdays], dh[wdays], dl[wdays]
	if len(days) < 3:
		return None
	mon = days.astype("datetime64[D]").astype("datetime64[M]").astype(np.int64)
	ms = np.flatnonzero(np.r_[True, mon[1:] != mon[:-1]])
	mr = np.maximum.reduceat(dh, ms) - np.minimum.reduceat(dl, ms)
	amr = dict(zip(mon[ms].tolist(), avgbefore(mon[ms], mr, 6).tolist()))
	lo = data.dayn(first) if first else -10 ** 9
	hi = data.dayn(last) if last else 10 ** 9
	sel = (days >= lo) & (days <= hi)
	days, dh, dl, mon = days[sel], dh[sel], dl[sel], mon[sel]
	if len(days) < 3:
		return None
	a = np.array([amr[int(x)] for x in mon])
	big = zigzag(dh, dl, swing * a)
	small = zigzag(dh, dl, retr * a)
	rets = retracements(big, small)
	ms = np.flatnonzero(np.r_[True, mon[1:] != mon[:-1]])
	nth = np.arange(len(days)) - np.repeat(ms, np.diff(np.r_[ms, len(days)]))	# 0 the first trading day of its month
	n = len(ms)
	slots = 23
	sw, rt = np.zeros(slots), np.zeros(slots)
	size, cnt = np.zeros(slots), np.zeros(slots)
	for i, s in big:
		sw[min(nth[i], slots - 1)] += 1
	for (i, s), z in zip(big, legsize(dh, dl, big)):
		if not np.isnan(z):
			size[min(nth[i], slots - 1)] += z
			cnt[min(nth[i], slots - 1)] += 1
	for i, s in rets:
		rt[min(nth[i], slots - 1)] += 1
	names = [f"day {k + 1}" for k in range(slots)]
	return Result("month", names, sw / max(n, 1), rt / max(n, 1), n, size / np.maximum(cnt, 1))

def windows(res, which="swing", least=None, merge=True):
	"""the slots of a day result as macro windows: runs of slots whose
	probability is at least least (the 75th percentile when None), as
	[("HHMM-HHMM", probability)] best first"""
	p = res.swing if which == "swing" else res.retr
	if least is None:
		least = float(np.percentile(p, 75))
	slot = None
	if len(res.names) > 1:
		a, b = (int(x[:2]) * 60 + int(x[3:]) for x in res.names[:2])
		slot = (b - a) % 1440
	out = []
	k = 0
	while k < len(p):
		if p[k] >= least and p[k] > 0:
			j = k
			while merge and j + 1 < len(p) and p[j + 1] >= least:
				j += 1
			a = res.names[k].replace(":", "")
			m = (int(res.names[j][:2]) * 60 + int(res.names[j][3:]) + slot) % 1440
			out.append((f"{a}-{m // 60:02d}{m % 60:02d}", float(p[k:j + 1].max())))
			k = j + 1
		else:
			k += 1
	return sorted(out, key=lambda x: -x[1])

# ---------------------------------------------------------------- the window

class Chart(QWidget):
	"""bars of the probabilities of a Result (day and month), or a grid of
	them (week): swings and retracements"""
	def __init__(self, parent=None):
		super().__init__(parent)
		self.res = None
		self.setMouseTracking(True)
		self.setMinimumSize(640, 300)
		self.boxes = []	# [(QRectF, text)] for the tooltips

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
		faint.setAlpha(110)
		grid = QColor(text)
		grid.setAlpha(30)
		self.boxes = []
		r = self.res
		f = QFont(self.font())
		f.setPointSizeF(max(8.0, f.pointSizeF() - 1))
		p.setFont(f)
		if r is None:
			p.setPen(faint)
			p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Not enough data")
			return
		if r.rows > 1:
			self.paintgrid(p, r, text, faint, grid)
		else:
			self.paintbars(p, r, text, faint, grid)

	def legend(self, p, x, y, text):
		for name, c in (("swing starts", SWING), ("retracement starts", RETR)):
			p.fillRect(QRectF(x, y - 9, 10, 10), QColor(c))
			p.setPen(text)
			p.drawText(QPointF(x + 14, y), name)
			x += 14 + QFontMetricsF(p.font()).horizontalAdvance(name) + 18

	def paintbars(self, p, r, text, faint, grid):
		W, H = self.width(), self.height()
		L, R, T, B = 44, 12, 28, 46
		pw, ph = W - L - R, H - T - B
		top = max(0.05, float(max(r.swing.max(), r.retr.max())))
		step = next(s for s in (0.05, 0.1, 0.2, 0.25, 0.5) if top / s <= 6)
		top = np.ceil(top / step) * step
		self.legend(p, L, 16, text)
		v = 0.0
		while v <= top + 1e-9:
			y = T + ph - v / top * ph
			p.setPen(QPen(grid, 1))
			p.drawLine(QPointF(L, y), QPointF(L + pw, y))
			p.setPen(faint)
			p.drawText(QRectF(0, y - 8, L - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{v:.0%}")
			v += step
		n = len(r.names)
		cw = pw / n
		bw = max(1.5, min(14.0, (cw - 3) / 2))
		every = max(1, int(np.ceil(48 / cw)))
		for k in range(n):
			x = L + k * cw + cw / 2
			for val, c, dx in ((r.swing[k], SWING, -bw / 2 - 0.5), (r.retr[k], RETR, bw / 2 + 0.5)):
				h = val / top * ph
				if h > 0:
					p.fillRect(QRectF(x + dx - bw / 2, T + ph - h, bw, h), QColor(c))
			box = QRectF(L + k * cw, T, cw, ph)
			tip = (f"{r.names[k]}\nswing starts: {r.swing[k]:.0%} of the {self.unit(r)}\n"
				f"retracement starts: {r.retr[k]:.0%}" + (f"\nmean swing: {r.size[k]:.0f} points" if r.size[k] > 0 else ""))
			self.boxes.append((box, tip))
			if k % every == 0:
				p.setPen(faint)
				p.drawText(QRectF(x - 30, T + ph + 4, 60, 16), Qt.AlignmentFlag.AlignCenter,
					r.names[k].replace("day ", ""))
		p.setPen(QPen(faint, 1))
		p.drawLine(QPointF(L, T + ph), QPointF(L + pw, T + ph))
		p.setPen(faint)
		p.drawText(QRectF(L, H - 20, pw, 16), Qt.AlignmentFlag.AlignCenter,
			"New York time, the trading day from 18:00" if r.kind == "day" else "trading day of the month")

	def paintgrid(self, p, r, text, faint, grid):
		W, H = self.width(), self.height()
		L, R, T = 44, 12, 28
		cols = len(r.names) // r.rows
		cw = (W - L - R) / cols
		gap = 18
		rh = max(10.0, (H - T - 24 - gap - 2 * 18) / (2 * r.rows))
		self.legend(p, L, 16, text)
		for g, (vals, c, title) in enumerate(((r.swing, SWING, "swing starts"), (r.retr, RETR, "retracement starts"))):
			y0 = T + 18 + g * (r.rows * rh + gap + 18)
			p.setPen(faint)
			p.drawText(QPointF(L, y0 - 4), title)
			top = max(1e-9, float(vals.max()))
			base = QColor(c)
			for d in range(r.rows):
				p.drawText(QRectF(0, y0 + d * rh, L - 6, rh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, WEEKDAYS[d])
				for k in range(cols):
					i = d * cols + k
					a = vals[i] / top
					col = QColor(base)
					col.setAlphaF(0.06 + 0.94 * a)
					box = QRectF(L + k * cw + 1, y0 + d * rh + 1, cw - 2, rh - 2)
					p.fillRect(box, col)
					self.boxes.append((box, f"{r.names[i]}\nswing starts: {r.swing[i]:.0%} of the weeks\n"
						f"retracement starts: {r.retr[i]:.0%}" + (f"\nmean swing: {r.size[i]:.0f} points" if r.size[i] > 0 else "")))
				p.setPen(faint)
			for k in range(0, cols, 2):
				p.drawText(QRectF(L + k * cw - 20, y0 + r.rows * rh + 1, 40 + cw, 14), Qt.AlignmentFlag.AlignLeft,
					f"{(DAYSTART + k) % 24:02d}")

	@staticmethod
	def unit(r):
		return {"day": "days", "week": "weeks", "month": "months"}[r.kind]

	def mouseMoveEvent(self, ev):
		at = ev.position()
		for box, tip in self.boxes:
			if box.contains(at):
				QToolTip.showText(ev.globalPosition().toPoint(), tip, self)
				return
		QToolTip.hideText()

RANGES = [("All the data", None), ("Last 3 months", 91), ("Last 6 months", 182), ("Last year", 365), ("Last 2 years", 730)]

class PatternsWindow(QDialog):
	"""View ▸ Swing Times: the times of the day, the hours of the week and
	the days of the month swings and retracements started, from the data"""
	def __init__(self, data, parent=None):
		super().__init__(parent)
		self.data = data
		self.setWindowTitle(f"Swing Times · {data.symbol or ''}")
		self.resize(1100, 560)
		lay = QVBoxLayout(self)
		row = QHBoxLayout()
		self.range = QComboBox()
		for name, _ in RANGES:
			self.range.addItem(name)
		self.swing = QDoubleSpinBox()
		self.swing.setRange(0.05, 3)
		self.swing.setSingleStep(0.05)
		self.swing.setValue(0.3)
		self.swing.setToolTip("a swing reverses at least this times the average range (of the 20 days, 8 weeks "
			"or 6 months before)")
		self.retr = QDoubleSpinBox()
		self.retr.setRange(0.02, 2)
		self.retr.setSingleStep(0.02)
		self.retr.setValue(0.12)
		self.retr.setToolTip("a retracement goes back at least this times the average range, against its swing")
		self.slot = QComboBox()
		for m in (15, 30, 60):
			self.slot.addItem(f"{m} min", m)
		self.slot.setCurrentIndex(1)
		for w, name in ((self.range, None), (self.swing, "Swing ≥"), (self.retr, "Retracement ≥"), (self.slot, "Slots")):
			if name:
				row.addWidget(QLabel(name))
			row.addWidget(w)
			if name in ("Swing ≥", "Retracement ≥"):
				row.addWidget(QLabel("× range"))
		row.addStretch(1)
		lay.addLayout(row)
		self.tabs = QTabWidget()
		self.charts = {}
		for kind, title in (("day", "Day"), ("week", "Week"), ("month", "Month")):
			c = Chart()
			self.charts[kind] = c
			self.tabs.addTab(c, title)
		lay.addWidget(self.tabs, 1)
		self.summary = QLabel()
		self.summary.setWordWrap(True)
		self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
		lay.addWidget(self.summary)
		bottom = QHBoxLayout()
		self.macrosbtn = QPushButton("Macro Times…")
		self.macrosbtn.setToolTip("the times of the day most likely to start a swing, as macro windows, "
			"to update an indicator's macro times")
		bottom.addWidget(self.macrosbtn)
		self.macrosbtn.clicked.connect(self.macros)
		bottom.addStretch(1)
		close = QPushButton("Close")
		close.clicked.connect(self.close)
		bottom.addWidget(close)
		lay.addLayout(bottom)
		self.results = {}
		self.timer = QTimer(self)
		self.timer.setSingleShot(True)
		self.timer.timeout.connect(self.compute)
		for w in (self.range, self.slot):
			w.currentIndexChanged.connect(lambda _=0: self.timer.start(150))
		for w in (self.swing, self.retr):
			w.valueChanged.connect(lambda _=0: self.timer.start(300))
		self.tabs.currentChanged.connect(lambda _=0: self.showsummary())
		self.compute()

	def macros(self):
		"""the macro times dialog, on the day's result"""
		r = self.results.get("day")
		if r is None:
			return
		import indicators
		have = []
		for name, path in indicators.scripts():
			try:
				with open(path, encoding="utf-8", errors="replace") as f:
					if marked(f.read()):
						have.append((name, path))
			except OSError:
				pass
		self.macrosdlg = MacrosDialog(r, have, self)
		self.macrosdlg.exec()
		changed = getattr(self.macrosdlg, "changed", None)
		self.macrosdlg = None
		if changed and self.parent() is not None and hasattr(self.parent(), "indicatorschanged"):
			self.parent().indicatorschanged()

	def period(self):
		days = RANGES[self.range.currentIndex()][1]
		last = self.data.last()
		return (last - timedelta(days=days) if days else None), last

	def compute(self):
		first, last = self.period()
		sw, rt = self.swing.value(), self.retr.value()
		self.results = {
			"day": byday(self.data, sw, rt, self.slot.currentData(), first, last),
			"week": byweek(self.data, sw, rt, first, last),
			"month": bymonth(self.data, sw, rt, first, last),
		}
		for k, c in self.charts.items():
			c.set(self.results[k])
		self.showsummary()

	def showsummary(self):
		kind = ["day", "week", "month"][self.tabs.currentIndex()]
		r = self.results.get(kind)
		if r is None:
			self.summary.setText("Not enough data for this.")
			return
		def fmt(top):
			return ", ".join(f"{n} ({p:.0%})" for n, p in top) or "none"
		self.summary.setText(f"From {r.n} {Chart.unit(r)}. Most likely swing starts: {fmt(r.top(5))}. "
			f"Retracements: {fmt(r.top(5, 'retr'))}.")

# ---------------------------------------------------------------- macro times in an indicator's source

MARK = "@dj-macros"	# a line of a script with it has the macro times in its first string: "HHMM-HHMM,HHMM-HHMM"

import re
STRING = re.compile(r'"([^"\\]*)"')

def marked(src):
	"""the lines of src (numbers from 0) holding macro times for the journal to update"""
	return [k for k, ln in enumerate(src.splitlines()) if MARK in ln and STRING.search(ln.split("//")[0] if "//" in ln else ln)]

def withmacros(src, times):
	"""src with the macro times of its marked lines replaced by times ("HHMM-HHMM,..."): (new source, [(old, new) lines])"""
	lines = src.splitlines(keepends=True)
	changes = []
	for k in marked(src):
		ln = lines[k]
		code, sep, comment = ln.partition("//")
		new = STRING.sub(lambda m: '"' + times + '"', code, count=1) + sep + comment
		if new != ln:
			changes.append((ln.rstrip("\n"), new.rstrip("\n")))
			lines[k] = new
	return "".join(lines), changes

def sortedtimes(wins):
	"""windows [("HHMM-HHMM", p)] as the string of macro times, by the clock from 18:00"""
	def key(w):
		m = int(w[:2]) * 60 + int(w[2:4])
		return (m - DAYSTART * 60) % 1440
	return ",".join(sorted((w for w, _ in wins), key=key))

class MacrosDialog(QDialog):
	"""the windows of the day most likely to start a swing, as macro times,
	and the scripts whose macro times can be set to them"""
	def __init__(self, res, scripts, parent=None):
		from PySide6.QtWidgets import QLineEdit, QListWidget, QMessageBox, QSlider
		super().__init__(parent)
		self.res, self.scripts = res, scripts
		self.setWindowTitle("Macro Times")
		self.resize(620, 420)
		lay = QVBoxLayout(self)
		note = QLabel("The times of the day most likely to start a swing (or a retracement), in New York time: "
			"the slots at or above the probability picked, joined when next to each other.")
		note.setWordWrap(True)
		lay.addWidget(note)
		row = QHBoxLayout()
		self.which = QComboBox()
		self.which.addItem("Swing starts", "swing")
		self.which.addItem("Retracement starts", "retr")
		row.addWidget(self.which)
		row.addWidget(QLabel("At least"))
		self.least = QSlider(Qt.Orientation.Horizontal)
		self.least.setRange(1, 100)
		self.least.setValue(max(1, int(round(float(np.percentile(res.swing, 75)) * 100))))
		row.addWidget(self.least, 1)
		self.leastlabel = QLabel()
		row.addWidget(self.leastlabel)
		lay.addLayout(row)
		self.list = QListWidget()
		lay.addWidget(self.list, 1)
		lay.addWidget(QLabel("Macro times (you can edit them):"))
		self.times = QLineEdit()
		lay.addWidget(self.times)
		row = QHBoxLayout()
		self.target = QComboBox()
		for name, path in scripts:
			self.target.addItem(name, path)
		self.update_ = QPushButton("Set in Indicator…")
		self.update_.setToolTip(f'replace the macro times of an indicator: the first string of its lines marked // {MARK}, '
			'as in  string djMacros = "0950-1010,1050-1110" // ' + MARK)
		self.update_.setEnabled(bool(scripts))
		if not scripts:
			self.target.addItem(f"no indicator has a line marked // {MARK}")
			self.target.setEnabled(False)
		row.addWidget(self.target, 1)
		row.addWidget(self.update_)
		close = QPushButton("Close")
		close.clicked.connect(self.close)
		row.addWidget(close)
		lay.addLayout(row)
		self.which.currentIndexChanged.connect(self.refill)
		self.least.valueChanged.connect(self.refill)
		self.update_.clicked.connect(self.apply)
		self.QMessageBox = QMessageBox
		self.refill()

	def wins(self):
		return windows(self.res, self.which.currentData(), self.least.value() / 100)

	def refill(self):
		self.leastlabel.setText(f"{self.least.value()}%")
		w = self.wins()
		self.list.clear()
		for t, p in w:
			self.list.addItem(f"{t[:2]}:{t[2:4]} – {t[5:7]}:{t[7:]}    {p:.0%} of the days")
		self.times.setText(sortedtimes(w))

	def apply(self):
		path = self.target.currentData()
		if not path:
			return False
		try:
			with open(path, encoding="utf-8") as f:
				src = f.read()
		except OSError as x:
			self.QMessageBox.warning(self, "Macro Times", f"Can't read it: {x}")
			return False
		new, changes = withmacros(src, self.times.text().strip())
		if not changes:
			self.QMessageBox.information(self, "Macro Times", "Its macro times are those already.")
			return False
		text = "\n\n".join(f"− {a.strip()}\n+ {b.strip()}" for a, b in changes)
		ok = self.QMessageBox.question(self, "Macro Times", f"Change {self.target.currentText()} ({path})?\n\n{text}\n\n"
			"The old one is kept next to it, ending in .bak.")
		if ok != self.QMessageBox.StandardButton.Yes:
			return False
		try:
			with open(path + ".bak", "w", encoding="utf-8") as f:
				f.write(src)
			with open(path + ".tmp", "w", encoding="utf-8") as f:
				f.write(new)
			import os
			os.replace(path + ".tmp", path)
		except OSError as x:
			self.QMessageBox.warning(self, "Macro Times", f"Can't write it: {x}")
			return False
		self.changed = path
		return True
