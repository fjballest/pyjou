#
# headless tests: python3 tests/test_strategy.py
# Pine strategies: the broker's fills (pine/strategy.py) and the backtests
# of the journal's data (backtest.py).
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
from datetime import datetime, timezone

import numpy as np

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

import pine
from pine import runtime as R

def candles(rows, tf=5):
	"""a Series of rows [(o, h, l, c)] of tf minutes from Monday 2 Nov 2026 14:30 UTC"""
	t0 = int(datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc).timestamp())
	a = np.array(rows, dtype=float)
	t = np.arange(len(a)) * tf * 60 + t0
	return R.Series(t * 1000, a[:, 0], a[:, 1], a[:, 2], a[:, 3], (t + tf * 60) * 1000, str(tf))

def run(src, rows, symbol="MNQ"):
	r = pine.run(pine.Script(src, "test"), candles(rows), lambda k: None, symbol=symbol)
	if r.error:
		print(r.error, getattr(r, "trace", ""))
	return r

FLAT = (100, 101, 99, 100)
HEAD = '//@version=6\nstrategy("T", overlay = true, process_orders_on_close = true, pyramiding = 0)\n'

# a long at the close of bar 1, its take profit hit on bar 3
src = HEAD + '''if bar_index == 1
    strategy.entry("Long", strategy.long)
    strategy.exit("Long exit", "Long", stop = 98, limit = 105)
plot(strategy.position_size, "size")
'''
r = run(src, [FLAT, FLAT, (100, 103, 99, 102), (102, 106, 101, 104), FLAT])
b = r.strategy
check(b is not None and len(b.trades) == 1, "a strategy's run has its broker and trades")
t = b.trades[0]
check((t.dir, t.price, t.bar, t.exitprice, t.exitbar, t.exitid) == (1, 100, 1, 105, 3, "Long exit"),
	"filled at the close of the signal candle, out at the limit")
check(t.points == 5 and t.profit == 10, "5 points, $10 on MNQ")
check((t.sl, t.tp) == (98, 105), "its stop and target kept")
check(t.at is not None and t.exitat is not None and t.at < t.exitat, "its fill times (ms)")
size = [v for _, (v, a, k) in sorted(list(r.plots.values())[0][1].items())]
check(size == [0, 0, 1, 0, 0], "strategy.position_size as the script sees it (filled after the signal bar ran): " + str(size))

# the stop, on a candle that opens past it: filled at the open
r = run(src, [FLAT, FLAT, (97, 99, 96, 98), FLAT])
t = r.strategy.trades[0]
check((t.exitprice, t.exitbar) == (97, 2), "a gap through the stop fills at the open")

# both in one candle: open nearer the low goes to the low first
r = run(src, [FLAT, FLAT, (99, 106, 97, 104), FLAT])
check(r.strategy.trades[0].exitprice == 98, "open nearer the low: the stop first")
r = run(src, [FLAT, FLAT, (103, 106, 97, 104), FLAT])
check(r.strategy.trades[0].exitprice == 105, "open nearer the high: the limit first")

# an opposite entry reverses; a same one is ignored
src = HEAD + '''if bar_index == 1 or bar_index == 2
    strategy.entry("Long", strategy.long)
if bar_index == 3
    strategy.entry("Short", strategy.short)
    strategy.exit("Short exit", "Short", stop = 110, limit = 95)
'''
r = run(src, [FLAT, FLAT, (100, 101, 99, 101), (101, 102, 100, 102), (102, 102, 94, 96), FLAT])
tr = r.strategy.trades
check(len(tr) == 2 and tr[0].exitbar == 3 and tr[0].exitprice == 102 and tr[0].points == 2,
	"an entry in the same direction is ignored; the opposite closes it")
check(tr[1].dir == -1 and tr[1].price == 102 and tr[1].exitprice == 95 and tr[1].exitbar == 4, "and opens the other way")

# without process_orders_on_close, market orders fill at the next open
src = '//@version=6\nstrategy("T")\nif bar_index == 1\n    strategy.entry("L", strategy.long)\nif bar_index == 3\n    strategy.close("L")\n'
r = run(src, [FLAT, FLAT, (100.5, 102, 100, 101), FLAT, (103, 104, 102, 103)])
t = r.strategy.trades[0]
check((t.price, t.bar, t.exitprice, t.exitbar) == (100.5, 2, 103, 4), "or else at the next open; strategy.close")

# stop and limit entries, exits in ticks, commission
src = ('//@version=6\nstrategy("T", commission_type = strategy.commission.cash_per_contract, commission_value = 0.5)\n'
	'if bar_index == 1\n    strategy.entry("B", strategy.long, stop = 103)\n'
	'strategy.exit("X", "B", profit = 8, loss = 20)\n')
r = run(src, [FLAT, FLAT, (101, 104, 100, 103.5), (103.5, 105.5, 103, 105), FLAT])
t = r.strategy.trades[0]
check((t.price, t.bar, t.exitprice, t.exitbar) == (103, 2, 105, 3), "a stop entry, then its exit 8 ticks up")
check(abs(t.profit - (2 * 2 - 1)) < 1e-9, "less $0.50 a side")
check((t.sl, t.tp) == (98, 105), "stop and target in ticks, as prices: " + str((t.sl, t.tp)))

# a plain indicator has no strategy
r = run('//@version=6\nindicator("I")\nplot(close)\n', [FLAT, FLAT])
check(r.strategy is None, "indicators have no broker")

# ICTScalp strategy compiles and runs, if its source is here
p = os.environ.get("ICTSCALP")
if p and os.path.exists(p):
	rng = np.random.default_rng(2)
	px = 20000 + np.cumsum(rng.normal(0, 5, 3000))
	rows = [(a, max(a, b) + 2, min(a, b) - 2, b) for a, b in zip(px[:-1], px[1:])]
	r = run(open(p).read(), rows)
	check(r.error is None and r.strategy is not None, f"ICTScalp: {len(r.strategy.trades)} trades")

# a backtest of the journal's data, from View ▸ Strategy Tester
from datetime import date
import m15
j, src = tempfile.mkdtemp(), tempfile.mkdtemp()
rng = np.random.default_rng(5)
d0 = m15.Data.dayn(date(2026, 6, 1))
p = 20000.0
with open(os.path.join(src, "MNQ.m1.csv"), "w") as f:
	f.write("time,open,high,low,close\n")
	for day in range(70):
		if day % 7 in (5, 6):
			continue
		t0 = int(m15.daystart([d0 + day])[0])
		for k in range(1380):
			o = p
			p = round((p + rng.normal(0, 3)) * 4) / 4
			f.write("%d,%g,%g,%g,%g\n" % (t0 + k * 60, o, max(o, p) + 0.5, min(o, p) - 0.5, p))
m15.importfile(j, os.path.join(src, "MNQ.m1.csv"))
data = m15.Data(j)
low = m15.Data(j, m15.lowtfs(j)[0])
import backtest
cross = """//@version=6
strategy("Cross", overlay = true, process_orders_on_close = true)
f = ta.sma(close, 10)
s = ta.sma(close, 30)
if ta.crossover(f, s)
    strategy.entry("L", strategy.long)
if ta.crossunder(f, s)
    strategy.entry("S", strategy.short)
strategy.exit("LX", "L", loss = 40, profit = 80)
strategy.exit("SX", "S", loss = 40, profit = 80)
"""
rep = backtest.backtest(pine.Script(cross, "Cross"), data, low, 5)
st = rep.stats()
check(rep.error is None and st["Trades"] > 50, f"a backtest on m5 of all the data: {st['Trades']} trades")
check(abs(st["Net profit"] - sum(t.profit for t in rep.trades if not t.open)) < 1e-6 and
	st["Winning trades"] + st["Losing trades"] <= st["Trades"], "its figures")
check(len(rep.equity) == rep.chart.n and abs(rep.equity[-1] - st["Net profit"] - rep.broker.openprofit(float(rep.chart.c[-1]))) < 1e-6,
	"the equity, every candle")
check(st["Max drawdown"] >= 0 and all(t.exitprice is not None for t in rep.trades if not t.open), "max drawdown")
long_, short = rep.stats("long"), rep.stats("short")
check(long_["Trades"] + short["Trades"] == st["Trades"], "longs and shorts")
part = backtest.backtest(pine.Script(cross, "Cross"), data, low, 5, first=date(2026, 7, 20))
check(part.trades and all(t.time >= int(m15.daystart([data.dayn(date(2026, 7, 20))])[0]) * 1000 for t in part.trades)
	and part.k0 > 0, "a range: started 5000 candles before, its trades only")
mon = {data.dayn(d) for d in data.days() if d.weekday() == 0}
only = backtest.backtest(pine.Script(cross, "Cross"), data, low, 5, only=mon)
check(only.trades and len(only.trades) < len(rep.trades) and all(backtest.nytime(t.time).weekday() in (0, 6) for t in only.trades)
	and abs(only.equity[-1] - only.stats()["Net profit"]) < 1e-6, "only the trades of some days")
com = backtest.backtest(pine.Script(cross, "Cross"), data, low, 5, commission=1)
check(abs(com.stats()["Net profit"] - (st["Net profit"] - 2 * st["Trades"])) < 1e-6, "with commission")
ev = __import__("threading").Event()
ev.set()
half = backtest.backtest(pine.Script(cross, "Cross"), data, low, 5, stop=ev)
check(half.cancelled, "stopped")
check(backtest.backtest(pine.Script('//@version=6\nindicator("I")\nplot(close)', "I"), data, low, 15).error,
	"an indicator is not tested")
csvp = os.path.join(src, "t.csv")
rep.tocsv(csvp)
check(len(open(csvp).read().splitlines()) == len(rep.trades) + 1, "trades exported")
by = {k: rep.by(k) for k in backtest.BYKINDS}
closed = [t for t in rep.trades if not t.open]
check(all(sum(r[1] for r in rows) == len(closed) for rows in by.values()) and
	all(abs(sum(r[3] for r in rows) - st["Net points"]) < 1e-6 for rows in by.values()), "the trades by period add up")
check([r[0] for r in by["Year"]] == ["2026"] and len(by["Month"]) >= 2 and by["Month"][0][0] < by["Month"][-1][0],
	"by year and month: " + ", ".join(r[0] for r in by["Month"]))
check({r[0] for r in by["Weekday"]} <= set(backtest.WEEKDAYS[:5] + ["Sunday"])
	and {r[0] for r in by["Session"]} <= {"Asia", "London", "NY AM", "NY PM", "Other"}, "by weekday and killzone")
check(backtest.periodof(datetime(2026, 7, 1, 11, 29), "Session") == 2 and
	backtest.periodof(datetime(2026, 7, 1, 11, 30), "Session") == 4, "NY AM ends at 11:30")
xsrc = cross.replace("f = ta.sma(close, 10)", 'n = input.int(10, "Fast")\nlossIn = input.float(40, "Loss")\n'
	'f = ta.sma(close, n)').replace("loss = 40", "loss = lossIn")
xs = pine.Script(xsrc, "CrossIn")
specs = backtest.inputspecs(xs, data, low, 5)
fast = backtest.findinput(specs, "Fast")
check(fast.kind == "int" and backtest.parsevalue(fast, " 7 ") == 7, "an input found by its title, its value parsed")
loss = backtest.findinput(specs, "Loss")
cmp = backtest.compare(xs, data, low, 5, [(fast.key, [10, 20]), (loss.key, [40.0, 60.0])])
check([tuple(c.values()) for c, _ in cmp] == [(10, 40.0), (10, 60.0), (20, 40.0), (20, 60.0)], "compared: every combination")
check(abs(cmp[0][1].stats()["Net profit"] - st["Net profit"]) < 1e-6 and
	cmp[0][1].stats()["Trades"] > cmp[2][1].stats()["Trades"], "the defaults as without inputs, a slower average fewer trades")
try:
	backtest.parsevalue(fast, "x")
	check(False, "a wrong value")
except ValueError:
	check(True, "a wrong value is refused")
import contextlib, io
xp = os.path.join(src, "CrossIn.txt")
with open(xp, "w") as f:
	f.write(xsrc)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
	rc = backtest.main(["-t", "5", "-I", "Fast=10,20", "-b", "year", "-q", j, xp])
outp = buf.getvalue()
check(rc == 0 and outp.count(" trades, net ") == 2 and "Fast = 20" in outp and "by year:" in outp and "2 run(s)" in outp,
	"the command line: " + outp.splitlines()[0][:80])
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
	check(backtest.main(["-I", "Nope=1", j, xp]) == 2, "the command line: an unknown input")

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
import mainwin
import indicators
import ocrworker
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])
with open(os.path.join(src, "Cross.txt"), "w") as f:
	f.write(cross)
win = mainwin.MainWindow(j)
win.show()
indicators.importfiles([os.path.join(src, "Cross.txt")])
win.testeract.trigger()
app.processEvents()
tw = win.testerwin
check(tw.isVisible() and tw.strategy.currentText() == "Cross" and tw.tf.findData(5) >= 0, "View ▸ Strategy Tester lists the strategies")
tw.tf.setCurrentIndex(tw.tf.findData(5))
tw.run(wait=True)
app.processEvents()
check(tw.rep is not None and tw.table.rowCount() == len(tw.rep.trades) and "trades, net " in tw.status.text(),
	"run in the background, its report: " + tw.status.text()[:90])
check(tw.figures.rowCount() > 10 and tw.hours.rowCount() > 0, "figures, by hour")
check(tw.periods.rowCount() == 1 and tw.periods.item(0, 0).text() == "2026", "by period: the year")
tw.bykind.setCurrentText("Session")
check(tw.periods.rowCount() >= 1 and tw.periods.item(0, 0).text() in ("Asia", "London", "NY AM", "NY PM", "Other"),
	"by period: the killzones")
img = tw.grab()
img.save(os.path.join(os.environ.get("SHOTS", src), "tester.png"))
tw.tabs.setCurrentIndex(1)
tw.table.cellClicked.emit(0, 0)
app.processEvents()
check(win.datamode and win.datakey[0] == "d", "a trade's day shown")
t0 = tw.rep.trades[0]
check(t0.at is not None and t0.exitat is not None and t0.at <= t0.exitat, "fill times kept")
check(getattr(win, "datashowntf", win.datatf) == 5 and win.datatf == 5, "in the time frame of the test")
dn = int(m15.daynos(np.array([t0.at // 1000]))[0])
check(win.datakey[1] == m15.Data.daydate(dn), "on the day of its entry")
g = win.datageom
check(g.view() is not None and g.t0 <= g.tx(t0.at / 1000) <= g.vt1 and g.t0 <= g.tx(t0.exitat / 1000) <= g.vt1,
	"zoomed on the trade")
check(g.bot <= t0.price <= g.top and g.bot <= t0.exitprice <= g.top, "with its prices")
check(win.tradeshown is not None and win.tradeshown["at"] == t0.at, "drawn as a position")
win.grab().save(os.path.join(os.environ.get("SHOTS", src), "trade.png"))
from PySide6.QtGui import QImage, QPainter
im = QImage(g.W, g.H, QImage.Format.Format_ARGB32)
im.fill(0)
p = QPainter(im)
backtest.tradepainter(dict(win.tradeshown, sl=t0.price - 20, tp=t0.price + 40))(p, g)
p.end()
check(im.pixelColor(int(g.X(g.tx(t0.at / 1000))) + 2, int(g.Y(t0.price + 20))).alpha() > 0, "a target zone")
indicators.importfiles([xp])
tw.fill()
tw.strategy.setCurrentIndex(tw.strategy.findText("CrossIn"))
tw.tabs.setCurrentIndex(tw.tabs.count() - 1)
app.processEvents()
check(tw.tabs.tabText(tw.tabs.currentIndex()) == "Compare" and tw.cmpin[0].findText("Fast") >= 0
	and tw.cmpin[1].itemText(0) == "—", "Compare lists the strategy's inputs")
tw.cmpin[0].setCurrentIndex(tw.cmpin[0].findText("Fast"))
tw.cmpvals[0].setText("10, 20, 30")
tw.compare_(wait=True)
app.processEvents()
check(tw.cmptable.rowCount() == 3 and tw.cmptable.item(2, 0).text() == "30" and "Compared 3 runs" in tw.status.text()
	and tw.cmptable.horizontalHeaderItem(tw.cmptable.columnCount() - 1).text() == "2026", "compared, net points by year")
tw.grab().save(os.path.join(os.environ.get("SHOTS", src), "compare.png"))
tw.showcompared(1)
check(tw.rep is tw.cmpruns[1][1] and tw.table.rowCount() == len(tw.rep.trades), "a run compared shown in the tabs")
tw.cmpvals[0].setText("x")
tw.compare_()
check("Compare:" in tw.status.text() and tw.thread is None, "a wrong value said")
tw.close()
app.processEvents()
check(win.tradeshown is None, "the trade goes with the tester")
seen = []
tw.settings(accept=lambda dlg: seen.append(dlg) or 0)
check(seen, "the strategy's settings")
print("ALL OK")
os._exit(0)
