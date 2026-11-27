"""Strategy Tester: a Pine strategy run on the journal's data, as
TradingView's Strategy Tester does on the chart, and the trades it made.

backtest() runs it (in any thread) on the candles of a time frame from the
m15 data and the lower one, for a range of days; Report has the trades of
that range and their figures; TesterWindow (View ▸ Strategy Tester…) asks
for the strategy, time frame and range, runs it in the background and
shows the report."""

import csv
import os
import re
import sys
import threading
import time as _time
from datetime import datetime, timedelta, timezone

import numpy as np

import m15

WARM = 5000	# the candles a run starts with before the range (as TradingView keeps)

def isstrategy(path):
	"""whether the Pine source at path declares a strategy()"""
	try:
		with open(path, encoding="utf-8", errors="replace") as f:
			src = f.read()
	except OSError:
		return False
	return re.search(r"^\s*strategy\s*\(", src, re.M) is not None

def strategies(extra=()):
	"""[(name, path)] of the indicators that are strategies, and extra paths"""
	import indicators
	out = [(n, p) for n, p in indicators.scripts() if isstrategy(p)]
	have = {p for _, p in out}
	for p in extra:
		if p not in have and os.path.isfile(p):
			out.append((os.path.splitext(os.path.basename(p))[0], p))
	return out

def tfs(data, low):
	"""the time frames (minutes) a backtest can use"""
	if low is not None and len(low):
		out = [m for m in (1, 2, 3, 5, 10, 15, 30, 60, 240) if m % low.tf == 0]
	else:
		out = [m for m in (15, 30, 60, 240) if m % data.tf == 0]
	return out

def backtest(script, data, low, tf, first=None, last=None, inputs=None, stop=None, progress=None,
		commission=None, slippage=None, only=None):
	"""run script (a pine.Script) on the candles of tf minutes of data (and
	low) from day first to last (dates, None for all), with WARM candles
	before first. commission ($ a contract a side) and slippage (ticks)
	replace the strategy's when not None. only, a set of day numbers,
	keeps the trades entered on those days (the strategy runs on all the
	candles, to keep what it computes). A Report"""
	import pine
	from pine.feed import Feed
	up = m15.daystart([data.dayn(last) + 1])[0] if last else int(max(data.t[-1], low.t[-1] if low is not None and len(low) else 0)) + 86400
	feed = WholeFeed(data, low, up)
	since = None
	if first:
		since = int(m15.daystart([data.dayn(first)])[0])
	src = feed.source(tf)
	start = None
	if since is not None:
		k = int(np.searchsorted(src.t, since, "left"))
		k0 = max(0, k - WARM * max(1, tf // src.tf))
		start = int(src.t[k0]) if k0 < len(src.t) else since
	chart = feed.minutes(tf, since=start)
	t0 = _time.time()
	def before(b):
		if commission is not None:
			b.comtype, b.comvalue = "cash_per_contract", float(commission)
		if slippage is not None:
			b.slippage = int(slippage)
	res = pine.run(script, chart, feed, symbol=data.symbol or "NQ", inputs=inputs, stop=stop, progress=progress,
		plots=False, onstrategy=before)
	return Report(res, chart, since, tf, data.symbol or "NQ", _time.time() - t0, only)

from pine.feed import Feed as _Feed

class WholeFeed(_Feed):
	"""a Feed whose requested time frames have all the data, not the last
	candles of them only"""
	def __call__(self, key):
		kind, n = key
		if kind == "m":
			return self.minutes(n)
		if kind == "S":
			return self.minutes(1)
		return self.periods(kind, n)

class Report:
	"""the trades of a backtest made in its range (since, UTC s), and its
	figures; error and cancelled as those of the run"""
	def __init__(self, res, chart, since, tf, symbol, seconds, only=None):
		self.res = res
		self.error = res.error
		self.cancelled = res.cancelled
		self.title = res.title
		self.tf, self.symbol, self.seconds = tf, symbol, seconds
		self.chart = chart
		self.only = only
		b = res.strategy
		self.broker = b
		self.k0 = 0
		if since is not None and chart.n:
			self.k0 = int(np.searchsorted(chart.t, since * 1000, "left"))
		self.trades = []
		self.pointvalue = b.pointvalue if b else 1
		self.capital = b.capital if b else 0
		if b is None:
			if self.error is None:
				self.error = "it is not a strategy: it has no strategy() declaration"
			self.equity = np.zeros(0)
			return
		self.trades = [t for t in b.trades if t.bar >= self.k0]
		if only is not None:
			dn = m15.daynos(np.array([t.time // 1000 for t in self.trades], dtype=np.int64)) if self.trades else []
			self.trades = [t for t, d in zip(self.trades, dn) if int(d) in only]
		n = chart.n
		closed = b.closedeq if b.closedeq is not None else np.zeros(n)
		opn = b.openeq if b.openeq is not None else np.zeros(n)
		ran = max(b.lastbar + 1, self.k0)
		eq = closed[:ran] + opn[:ran]
		before = b.trades and sum(t.profit for t in b.trades if t.bar < self.k0 and not t.open)
		self.equity = eq[self.k0:] - (before or 0)	# from the range's start
		if only is not None:	# the closed profit of the trades kept, as they closed
			e = np.zeros(ran)
			for t in self.trades:
				if not t.open and t.exitbar < ran:
					e[t.exitbar] += t.profit
			self.equity = np.cumsum(e)[self.k0:]
		self.etimes = chart.t[self.k0:ran]

	def stats(self, which="all"):
		"""{figure: value} of the closed trades (all, long or short)"""
		tr = [t for t in self.trades if not t.open and (which == "all" or (t.dir > 0) == (which == "long"))]
		p = np.array([t.profit for t in tr]) if tr else np.zeros(0)
		pts = np.array([t.points for t in tr]) if tr else np.zeros(0)
		win, loss = p[p > 0], p[p < 0]
		gp, gl = float(win.sum()), float(-loss.sum())
		out = {
			"Net profit": float(p.sum()),
			"Net points": float(pts.sum()),
			"Gross profit": gp,
			"Gross loss": gl,
			"Profit factor": gp / gl if gl else (float("inf") if gp else float("nan")),
			"Trades": len(tr),
			"Winning trades": len(win),
			"Losing trades": len(loss),
			"Win rate": len(win) / len(tr) if tr else float("nan"),
			"Average trade": float(p.mean()) if len(p) else float("nan"),
			"Average win": float(win.mean()) if len(win) else float("nan"),
			"Average loss": float(loss.mean()) if len(loss) else float("nan"),
			"Win / loss ratio": float(win.mean() / -loss.mean()) if len(win) and len(loss) else float("nan"),
			"Largest win": float(win.max()) if len(win) else float("nan"),
			"Largest loss": float(loss.min()) if len(loss) else float("nan"),
			"Max consecutive losses": maxrun(p < 0),
			"Average bars in trade": float(np.mean([t.exitbar - t.bar for t in tr])) if tr else float("nan"),
			"Commission paid": float(sum(t.commission for t in tr)),
		}
		if which == "all":
			out["Max drawdown"] = maxdrawdown(self.equity)
			out["Open trades"] = sum(1 for t in self.trades if t.open)
		return out

	def byhour(self):
		"""[(hour of entry, NY time), trades, net profit, win rate)]"""
		rows = {}
		for t in self.trades:
			if t.open:
				continue
			h = nytime(t.time).hour
			r = rows.setdefault(h, [0, 0.0, 0])
			r[0] += 1
			r[1] += t.profit
			r[2] += t.profit > 0
		return [(h, n, p, w / n) for h, (n, p, w) in sorted(rows.items(), key=lambda x: (x[0] - 18) % 24)]

	def by(self, kind):
		"""[(label, trades, net profit, net points, win rate, profit factor)]
		of the closed trades by the year, month, weekday, killzone session
		(New York time, as ICTlevels has them) or hour they were entered in
		(kind: one of BYKINDS)"""
		rows = {}
		for t in self.trades:
			if t.open:
				continue
			k = periodof(nytime(t.time), kind)
			r = rows.setdefault(k, [0, 0.0, 0.0, 0, 0.0, 0.0])
			r[0] += 1
			r[1] += t.profit
			r[2] += t.points
			r[3] += t.profit > 0
			if t.profit > 0:
				r[4] += t.profit
			else:
				r[5] -= t.profit
		out = []
		for k in sorted(rows, key=lambda k: periodsort(k, kind)):
			n, p, pts, w, gp, gl = rows[k]
			out.append((periodlabel(k, kind), n, p, pts, w / n, gp / gl if gl else (float("inf") if gp else float("nan"))))
		return out

	def tocsv(self, path):
		with open(path, "w", newline="") as f:
			w = csv.writer(f)
			w.writerow(["Trade", "Type", "Signal", "Entry time (New York)", "Entry price", "Exit signal",
				"Exit time (New York)", "Exit price", "Contracts", "Points", "Profit", "Run-up (points)", "Drawdown (points)"])
			for k, t in enumerate(self.trades, 1):
				w.writerow([k, "Long" if t.dir > 0 else "Short", t.id, fmttime(t.time), t.price,
					t.exitid or "Open", fmttime(t.exittime) if t.exittime else "", "" if t.exitprice is None else t.exitprice,
					t.qty, round(t.points, 4) + 0.0, round(t.profit, 2) + 0.0, round(t.runup(), 4) + 0.0, round(t.drawdown(), 4) + 0.0])

BYKINDS = ["Year", "Month", "Weekday", "Session", "Hour"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SESSIONS = [("Asia", 20 * 60, 24 * 60), ("London", 2 * 60, 5 * 60), ("NY AM", 7 * 60, 11 * 60 + 30),
	("NY PM", 13 * 60 + 30, 16 * 60)]	# the killzones (New York time), as ICTlevels

def periodof(nt, kind):
	"""the period of kind (BYKINDS) of nt, a New York time"""
	if kind == "Year":
		return nt.year
	if kind == "Month":
		return (nt.year, nt.month)
	if kind == "Weekday":
		return nt.weekday()
	if kind == "Hour":
		return nt.hour
	m = nt.hour * 60 + nt.minute
	for k, (_, a, b) in enumerate(SESSIONS):
		if a <= m < b:
			return k
	return len(SESSIONS)	# outside them

def periodsort(k, kind):
	return (k - 18) % 24 if kind == "Hour" else k

def periodlabel(k, kind):
	if kind == "Month":
		return f"{k[0]}-{k[1]:02d}"
	if kind == "Weekday":
		return WEEKDAYS[k]
	if kind == "Session":
		return SESSIONS[k][0] if k < len(SESSIONS) else "Other"
	if kind == "Hour":
		return f"{k:02d}:00"
	return str(k)

def parsevalue(inp, s):
	"""the value of input inp (a runtime.Input) written as s"""
	s = s.strip()
	if inp.kind == "bool":
		if s.lower() in ("true", "on", "yes", "1"):
			return True
		if s.lower() in ("false", "off", "no", "0"):
			return False
		raise ValueError(f"{inp.title}: {s} is not true or false")
	if inp.kind == "int":
		return int(float(s))
	if inp.kind == "float":
		return float(s)
	opts = inp.args.get("options")
	if opts and s not in opts:
		m = [o for o in opts if str(o).lower() == s.lower()]
		if not m:
			raise ValueError(f"{inp.title}: {s} is not one of {', '.join(map(str, opts))}")
		s = m[0]
	return s

def combos(axes):
	"""the combinations of axes [(input key, [values])]: [{key: value}]"""
	out = [{}]
	for key, vals in axes:
		out = [{**c, key: v} for c in out for v in vals]
	return out

def compare(script, data, low, tf, axes, first=None, last=None, inputs=None, stop=None, progress=None,
		commission=None, slippage=None, only=None, each=None):
	"""backtest script for each combination of the values of axes [(input
	key, [values])] on top of inputs: [(combination, Report)], one after
	the other (pine runs one script at a time). each(k, n, combination,
	report) is called after each run; stop ends it with the runs made"""
	out = []
	cs = combos(axes)
	for k, c in enumerate(cs):
		if stop is not None and stop.is_set():
			break
		def prog(i, n, k=k):
			if progress:
				progress(k * n + i, len(cs) * n)
		rep = backtest(script, data, low, tf, first, last, {**(inputs or {}), **c}, stop, prog, commission, slippage, only)
		if rep.cancelled and out:
			break
		out.append((c, rep))
		if each:
			each(k, len(cs), c, rep)
	return out

def inputspecs(script, data, low, tf):
	"""the inputs of script ([runtime.Input]), from a short run"""
	import pine
	from pine.feed import Feed
	feed = Feed(data, low, int(max(data.t[-1], low.t[-1] if low is not None and len(low) else 0)) + 900)
	r = pine.run(script, feed.minutes(tf, nbars=300), feed, symbol=data.symbol or "NQ", plots=False)
	return r.inputs

def findinput(specs, name):
	"""the input of specs named name: its key, or its title when only one has it"""
	for i in specs:
		if i.key == name:
			return i
	m = [i for i in specs if i.title == name] or [i for i in specs if i.title.lower().startswith(name.lower())]
	if len(m) != 1:
		raise ValueError(f"no input {name}" if not m else f"{name} is the title of {len(m)} inputs: give its key, one of "
			+ "; ".join(i.key for i in m))
	return m[0]

def maxrun(mask):
	best = run = 0
	for x in mask:
		run = run + 1 if x else 0
		best = max(best, run)
	return best

def maxdrawdown(eq):
	if not len(eq):
		return 0.0
	peak = np.maximum.accumulate(np.r_[0.0, eq])
	return float(np.max(peak - np.r_[0.0, eq]))

def nytime(ms):
	t = int(ms) // 1000
	return datetime.fromtimestamp(t + int(m15.nyoffsets(np.array([t]))[0]), timezone.utc).replace(tzinfo=None)

def fmttime(ms):
	return nytime(ms).strftime("%Y-%m-%d %H:%M")

# ---------------------------------------------------------------- the window

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
	QLineEdit, QMessageBox, QProgressBar, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QToolTip,
	QVBoxLayout, QWidget)

BLUE = QColor("#257de0")
RED = QColor("#e0453a")
GREEN = QColor("#2a9d5c")

class EquityChart(QWidget):
	"""the equity of a Report (net profit, closed and open, at each candle),
	pointed at to read it"""
	def __init__(self, parent=None):
		super().__init__(parent)
		self.rep = None
		self.at = None
		self.setMouseTracking(True)
		self.setMinimumHeight(220)

	def set(self, rep):
		self.rep = rep
		self.update()

	def geom(self):
		return QRectF(64, 12, self.width() - 80, self.height() - 40)

	def paintEvent(self, ev):
		p = QPainter(self)
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		pal = self.palette()
		text = pal.color(pal.ColorRole.WindowText)
		faint = QColor(text)
		faint.setAlphaF(0.15)
		r = self.geom()
		rep = self.rep
		if rep is None or not len(rep.equity):
			p.setPen(text)
			p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Run a strategy to see its equity")
			return
		eq = rep.equity
		lo, hi = min(0.0, float(eq.min())), max(0.0, float(eq.max()))
		if hi - lo < 1e-9:
			hi = lo + 1
		pad = (hi - lo) * 0.05
		lo, hi = lo - pad, hi + pad
		n = len(eq)
		X = lambda k: r.left() + r.width() * k / max(n - 1, 1)
		Y = lambda v: r.bottom() - r.height() * (v - lo) / (hi - lo)
		# grid and price labels
		p.setFont(self.font())
		for k in range(5):
			v = lo + (hi - lo) * k / 4
			y = Y(v)
			p.setPen(QPen(faint, 1))
			p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
			p.setPen(text)
			p.drawText(QRectF(0, y - 8, 58, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{v:,.0f}")
		zero = QPen(text, 1)
		zero.setColor(QColor(text.red(), text.green(), text.blue(), 110))
		p.setPen(zero)
		p.drawLine(QPointF(r.left(), Y(0)), QPointF(r.right(), Y(0)))
		# dates
		ts = rep.etimes
		for k in range(5):
			i = int((n - 1) * k / 4)
			x = X(i)
			p.setPen(text)
			lab = nytime(ts[i]).strftime("%d %b %y")
			box = QRectF(x - 40, r.bottom() + 6, 80, 16)
			if box.right() > self.width():
				box.moveRight(self.width() - 2)
			p.drawText(box, Qt.AlignmentFlag.AlignCenter, lab)
		# the line, decimated to the pixels
		step = max(1, n // max(int(r.width()), 1))
		idx = np.arange(0, n, step)
		path = QPainterPath(QPointF(X(idx[0]), Y(eq[idx[0]])))
		for i in idx[1:]:
			path.lineTo(QPointF(X(i), Y(eq[i])))
		path.lineTo(QPointF(X(n - 1), Y(eq[-1])))
		p.setPen(QPen(BLUE, 2))
		p.drawPath(path)
		if self.at is not None:
			i = self.at
			x, y = X(i), Y(eq[i])
			p.setPen(QPen(faint, 1))
			p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
			p.setPen(QPen(pal.color(pal.ColorRole.Window), 2))
			p.setBrush(BLUE)
			p.drawEllipse(QPointF(x, y), 4, 4)

	def mouseMoveEvent(self, ev):
		rep = self.rep
		if rep is None or not len(rep.equity):
			return
		r = self.geom()
		n = len(rep.equity)
		i = int(round((ev.position().x() - r.left()) / max(r.width(), 1) * (n - 1)))
		i = max(0, min(n - 1, i))
		self.at = i
		QToolTip.showText(ev.globalPosition().toPoint(), f"{fmttime(rep.etimes[i])}\nnet profit: {money(rep.equity[i])}", self)
		self.update()

	def leaveEvent(self, ev):
		self.at = None
		self.update()

class _Signals(QObject):
	progress = Signal(int, int)
	done = Signal(object)
	compared = Signal(int, int, object, object)	# a run of a comparison: k, n, combination, report
	comparedone = Signal(object)

class TesterWindow(QDialog):
	"""View ▸ Strategy Tester: a strategy run on the data, its figures,
	equity and trades"""
	COLS = ["#", "Type", "Signal", "Entry (New York)", "Price", "Exit", "Exit time", "Price", "Points", "Profit",
		"Run-up", "Drawdown"]

	def __init__(self, win, parent=None):
		super().__init__(parent or win)
		self.win = win
		self.data = win.data
		self.rep = None
		self.thread = None
		self.stopper = None
		self.setWindowTitle(f"Strategy Tester · {self.data.symbol or ''}")
		self.resize(1100, 720)
		lay = QVBoxLayout(self)
		row = QHBoxLayout()
		row.addWidget(QLabel("Strategy"))
		self.strategy = QComboBox()
		self.strategy.setMinimumWidth(240)
		row.addWidget(self.strategy)
		self.settingsbtn = QPushButton("Settings…")
		self.settingsbtn.setToolTip("the strategy's inputs, as its indicator settings: the same for the charts")
		self.settingsbtn.clicked.connect(self.settings)
		row.addWidget(self.settingsbtn)
		self.filebtn = QPushButton("Add File…")
		self.filebtn.setToolTip("a Pine strategy kept elsewhere, to test")
		self.filebtn.clicked.connect(self.addfile)
		row.addWidget(self.filebtn)
		row.addStretch(1)
		lay.addLayout(row)
		row = QHBoxLayout()
		row.addWidget(QLabel("Time frame"))
		self.tf = QComboBox()
		row.addWidget(self.tf)
		import patterns
		self.range = QComboBox()
		for name, _ in patterns.RANGES:
			self.range.addItem(name)
		row.addWidget(QLabel("Range"))
		row.addWidget(self.range)
		row.addWidget(QLabel("Commission"))
		self.commission = QDoubleSpinBox()
		self.commission.setRange(0, 50)
		self.commission.setDecimals(2)
		self.commission.setPrefix("$")
		self.commission.setSuffix(" a contract a side")
		self.commission.setSpecialValueText("the strategy's")
		self.commission.setValue(0)
		row.addWidget(self.commission)
		row.addWidget(QLabel("Slippage"))
		self.slippage = QSpinBox()
		self.slippage.setRange(0, 40)
		self.slippage.setSuffix(" ticks")
		self.slippage.setSpecialValueText("the strategy's")
		row.addWidget(self.slippage)
		row.addStretch(1)
		self.runbtn = QPushButton("Run")
		self.runbtn.setDefault(True)
		self.runbtn.clicked.connect(self.runorstop)
		row.addWidget(self.runbtn)
		lay.addLayout(row)
		row = QHBoxLayout()
		self.bar = QProgressBar()
		self.bar.setTextVisible(False)
		self.bar.setMaximumHeight(8)
		self.bar.hide()
		row.addWidget(self.bar, 1)
		lay.addLayout(row)
		self.status = QLabel("")
		self.status.setWordWrap(True)
		self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
		lay.addWidget(self.status)
		self.tabs = QTabWidget()
		over = QWidget()
		ol = QVBoxLayout(over)
		ol.setContentsMargins(0, 0, 0, 0)
		self.chart = EquityChart()
		ol.addWidget(self.chart, 3)
		self.figures = QTableWidget(0, 4)
		self.figures.setHorizontalHeaderLabels(["", "All", "Long", "Short"])
		self.figures.verticalHeader().hide()
		self.figures.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
		self.figures.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
		ol.addWidget(self.figures, 2)
		self.tabs.addTab(over, "Overview")
		self.table = QTableWidget(0, len(self.COLS))
		self.table.setHorizontalHeaderLabels(self.COLS)
		self.table.verticalHeader().hide()
		self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
		self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
		self.table.setToolTip("double click a trade to show its day in the data view")
		self.table.cellClicked.connect(self.showtrade)
		self.tabs.addTab(self.table, "List of Trades")
		self.hours = QTableWidget(0, 4)
		self.hours.setHorizontalHeaderLabels(["Entry hour (New York)", "Trades", "Net profit", "Win rate"])
		self.hours.verticalHeader().hide()
		self.hours.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
		self.hours.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
		self.tabs.addTab(self.hours, "By Hour")
		per = QWidget()
		pl = QVBoxLayout(per)
		pl.setContentsMargins(0, 0, 0, 0)
		prow = QHBoxLayout()
		prow.addWidget(QLabel("By"))
		self.bykind = QComboBox()
		for k in BYKINDS[:-1]:
			self.bykind.addItem(k)
		self.bykind.setToolTip("the trades by the year, month or weekday they were entered in, or by the killzone "
			"(New York time: Asia 20:00-00:00, London 02:00-05:00, NY AM 07:00-11:30, NY PM 13:30-16:00, or Other)")
		self.bykind.currentIndexChanged.connect(self.fillperiods)
		prow.addWidget(self.bykind)
		prow.addStretch(1)
		pl.addLayout(prow)
		self.periods = QTableWidget(0, 6)
		self.periods.setHorizontalHeaderLabels(["", "Trades", "Net profit", "Net points", "Win rate", "Profit factor"])
		self.periods.verticalHeader().hide()
		self.periods.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
		self.periods.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
		pl.addWidget(self.periods, 1)
		self.tabs.addTab(per, "By Period")
		cmp = QWidget()
		cl = QVBoxLayout(cmp)
		cl.setContentsMargins(0, 0, 0, 0)
		crow = QHBoxLayout()
		self.cmpin, self.cmpvals = [], []
		for k in range(2):
			crow.addWidget(QLabel("Input" if k == 0 else "and"))
			c = QComboBox()
			c.setMinimumWidth(200)
			c.setToolTip("an input of the strategy whose values are compared" if k == 0 else
				"a second input: every combination of the values of both is run")
			crow.addWidget(c)
			e = QLineEdit()
			e.setPlaceholderText("values, by commas: 1, 2, 3 · true, false · an option")
			crow.addWidget(e, 1)
			self.cmpin.append(c)
			self.cmpvals.append(e)
		self.cmpbtn = QPushButton("Compare")
		self.cmpbtn.setToolTip("run the strategy once for each value (or combination), with the time frame, range, "
			"commission and slippage above and the other inputs as set")
		self.cmpbtn.clicked.connect(self.compareorstop)
		crow.addWidget(self.cmpbtn)
		cl.addLayout(crow)
		self.cmptable = QTableWidget(0, 0)
		self.cmptable.verticalHeader().hide()
		self.cmptable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
		self.cmptable.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
		self.cmptable.setToolTip("net points by year at the right; click a run to see its figures and trades in "
			"the other tabs")
		self.cmptable.cellClicked.connect(self.showcompared)
		cl.addWidget(self.cmptable, 1)
		self.tabs.addTab(cmp, "Compare")
		self.tabs.currentChanged.connect(self.ontab)
		self.cmpspecs = None	# (path, tf, [runtime.Input]) the inputs are listed for
		self.cmpruns = []
		lay.addWidget(self.tabs, 1)
		row = QHBoxLayout()
		self.exportbtn = QPushButton("Export Trades…")
		self.exportbtn.setEnabled(False)
		self.exportbtn.clicked.connect(self.export)
		row.addWidget(self.exportbtn)
		row.addStretch(1)
		close = QPushButton("Close")
		close.clicked.connect(self.close)
		row.addWidget(close)
		lay.addLayout(row)
		self.sig = _Signals()
		self.sig.progress.connect(self.onprogress)
		self.sig.done.connect(self.ondone)
		self.sig.compared.connect(self.oncompared)
		self.sig.comparedone.connect(self.oncomparedone)
		self.strategy.currentIndexChanged.connect(lambda _: self.listinputs(False))
		self.fill()

	# ------------------------------------------------------------ choices

	def settings_(self):
		import mainwin
		return mainwin.settings()

	def extra(self):
		v = self.settings_().value("tester/files", [])
		if isinstance(v, str):
			v = [v] if v else []
		return [p for p in (v or []) if os.path.isfile(p)]

	def fill(self):
		s = self.settings_()
		cur = self.strategy.currentData() or s.value("tester/strategy", "")
		self.strategy.clear()
		for name, path in strategies(self.extra()):
			self.strategy.addItem(name, path)
		k = self.strategy.findData(cur)
		if k >= 0:
			self.strategy.setCurrentIndex(k)
		if not self.strategy.count():
			self.strategy.addItem("no strategies: import one or Add File…")
			self.strategy.setEnabled(False)
		else:
			self.strategy.setEnabled(True)
		self.tf.clear()
		low = self.win.getlow()
		for m in tfs(self.data, low):
			self.tf.addItem(m15.tfname(m), m)
		k = self.tf.findData(int(s.value("tester/tf", 5) or 5))
		self.tf.setCurrentIndex(k if k >= 0 else 0)
		self.range.setCurrentIndex(int(s.value("tester/range", 0) or 0))

	def addfile(self):
		path, _ = QFileDialog.getOpenFileName(self, "Pine Strategy", "", "Pine scripts (*.txt *.pine);;All files (*)")
		if not path:
			return
		if not isstrategy(path):
			QMessageBox.information(self, "Strategy Tester", f"{os.path.basename(path)} has no strategy() declaration.")
			return
		files = self.extra()
		if path not in files:
			files.append(path)
		self.settings_().setValue("tester/files", files)
		self.fill()
		self.strategy.setCurrentIndex(max(0, self.strategy.findData(path)))

	def name(self):
		path = self.strategy.currentData()
		return (self.strategy.currentText(), path) if path else (None, None)

	def settings(self, accept=None):
		"""the inputs of the strategy, from a short run, as its indicator settings"""
		import indicators
		import pine
		from pine.feed import Feed
		name, path = self.name()
		if not path:
			return
		with open(path, encoding="utf-8", errors="replace") as f:
			script = pine.Script(f.read(), name)
		if script.error:
			QMessageBox.warning(self, "Strategy Tester", f"{name}: {script.error}")
			return
		low = self.win.getlow()
		feed = Feed(self.data, low, int(self.data.t[-1]) + 900)
		r = pine.run(script, feed.minutes(self.tf.currentData() or 15, nbars=300), feed, symbol=self.data.symbol or "NQ",
			inputs=indicators.inputs(name), plots=False)
		if indicators.inputsdialog(self, name, r.inputs, r.title or name, accept) and hasattr(self.win, "indicatorschanged"):
			self.win.indicatorschanged()

	def period(self):
		import patterns
		days = patterns.RANGES[self.range.currentIndex()][1]
		last = self.data.last()
		return (last - timedelta(days=days) if days else None), last

	# ------------------------------------------------------------ running

	def runorstop(self):
		if self.thread is not None:
			self.stopper.set()
			self.runbtn.setEnabled(False)
			return
		self.run()

	def run(self, wait=False):
		import indicators
		import pine
		name, path = self.name()
		if not path:
			return
		with open(path, encoding="utf-8", errors="replace") as f:
			script = pine.Script(f.read(), name)
		if script.error:
			self.status.setText(f"{name}: {script.error}")
			return
		tf = self.tf.currentData()
		s = self.settings_()
		s.setValue("tester/strategy", path)
		s.setValue("tester/tf", tf)
		s.setValue("tester/range", self.range.currentIndex())
		low = self.win.getlow()
		first, last = self.period()
		com = self.commission.value() or None
		slip = self.slippage.value() or None
		values = indicators.inputs(name)
		f = self.win.filtered() if hasattr(self.win, "filtered") else None
		only = f[0] if f else None
		self.stopper = threading.Event()
		self.runbtn.setText("Stop")
		self.bar.setRange(0, 0)
		self.bar.show()
		self.status.setText(f"Running {name} on {m15.tfname(tf)} candles… charts wait for their indicators meanwhile.")
		indicators.cancel()
		def work():
			try:
				rep = backtest(script, self.data, low, tf, first, last, values, self.stopper,
					lambda i, n: self.sig.progress.emit(i, n), com, slip, only)
			except Exception as x:	# said, not raised in the thread
				rep = x
			self.sig.done.emit(rep)
		self.thread = threading.Thread(target=work, daemon=True)
		self.thread.start()
		if wait:
			self.thread.join()
			from PySide6.QtWidgets import QApplication
			QApplication.processEvents()

	def onprogress(self, i, n):
		self.bar.setRange(0, n)
		self.bar.setValue(i)

	def ondone(self, rep):
		self.thread = None
		self.runbtn.setText("Run")
		self.runbtn.setEnabled(True)
		self.bar.hide()
		if isinstance(rep, Exception):
			self.status.setText(f"The run failed: {type(rep).__name__}: {rep}")
			return
		self.show_(rep)

	def show_(self, rep):
		self.rep = rep
		self.chart.set(rep)
		st = rep.stats()
		head = f"{rep.title or 'Strategy'} on {rep.symbol} {m15.tfname(rep.tf)}: "
		if rep.error and rep.broker is None:
			self.status.setText(head + rep.error)
		else:
			pf = st["Profit factor"]
			msg = (f"{st['Trades']} trades, net {money(st['Net profit'])} ({st['Net points']:,.2f} points), "
				f"win rate {pct(st['Win rate'])}, profit factor {num(pf)}, max drawdown {money(st['Max drawdown'])}. "
				f"{rep.chart.n - rep.k0:,} candles in {rep.seconds:.1f} s.")
			if rep.only is not None:
				msg += f" Only the trades entered on the {len(rep.only):,} days the search leaves in the list."
			if rep.cancelled:
				msg += " Stopped before the end: these are the trades up to there."
			if rep.error:
				msg += f" It failed: {rep.error}"
			self.status.setText(head + msg)
		self.exportbtn.setEnabled(bool(rep.trades))
		figs = [rep.stats(w) for w in ("all", "long", "short")]
		keys = list(figs[0])
		self.figures.setRowCount(len(keys))
		for k, key in enumerate(keys):
			self.figures.setItem(k, 0, QTableWidgetItem(key))
			for j, f in enumerate(figs, 1):
				v = f.get(key)
				self.figures.setItem(k, j, QTableWidgetItem("" if v is None else fmtfig(key, v)))
		self.table.setRowCount(len(rep.trades))
		for k, t in enumerate(rep.trades):
			vals = [k + 1, "Long" if t.dir > 0 else "Short", t.id, fmttime(t.time), f"{t.price:.2f}",
				t.exitid or "Open", fmttime(t.exittime) if t.exittime else "",
				"" if t.exitprice is None else f"{t.exitprice:.2f}", f"{t.points:.2f}", f"{t.profit:,.2f}",
				f"{t.runup():.2f}", f"{t.drawdown():.2f}"]
			for j, v in enumerate(vals):
				it = QTableWidgetItem(str(v))
				if j == 9 and not t.open:
					it.setForeground(GREEN if t.profit > 0 else RED if t.profit < 0 else it.foreground())
				if j in (0, 4, 7, 8, 9, 10, 11):
					it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
				self.table.setItem(k, j, it)
		self.table.resizeColumnsToContents()
		self.fillperiods()
		hrs = rep.byhour()
		self.hours.setRowCount(len(hrs))
		for k, (h, n, p, w) in enumerate(hrs):
			for j, v in enumerate([f"{h:02d}:00", str(n), money(p), pct(w)]):
				self.hours.setItem(k, j, QTableWidgetItem(v))

	def fillperiods(self, _=None):
		rep = self.rep
		rows = rep.by(self.bykind.currentText()) if rep is not None and rep.broker is not None else []
		self.periods.setRowCount(len(rows))
		for k, (lb, n, p, pts, w, pf) in enumerate(rows):
			for j, v in enumerate([lb, f"{n:,}", money(p), num(pts), pct(w), num(pf)]):
				it = QTableWidgetItem(v)
				if j == 2:
					it.setForeground(GREEN if p > 0 else RED if p < 0 else it.foreground())
				self.periods.setItem(k, j, it)

	# ------------------------------------------------------------ comparing inputs

	def ontab(self, k):
		if self.tabs.tabText(k) == "Compare":
			self.listinputs(True)

	def listinputs(self, load=True):
		"""list the strategy's inputs in the Compare tab (a short run)"""
		import pine
		name, path = self.name()
		key = (path, self.tf.currentData())
		if self.cmpspecs is not None and self.cmpspecs[0] == key:
			return
		for c in self.cmpin:
			c.clear()
		self.cmpspecs = None
		if not path or not load:
			return
		with open(path, encoding="utf-8", errors="replace") as f:
			script = pine.Script(f.read(), name)
		if script.error:
			self.status.setText(f"{name}: {script.error}")
			return
		try:
			specs = [i for i in inputspecs(script, self.data, self.win.getlow(), key[1] or 15)
				if i.kind in ("bool", "int", "float", "string", "timeframe", "session")]
		except Exception as x:
			self.status.setText(f"{name}: its inputs: {x}")
			return
		self.cmpspecs = (key, specs)
		for k, c in enumerate(self.cmpin):
			if k:
				c.addItem("—", None)
			for i in specs:
				grp = i.args.get("group") or ""
				c.addItem((f"{grp}: " if grp else "") + (i.title or i.key), i.key)
				c.setItemData(c.count() - 1, f"{i.kind}, now {i.defval}" + (f"; one of {', '.join(map(str, i.args['options']))}"
					if i.args.get("options") else ""), Qt.ItemDataRole.ToolTipRole)

	def axes(self):
		"""[(input key, [values])] of the Compare tab; ValueError when wrong"""
		if self.cmpspecs is None:
			raise ValueError("the strategy's inputs are not listed")
		specs = {i.key: i for i in self.cmpspecs[1]}
		out = []
		for c, e in zip(self.cmpin, self.cmpvals):
			key = c.currentData()
			if key is None:
				continue
			vals = [v for v in e.text().split(",") if v.strip()]
			if not vals:
				if not out:
					raise ValueError("no values to compare")
				continue
			out.append((key, [parsevalue(specs[key], v) for v in vals]))
		return out

	def compareorstop(self):
		if self.thread is not None:
			self.stopper.set()
			self.cmpbtn.setEnabled(False)
			return
		self.compare_()

	def compare_(self, wait=False):
		import indicators
		import pine
		name, path = self.name()
		if not path:
			return
		self.listinputs(True)
		try:
			axes = self.axes()
		except ValueError as x:
			self.status.setText(f"Compare: {x}")
			return
		with open(path, encoding="utf-8", errors="replace") as f:
			script = pine.Script(f.read(), name)
		tf = self.tf.currentData()
		low = self.win.getlow()
		first, last = self.period()
		com = self.commission.value() or None
		slip = self.slippage.value() or None
		values = indicators.inputs(name)
		f = self.win.filtered() if hasattr(self.win, "filtered") else None
		only = f[0] if f else None
		titles = {i.key: i.title for i in self.cmpspecs[1]}
		self.cmpcols = [titles.get(k, k) for k, _ in axes]
		self.cmpkeys = [k for k, _ in axes]
		self.cmpruns = []
		self.cmptable.setRowCount(0)
		self.stopper = threading.Event()
		self.cmpbtn.setText("Stop")
		self.runbtn.setEnabled(False)
		self.bar.setRange(0, 0)
		self.bar.show()
		n = len(combos(axes))
		self.status.setText(f"Comparing {n} runs of {name} on {m15.tfname(tf)} candles…")
		indicators.cancel()
		def work():
			try:
				res = compare(script, self.data, low, tf, axes, first, last, values, self.stopper,
					lambda i, n: self.sig.progress.emit(i, n), com, slip, only,
					lambda k, n, c, rep: self.sig.compared.emit(k, n, c, rep))
			except Exception as x:
				res = x
			self.sig.comparedone.emit(res)
		self.thread = threading.Thread(target=work, daemon=True)
		self.thread.start()
		if wait:
			self.thread.join()
			from PySide6.QtWidgets import QApplication
			QApplication.processEvents()

	def oncompared(self, k, n, c, rep):
		self.cmpruns.append((c, rep))
		years = sorted({y for _, r in self.cmpruns if r.broker is not None for y, *_ in r.by("Year")})
		cols = self.cmpcols + ["Trades", "Net points", "Points a trade", "Net profit", "Win rate", "Profit factor",
			"Max drawdown"] + [str(y) for y in years]
		self.cmptable.setColumnCount(len(cols))
		self.cmptable.setHorizontalHeaderLabels(cols)
		self.cmptable.setRowCount(len(self.cmpruns))
		for row, (c, r) in enumerate(self.cmpruns):
			st = r.stats() if r.broker is not None else None
			ys = {lb: pts for lb, _, _, pts, _, _ in r.by("Year")} if st else {}
			vals = [str(c.get(key)) for key in self.cmpkeys]
			if st:
				nt = st["Trades"]
				vals += [f"{nt:,}", num(st["Net points"]), num(st["Net points"] / nt) if nt else "—", money(st["Net profit"]),
					pct(st["Win rate"]), num(st["Profit factor"]), money(st["Max drawdown"])]
				vals += [num(ys[str(y)]) if str(y) in ys else "" for y in years]
			else:
				vals += [r.error or "failed"]
			for j, v in enumerate(vals):
				it = QTableWidgetItem(v)
				if j >= len(self.cmpkeys):
					it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
				self.cmptable.setItem(row, j, it)
		self.cmptable.resizeColumnsToContents()
		self.status.setText(f"Compared {k + 1} of {n} runs…")

	def oncomparedone(self, res):
		self.thread = None
		self.cmpbtn.setText("Compare")
		self.cmpbtn.setEnabled(True)
		self.runbtn.setEnabled(True)
		self.bar.hide()
		if isinstance(res, Exception):
			self.status.setText(f"The comparison failed: {type(res).__name__}: {res}")
			return
		traded = [cr for cr in res if cr[1].broker is not None and cr[1].stats()["Trades"]]
		best = max(traded, key=lambda cr: cr[1].stats()["Net points"], default=None)
		msg = f"Compared {len(res)} runs."
		if best is not None:
			msg += " Most net points: " + ", ".join(f"{t} = {best[0].get(k)}" for t, k in zip(self.cmpcols, self.cmpkeys)) + \
				f" ({best[1].stats()['Net points']:,.2f} points). Click a run to see it in the other tabs."
		self.status.setText(msg)

	def showcompared(self, row, _col=0):
		if 0 <= row < len(self.cmpruns):
			self.show_(self.cmpruns[row][1])

	def showtrade(self, row, _col=0):
		"""show trade row on the data view, in the time frame of the test,
		zoomed on it, drawn as a position"""
		if self.rep is None or row >= len(self.rep.trades):
			return
		t = self.rep.trades[row]
		w = self.win
		if not hasattr(w, "setdatamode"):
			return
		info = tradeinfo(t, self.rep.tf)
		w.tradeshown = info
		if not w.datamode:
			w.setdatamode(True)
		if not w.datamode:
			return
		tf = self.rep.tf
		w.setdatatf(tf)
		d = m15.Data.daydate(int(m15.daynos(np.array([info["at"] // 1000]))[0]))
		from dataview import Geom
		g = Geom(w.data, "d", d, tf, w.getlow() if tf < 15 else None)
		if g.ok:
			w.datazooms[("d", d, tf)] = tradeview(g, info)
		w.showdata(("d", d), force=True)
		w.raise_()
		w.activateWindow()

	def export(self, path=None):
		if self.rep is None:
			return
		if not path:
			path, _ = QFileDialog.getSaveFileName(self, "Export Trades", f"{self.rep.title or 'trades'}.csv", "CSV (*.csv)")
		if path:
			self.rep.tocsv(path)
			self.status.setText(self.status.text().split(" Exported")[0] + f" Exported to {path}.")

	def closeEvent(self, ev):
		if self.stopper is not None:
			self.stopper.set()
		w = self.win
		if getattr(w, "tradeshown", None) is not None:	# the trade drawn goes with the tester
			w.tradeshown = None
			if w.datamode and w.datakey is not None:
				w.showdata(w.datakey, force=True)
		super().closeEvent(ev)

# ---------------------------------------------------------------- a trade on the chart

def tradeinfo(t, tf):
	"""what tradepainter draws of strategy.Trade t, run in time frame tf"""
	at = t.at if t.at is not None else t.time
	exitat = t.exitat if t.exitat is not None else t.exittime
	return {"tf": tf, "dir": t.dir, "id": t.id, "at": int(at), "exitat": None if exitat is None else int(exitat),
		"price": t.price, "exitprice": t.exitprice, "sl": t.sl, "tp": t.tp, "points": t.points, "profit": t.profit,
		"exitid": t.exitid}

def tradeview(g, info):
	"""the part of the chart of g to show for trade info: (top, bot, t0, t1)"""
	top0, bot0, w0, w1 = g.whole
	te = g.tx(info["at"] / 1000)
	tx = g.tx(info["exitat"] / 1000) if info["exitat"] else te + 10 * g.cw
	tx = min(tx, w1)
	span = max(tx - te, 8 * g.cw)
	t0, t1 = max(w0, te - 2.5 * span), min(w1, tx + 1.5 * span)
	wall, o, h, l, c, zero = g.bars
	tt = (wall - zero) / g.unit
	m = (tt >= t0) & (tt <= t1)
	ps = [x for x in (info["price"], info["exitprice"], info["sl"], info["tp"]) if x is not None]
	his = ([float(h[m].max())] if m.any() else []) + ps
	los = ([float(l[m].min())] if m.any() else []) + ps
	hi, lo = (max(his), min(los)) if his else (top0, bot0)
	pad = (hi - lo) * 0.08 or 1
	return (hi + pad, lo - pad, t0, t1)

ZGREEN = QColor(8, 153, 129)
ZRED = QColor(242, 54, 69)

def tradepainter(info):
	"""fn(painter, geom) drawing trade info as a long or short position
	tool: the target zone over the stop zone from the entry, the entry
	line, and the path to the exit with its result"""
	from PySide6.QtGui import QFont, QFontMetricsF

	def fn(p, g):
		d = info["dir"]
		xs = g.X(g.tx(info["at"] / 1000))
		xe = g.X(g.tx(info["exitat"] / 1000)) if info["exitat"] else g.X(g.vt1)
		slot = g.cw / (g.t1 - g.t0) * g.pw
		xe = max(xe, xs + 3 * slot)
		ye = g.Y(info["price"])
		p.save()
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		f = QFont()
		f.setPixelSize(14)
		p.setFont(f)
		fm = QFontMetricsF(f)
		def zone(level, col):
			if level is None:
				return None
			y = g.Y(level)
			r = QRectF(xs, min(y, ye), xe - xs, abs(y - ye))
			fill = QColor(col)
			fill.setAlpha(80)
			p.fillRect(r, fill)
			edge = QColor(col)
			edge.setAlpha(160)
			p.setPen(QPen(edge, 1))
			p.drawLine(QPointF(xs, y), QPointF(xe, y))
			return y
		ytp = zone(info["tp"], ZGREEN)
		ysl = zone(info["sl"], ZRED)
		if ytp is None and ysl is None and info["exitprice"] is not None:	# no stop or target: entry to exit
			zone(info["exitprice"], ZGREEN if info["points"] > 0 else ZRED)
		p.setPen(QPen(QColor(90, 100, 115), 1.5))
		p.drawLine(QPointF(xs, ye), QPointF(xe, ye))
		def tag(text, x, y, col, above):
			w, h = fm.horizontalAdvance(text) + 10, fm.height() + 4
			r = QRectF(x - w / 2, (y - h - 3) if above else (y + 3), w, h)
			p.fillRect(r, col)
			p.setPen(QColor("white"))
			p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
		mid = (xs + xe) / 2
		if ytp is not None:
			tag(f"Target {info['tp']:.2f} ({(info['tp'] - info['price']) * d:+.2f})", mid, ytp, ZGREEN, ytp < ye)
		if ysl is not None:
			tag(f"Stop {info['sl']:.2f} ({(info['sl'] - info['price']) * d:+.2f})", mid, ysl, ZRED, ysl < ye)
		if info["exitprice"] is not None:
			yx = g.Y(info["exitprice"])
			col = ZGREEN if info["points"] > 0 else ZRED if info["points"] < 0 else QColor(120, 120, 120)
			pen = QPen(col, 1.6, Qt.PenStyle.DashLine)
			p.setPen(pen)
			p.drawLine(QPointF(xs, ye), QPointF(xe, yx))
			p.setPen(QPen(QColor("white"), 1.5))
			p.setBrush(col)
			p.drawEllipse(QPointF(xe, yx), 5, 5)
			p.setBrush(Qt.BrushStyle.NoBrush)
			text = f"{'Long' if d > 0 else 'Short'} {info['points']:+.2f} pts  {money(info['profit'])}"
			w = fm.horizontalAdvance(text) + 12
			x = min(xe + 8, g.L + g.pw - w)
			r = QRectF(x, yx - fm.height() / 2 - 2, w, fm.height() + 4)
			p.fillRect(r, col)
			p.setPen(QColor("white"))
			p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
		p.setPen(QPen(QColor("white"), 1.5))
		p.setBrush(QColor(37, 125, 224))
		p.drawEllipse(QPointF(xs, ye), 5, 5)
		p.restore()
	return fn

def money(v):
	return "—" if v != v else ("-" if v < 0 else "") + f"${abs(v):,.2f}"

def pct(x):
	return "—" if x != x else f"{x:.1%}"

def num(x):
	return "—" if x != x else ("∞" if x == float("inf") else f"{x:.2f}")

def fmtfig(key, v):
	if isinstance(v, int):
		return f"{v:,}"
	if key == "Win rate":
		return pct(v)
	if key in ("Profit factor", "Win / loss ratio", "Average bars in trade", "Net points"):
		return num(v)
	return money(v)

# ---------------------------------------------------------------- command line

USAGE = """usage: python3 backtest.py [options] journal strategy.txt
run a Pine strategy on the data of a journal (its folder) and print its figures
	-t min	time frame in minutes (5)
	-f date	first day (YYYY-MM-DD), -l date	last day
	-i name=value	set an input, by its title or its start (or key, group|title|inline)
	-I name=v1,v2,...	compare the values of an input (more -I: their combinations)
	-b kind	the figures by Year, Month, Weekday, Session or Hour (more -b: more tables)
	-c usd	commission a contract a side, -s ticks	slippage
	-o file.csv	export the trades (of the last run)
	-q	no per trade lines"""

def main(argv):
	import getopt
	from datetime import date
	import pine
	try:
		opts, args = getopt.getopt(argv, "t:f:l:i:I:b:c:s:o:q")
	except getopt.GetoptError as x:
		print(x, file=sys.stderr)
		print(USAGE, file=sys.stderr)
		return 2
	if len(args) != 2:
		print(USAGE, file=sys.stderr)
		return 2
	tf, first, last, sets, axes, bys, com, slip, out, quiet = 5, None, None, [], [], [], None, None, None, False
	for o, v in opts:
		if o == "-t":
			tf = int(v)
		elif o == "-f":
			first = date.fromisoformat(v)
		elif o == "-l":
			last = date.fromisoformat(v)
		elif o == "-i":
			sets.append(v.split("=", 1))
		elif o == "-I":
			axes.append(v.split("=", 1))
		elif o == "-b":
			k = [x for x in BYKINDS if x.lower() == v.lower()]
			if not k:
				print(f"-b {v}: one of {', '.join(BYKINDS)}", file=sys.stderr)
				return 2
			bys.append(k[0])
		elif o == "-c":
			com = float(v)
		elif o == "-s":
			slip = int(v)
		elif o == "-o":
			out = v
		elif o == "-q":
			quiet = True
	jdir, path = args
	data = m15.Data(jdir)
	lows = m15.lowtfs(jdir)
	low = m15.Data(jdir, lows[0]) if lows else None
	if not len(data):
		print(f"{jdir}: no m15 data", file=sys.stderr)
		return 1
	if tf not in tfs(data, low):
		print(f"-t {tf}: the data has {', '.join(map(str, tfs(data, low)))}", file=sys.stderr)
		return 1
	with open(path, encoding="utf-8", errors="replace") as f:
		script = pine.Script(f.read(), os.path.splitext(os.path.basename(path))[0])
	if script.error:
		print(f"{path}: {script.error}", file=sys.stderr)
		return 1
	try:
		specs = inputspecs(script, data, low, tf)
		inputs = {}
		for name, v in sets:
			i = findinput(specs, name)
			inputs[i.key] = parsevalue(i, v)
		ax = []
		for name, vs in axes:
			i = findinput(specs, name)
			ax.append((i.key, [parsevalue(i, x) for x in vs.split(",")]))
	except ValueError as x:
		print(x, file=sys.stderr)
		return 2
	titles = {i.key: i.title for i in specs}
	def show(c, rep):
		st = rep.stats()
		head = ", ".join(f"{titles.get(k, k)} = {v}" for k, v in c.items()) or (rep.title or "strategy")
		if rep.error and rep.broker is None:
			print(f"{head}: {rep.error}")
			return
		print(f"{head}: {st['Trades']} trades, net {money(st['Net profit'])} ({st['Net points']:,.2f} points, "
			f"{num(st['Net points'] / st['Trades']) if st['Trades'] else '—'} a trade), win rate {pct(st['Win rate'])}, "
			f"profit factor {num(st['Profit factor'])}, max drawdown {money(st['Max drawdown'])}"
			+ (f"; failed: {rep.error}" if rep.error else ""))
		for kind in bys:
			print(f"  by {kind.lower()}:")
			for lb, n, p, pts, w, pf in rep.by(kind):
				print(f"    {lb:>10} {n:6d} trades {money(p):>14} {pts:12,.2f} points {pct(w):>7} win  pf {num(pf)}")
	t0 = _time.time()
	res = compare(script, data, low, tf, ax, first, last, inputs, None, None, com, slip,
		each=lambda k, n, c, rep: show(c, rep))
	if not quiet and len(res) == 1:
		for t in res[0][1].trades:
			print(f"  {fmttime(t.time)} {'long ' if t.dir > 0 else 'short'} {t.price:10.2f} -> "
				f"{'' if t.exitprice is None else f'{t.exitprice:.2f}':>10} {t.points:+9.2f} {t.exitid or 'open'}")
	if out and res:
		res[-1][1].tocsv(out)
	print(f"{len(res)} run(s) in {_time.time() - t0:.1f} s")
	return 0

if __name__ == "__main__":
	sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
	os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
	sys.exit(main(sys.argv[1:]))
