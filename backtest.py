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

	def tocsv(self, path):
		with open(path, "w", newline="") as f:
			w = csv.writer(f)
			w.writerow(["Trade", "Type", "Signal", "Entry time (New York)", "Entry price", "Exit signal",
				"Exit time (New York)", "Exit price", "Contracts", "Points", "Profit", "Run-up (points)", "Drawdown (points)"])
			for k, t in enumerate(self.trades, 1):
				w.writerow([k, "Long" if t.dir > 0 else "Short", t.id, fmttime(t.time), t.price,
					t.exitid or "Open", fmttime(t.exittime) if t.exittime else "", "" if t.exitprice is None else t.exitprice,
					t.qty, round(t.points, 4), round(t.profit, 2), round(t.runup(), 4), round(t.drawdown(), 4)])

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
	QMessageBox, QProgressBar, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QToolTip,
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
			p.drawText(QRectF(x - 40, r.bottom() + 6, 80, 16), Qt.AlignmentFlag.AlignCenter, lab)
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
		QToolTip.showText(ev.globalPosition().toPoint(), f"{fmttime(rep.etimes[i])}\nnet profit: ${rep.equity[i]:,.2f}", self)
		self.update()

	def leaveEvent(self, ev):
		self.at = None
		self.update()

class _Signals(QObject):
	progress = Signal(int, int)
	done = Signal(object)

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
		self.table.cellDoubleClicked.connect(self.showtrade)
		self.tabs.addTab(self.table, "List of Trades")
		self.hours = QTableWidget(0, 4)
		self.hours.setHorizontalHeaderLabels(["Entry hour (New York)", "Trades", "Net profit", "Win rate"])
		self.hours.verticalHeader().hide()
		self.hours.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
		self.hours.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
		self.tabs.addTab(self.hours, "By Hour")
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
			msg = (f"{st['Trades']} trades, net ${st['Net profit']:,.2f} ({st['Net points']:,.2f} points), "
				f"win rate {pct(st['Win rate'])}, profit factor {num(pf)}, max drawdown ${st['Max drawdown']:,.2f}. "
				f"{rep.chart.n - rep.k0:,} candles in {rep.seconds:.0f} s.")
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
		hrs = rep.byhour()
		self.hours.setRowCount(len(hrs))
		for k, (h, n, p, w) in enumerate(hrs):
			for j, v in enumerate([f"{h:02d}:00", str(n), f"${p:,.2f}", pct(w)]):
				self.hours.setItem(k, j, QTableWidgetItem(v))

	def showtrade(self, row, _col):
		if self.rep is None or row >= len(self.rep.trades):
			return
		t = self.rep.trades[row]
		d = m15.Data.daydate(int(m15.daynos(np.array([t.time // 1000]))[0]))
		w = self.win
		if not getattr(w, "datamode", False) and hasattr(w, "setdatamode"):
			w.setdatamode(True)
		if getattr(w, "datamode", False):
			w.showdata(("d", d))
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
		super().closeEvent(ev)

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
	return "—" if v != v else f"${v:,.2f}"
