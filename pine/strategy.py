"""The broker of Pine strategies, as TradingView's broker emulator: the
orders a strategy places (strategy.entry, exit, close...) filled on the
candles, and the trades they made.

Market orders fill at the close of the candle they are placed on when
the strategy says process_orders_on_close, or else at the open of the
next one. Stop and limit orders (of entries and exits) fill on the next
candles, as the price goes through them: from the open to the nearest of
the high and the low, to the other, and to the close (TradingView's
assumption); a candle opening past one fills it at the open."""

import math

import numpy as np

from . import runtime as R

LONG, SHORT = "long", "short"

def _na(x):
	return x is None or R.isna(x)

class Trade:
	"""a position opened by entry id: dir +1 or -1, qty contracts at price,
	on bar (and time, ms); once closed, the exit's id, price, bar, time, and
	its profit (in points of a contract, and in money net of commission)"""
	def __init__(self, id, dir, qty, price, bar, time, comment=""):
		self.id, self.dir, self.qty, self.price, self.bar, self.time = id, dir, qty, price, bar, time
		self.comment = comment
		self.exitid = self.exitprice = self.exitbar = self.exittime = None
		self.points = self.profit = 0.0
		self.commission = 0.0
		self.best = self.worst = price	# the most favourable and adverse prices while open

	@property
	def open(self):
		return self.exitbar is None

	def runup(self):
		return (self.best - self.price) * self.dir + 0.0	# no -0.0

	def drawdown(self):
		return (self.price - self.worst) * self.dir + 0.0

class Order:
	"""an entry order: dir, qty, limit and stop (na: none, a market order)"""
	def __init__(self, id, dir, qty, limit, stop, comment, bar):
		self.id, self.dir, self.qty, self.limit, self.stop, self.comment, self.bar = id, dir, qty, limit, stop, comment, bar
		self.armed = _na(stop)	# a stop limit entry becomes a limit one once its stop is hit

	@property
	def market(self):
		return _na(self.limit) and _na(self.stop)

class Exit:
	"""an exit order of the trades of entry frm: a stop and a limit (or
	none of one), as prices; armed once there is a trade of frm"""
	def __init__(self, id, frm, limit, stop, comment):
		self.id, self.frm, self.limit, self.stop, self.comment = id, frm, limit, stop, comment
		self.armed = False

class Broker:
	def __init__(self):
		self.on = False	# a strategy declared it
		self.closefill = False	# process_orders_on_close
		self.pyramiding = 1
		self.qtytype, self.qtyvalue = "fixed", 1.0
		self.capital = 1000000.0
		self.comtype, self.comvalue = "cash_per_contract", 0.0
		self.slippage = 0	# ticks
		self.pointvalue = 1.0
		self.mintick = 0.25
		self.trades = []	# [Trade], open and closed, in order
		self.open = []		# those open
		self.closedsum = 0.0	# the profit of those closed
		self.nwins = self.nlosses = 0
		self.won = self.lost = 0.0
		self.entries = {}	# {id: Order} pending
		self.exits = {}		# {id: Exit}
		self.closes = []	# [(entry id or None for all, comment)] market closes pending
		self.closedeq = self.openeq = None	# numpy arrays: the closed and open profit at each bar's close
		self.S = None
		self.hook = None	# called with the broker once declared: to change its settings
		self.lastbar = -1	# the last bar run

	def declare(self, k):
		self.on = True
		self.closefill = bool(k.get("process_orders_on_close", False))
		p = k.get("pyramiding", 0)
		self.pyramiding = max(1, int(p)) if not _na(p) else 1
		self.qtytype = k.get("default_qty_type", "fixed")
		v = k.get("default_qty_value", 1)
		self.qtyvalue = 1.0 if _na(v) else float(v)
		c = k.get("initial_capital", 1000000)
		self.capital = 1000000.0 if _na(c) else float(c)
		self.comtype = k.get("commission_type", "percent")
		v = k.get("commission_value", 0)
		self.comvalue = 0.0 if _na(v) else float(v)
		s = k.get("slippage", 0)
		self.slippage = 0 if _na(s) else int(s)
		if self.hook is not None:
			self.hook(self)

	# ------------------------------------------------------------ the state

	def opentrades(self):
		return list(self.open)

	def closedtrades(self):
		return [t for t in self.trades if not t.open]

	@property
	def size(self):
		return sum(t.dir * t.qty for t in self.open)

	@property
	def avgprice(self):
		o = self.open
		q = sum(t.qty for t in o)
		return sum(t.price * t.qty for t in o) / q if q else R.na

	def netprofit(self):
		return self.closedsum

	def openprofit(self, price=None):
		if price is None:
			price = self.S.c[R.RT.bar] if self.S is not None and self.S.n else 0
		return sum((price - t.price) * t.dir * t.qty * self.pointvalue for t in self.open)

	@property
	def equityvalue(self):
		return self.capital + self.netprofit() + self.openprofit()

	def wins(self):
		return self.nwins

	def losses(self):
		return self.nlosses

	def grossprofit(self):
		return self.won

	def grossloss(self):
		return self.lost

	# ------------------------------------------------------------ the orders

	def qty(self, q, price):
		if not _na(q):
			return float(q)
		if self.qtytype == "cash":
			return max(1.0, math.floor(self.qtyvalue / (price * self.pointvalue)))
		if self.qtytype == "percent":
			return max(1.0, math.floor(self.equityvalue * self.qtyvalue / 100 / (price * self.pointvalue)))
		return self.qtyvalue

	def entry(self, id, direction, qty=R.na, limit=R.na, stop=R.na, oca_name=None, oca_type=None, comment="",
			alert_message=None, disable_alert=False, **_k):
		d = 1 if direction == LONG else -1
		self.entries[id] = Order(id, d, qty, limit, stop, "" if _na(comment) else comment, R.RT.bar)
		return R.na

	def order(self, id, direction, qty=R.na, limit=R.na, stop=R.na, comment="", **_k):
		return self.entry(id, direction, qty, limit, stop, comment=comment)

	def exit(self, id, from_entry="", qty=R.na, qty_percent=R.na, profit=R.na, limit=R.na, loss=R.na, stop=R.na,
			trail_price=R.na, trail_points=R.na, trail_offset=R.na, oca_name=None, comment="", **_k):
		frm = "" if _na(from_entry) else from_entry
		old = self.exits.get(id)
		e = Exit(id, frm, limit, stop, "" if _na(comment) else comment)
		e.profit, e.loss = profit, loss	# in ticks from the entry price
		e.armed = any(not frm or t.id == frm for t in self.open) or (old is not None and old.armed)
		self.exits[id] = e
		return R.na

	def close(self, id, comment="", qty=R.na, qty_percent=R.na, immediately=False, **_k):
		self.closes.append((id, "" if _na(comment) else comment))
		if immediately:
			self.marketcloses(self.S.c[R.RT.bar], R.RT.bar)
		return R.na

	def close_all(self, comment="", immediately=False, **_k):
		return self.close(None, comment, immediately=immediately)

	def cancel(self, id):
		self.entries.pop(id, None)
		self.exits.pop(id, None)
		return R.na

	def cancel_all(self):
		self.entries.clear()
		self.exits.clear()
		return R.na

	# ------------------------------------------------------------ the fills

	def commission(self, qty, price):
		if self.comtype == "percent":
			return qty * price * self.pointvalue * self.comvalue / 100
		if self.comtype == "cash_per_order":
			return self.comvalue
		return qty * self.comvalue

	def slip(self, price, dir):
		return price + dir * self.slippage * self.mintick

	def openat(self, o, price, bar):
		"""fill entry order o at price: it closes the opposite trades first"""
		price = self.slip(price, o.dir)
		size = self.size
		if size and (size > 0) != (o.dir > 0):
			for t in self.opentrades():
				self.closetrade(t, price, bar, o.id, reverse=True)
		elif size and len(self.opentrades()) >= self.pyramiding:
			return False
		q = self.qty(o.qty, price)
		t = Trade(o.id, o.dir, q, price, bar, int(self.S.t[bar]), o.comment)
		t.commission = self.commission(q, price)
		self.trades.append(t)
		self.open.append(t)
		for e in self.exits.values():
			if not e.frm or e.frm == o.id:
				e.armed = True
		return True

	def closetrade(self, t, price, bar, exitid, reverse=False):
		if not reverse:
			price = self.slip(price, -t.dir)
		t.exitid, t.exitprice, t.exitbar, t.exittime = exitid, price, bar, int(self.S.t[bar])
		t.points = (price - t.price) * t.dir
		t.commission += self.commission(t.qty, price)
		t.profit = t.points * t.qty * self.pointvalue - t.commission
		t.best = max(t.best, price) if t.dir > 0 else min(t.best, price)
		t.worst = min(t.worst, price) if t.dir > 0 else max(t.worst, price)
		self.open.remove(t)
		self.closedsum += t.profit
		if t.profit > 0:
			self.nwins += 1
			self.won += t.profit
		elif t.profit < 0:
			self.nlosses += 1
			self.lost -= t.profit
		if not any(x.id == t.id for x in self.open):
			for k in [k for k, e in self.exits.items() if e.armed and (e.frm == t.id or not e.frm)]:
				if not e_open(self, self.exits[k]):
					del self.exits[k]

	def marketcloses(self, price, bar):
		for id, comment in self.closes:
			for t in self.opentrades():
				if id is None or t.id == id:
					self.closetrade(t, price, bar, "Close" if id is None else "Close entry(s) order " + id)
		self.closes = []

	def market(self, price, bar):
		"""fill the market orders at price"""
		self.marketcloses(price, bar)
		for id in [k for k, o in self.entries.items() if o.market]:
			o = self.entries.pop(id)
			self.openat(o, price, bar)

	def levels(self, e):
		"""[(price, kind, trade)] where exit e fills the trades it is for"""
		out = []
		for t in self.opentrades():
			if e.frm and t.id != e.frm:
				continue
			stop, limit = e.stop, e.limit
			if _na(stop) and not _na(getattr(e, "loss", R.na)):
				stop = t.price - t.dir * e.loss * self.mintick
			if _na(limit) and not _na(getattr(e, "profit", R.na)):
				limit = t.price + t.dir * e.profit * self.mintick
			if not _na(stop):
				out.append((float(stop), "stop", t))
			if not _na(limit):
				out.append((float(limit), "limit", t))
		return out

	def triggers(self, a, b):
		"""the orders that fill as the price goes from a to b:
		[(distance from a, fill price, what)]"""
		up = b >= a
		out = []
		for o in self.entries.values():
			if o.market:
				continue
			if not o.armed:
				s = float(o.stop)
				if (o.dir > 0 and up and a <= s <= b) or (o.dir < 0 and not up and b <= s <= a):
					out.append((abs(s - a), s, ("arm", o)))
				continue
			if not _na(o.limit):
				x = float(o.limit)
				if (o.dir > 0 and not up and b <= x <= a) or (o.dir < 0 and up and a <= x <= b):
					out.append((abs(x - a), x, ("entry", o)))
			elif not _na(o.stop):
				x = float(o.stop)
				if (o.dir > 0 and up and a <= x <= b) or (o.dir < 0 and not up and b <= x <= a):
					out.append((abs(x - a), x, ("entry", o)))
		for e in self.exits.values():
			if not e.armed:
				continue
			for x, kind, t in self.levels(e):
				# a long's stop and a short's limit fill going down, the others going up
				down = (t.dir > 0) == (kind == "stop")
				if (down and not up and b <= x <= a) or (not down and up and a <= x <= b):
					out.append((abs(x - a), x, ("exit", e, t)))
		return sorted(out, key=lambda z: z[0])

	def gaps(self, o, bar):
		"""fill what the open of bar is already past"""
		for e in list(self.exits.values()):
			if not e.armed:
				continue
			for x, kind, t in self.levels(e):
				if not t.open:
					continue
				down = (t.dir > 0) == (kind == "stop")
				if (down and o <= x) or (not down and o >= x):
					self.closetrade(t, o, bar, e.id)
		for id in list(self.entries):
			e = self.entries.get(id)
			if e is None or e.market or not e.armed:
				continue
			if not _na(e.limit):
				x = float(e.limit)
				if (e.dir > 0 and o <= x) or (e.dir < 0 and o >= x):
					del self.entries[id]
					self.openat(e, o, bar)
			elif not _na(e.stop):
				x = float(e.stop)
				if (e.dir > 0 and o >= x) or (e.dir < 0 and o <= x):
					del self.entries[id]
					self.openat(e, o, bar)

	def candle(self, bar):
		"""fill the orders placed before bar as the price goes through it"""
		S = self.S
		o, h, l, c = float(S.o[bar]), float(S.h[bar]), float(S.l[bar]), float(S.c[bar])
		if not self.closefill:
			self.market(o, bar)
		self.gaps(o, bar)
		path = [o, h, l, c] if h - o <= o - l else [o, l, h, c]
		for a, b in zip(path, path[1:]):
			for _ in range(100):	# a fill may arm other orders on the way
				hits = self.triggers(a, b)
				if not hits:
					break
				_, x, what = hits[0]
				if what[0] == "arm":
					what[1].armed = True
				elif what[0] == "entry":
					self.entries.pop(what[1].id, None)
					self.openat(what[1], x, bar)
				else:
					e, t = what[1], what[2]
					if t.open:
						self.closetrade(t, x, bar, e.id)
				a = x
		for t in self.opentrades():
			if t.dir > 0:
				t.best, t.worst = max(t.best, h), min(t.worst, l)
			else:
				t.best, t.worst = min(t.best, l), max(t.worst, h)

	def before(self, bar):
		if self.on and bar > 0:
			self.candle(bar)

	def after(self, bar):
		if not self.on:
			return
		if self.closefill:
			self.market(float(self.S.c[bar]), bar)
		self.lastbar = bar
		if self.closedeq is None:
			self.closedeq = np.zeros(self.S.n)
			self.openeq = np.zeros(self.S.n)
		self.closedeq[bar] = self.closedsum
		self.openeq[bar] = self.openprofit(float(self.S.c[bar])) if self.open else 0.0

def e_open(b, e):
	"""whether exit e still has trades to close"""
	return any(not e.frm or t.id == e.frm for t in b.open)

def _st():
	return R.RT.st

def builtins():
	"""{Pine name: function} of the strategy calls, and {name: expression}
	of its variables"""
	F = {}
	for name in ("entry", "exit", "close", "close_all", "cancel", "cancel_all", "order"):
		F["strategy." + name] = (lambda name: lambda *a, **k: getattr(R.RT.st, name)(*a, **k))(name)
	D = {
		"strategy.position_size": "_RT.st.size", "strategy.position_avg_price": "_RT.st.avgprice",
		"strategy.equity": "_RT.st.equityvalue", "strategy.netprofit": "_RT.st.netprofit()",
		"strategy.openprofit": "_RT.st.openprofit()", "strategy.initial_capital": "_RT.st.capital",
		"strategy.opentrades": "len(_RT.st.opentrades())", "strategy.closedtrades": "len(_RT.st.closedtrades())",
		"strategy.wintrades": "_RT.st.wins()", "strategy.losstrades": "_RT.st.losses()",
		"strategy.grossprofit": "_RT.st.grossprofit()", "strategy.grossloss": "_RT.st.grossloss()",
		"strategy.position_entry_name": "(_RT.st.opentrades()[-1].id if _RT.st.opentrades() else '')",
	}
	return F, D
