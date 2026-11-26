"""Pine indicators on frozen candles: a script is compiled to Python once
and run bar by bar up to the last candle shown, as if that one were the
last; what it draws is kept in a Result (see draw.py).

Only the part of Pine v6 the journal's indicators use is supported."""

import bisect
import hashlib
import time as _time
import traceback

from . import runtime as R
from .compile import compile_script, namespace
from .parse import PineError

NBARS = 5000	# the chart bars a script runs on, as TradingView keeps

class Script:
	"""a compiled Pine script; error is why it could not be compiled"""
	_cache = {}

	def __init__(self, src, name="script"):
		self.src = src
		self.name = name
		self.error = None
		self.code = None
		self.title = name
		key = hashlib.sha1(src.encode()).hexdigest()
		hit = Script._cache.get(key)
		try:
			if hit is None:
				hit = compile_script(src, name)
				Script._cache[key] = hit
			self.py, self.code, self.consts, self.lines = hit
		except PineError as x:
			self.error = str(x)
		except RecursionError:
			self.error = "too deeply nested"
		import re
		m = re.search(r'indicator\s*\(\s*(?:title\s*=\s*)?"([^"]*)"', src)
		if m:
			self.title = m.group(1)

class Result:
	"""what a run drew: lines, labels, boxes, tables, linefills (alive ones),
	plots {site: (kind, {bar: (value, args, kwargs)}, title)}, the chart
	bars S, and error, a message when the run stopped"""
	def __init__(self):
		self.lines = []
		self.labels = []
		self.boxes = []
		self.tables = []
		self.linefills = []
		self.plots = {}
		self.S = None
		self.error = None
		self.seconds = 0
		self.title = ""

def run(script, chart, sources, symbol="NQ", inputs=None, tz="America/New_York"):
	"""run script on the chart bars (a runtime.Series) and those sources
	returns for a time frame key (see runtime.tfkind): a Result"""
	res = Result()
	res.S = chart
	res.title = script.title
	if script.error:
		res.error = script.error
		return res
	t0 = _time.time()
	RT = R.RT
	RT.reset()
	RT.tz = tz
	RT.sources = sources
	RT.inputs = inputs or {}
	RT.chart = chart.tfp
	RT.tfp = chart.tfp
	RT.symbol = symbol
	root = symbol.rstrip("!").rstrip("1") or symbol
	RT.sym = {"ticker": root + "1!", "tickerid": "CME_MINI:" + root + "1!", "root": root, "prefix": "CME_MINI",
		"description": DESCRIPTIONS.get(root, root + " Futures"), "type": "futures",
		"pointvalue": POINTVALUES.get(root, 1)}
	RT.mintick = 0.25
	ns = namespace()
	ns.update(script.consts)
	RT.ns = ns
	ctx = R.Ctx()
	try:
		if chart.n == 0:
			raise R.PineRuntimeError("no candles")
		exec(script.code, ns)
		R.setbar(ns, chart, 0)
		ns["_init"](ctx)
		bar = ns["_bar"]
		for i in range(chart.n):
			R.setbar(ns, chart, i)
			bar(ctx)
	except Exception as x:
		tb = traceback.extract_tb(x.__traceback__)
		where = ""
		for fr in reversed(tb):
			if fr.filename == script.name:
				k = bisect.bisect_right(script.lines, (fr.lineno, 1 << 30)) - 1
				if k >= 0:
					where = f" (line {script.lines[k][1]})"
				break
		res.error = f"{type(x).__name__}: {x}{where} at bar {RT.bar}"
		res.trace = traceback.format_exc()
	res.lines = [o for o in RT.objs["line"] if o.alive]
	res.labels = [o for o in RT.objs["label"] if o.alive]
	res.boxes = [o for o in RT.objs["box"] if o.alive]
	res.tables = [o for o in RT.objs["table"] if o.alive]
	res.linefills = [o for o in RT.objs["linefill"] if o.alive]
	res.plots = RT.plots
	res.seconds = _time.time() - t0
	RT.ns = None
	RT.sources = None
	RT.htfs = {}
	return res

DESCRIPTIONS = {"NQ": "E-mini Nasdaq-100 Futures", "MNQ": "Micro E-mini Nasdaq-100 Futures",
	"ES": "E-mini S&P 500 Futures", "MES": "Micro E-mini S&P 500 Futures", "YM": "E-mini Dow Futures",
	"MYM": "Micro E-mini Dow Futures", "RTY": "E-mini Russell 2000 Futures", "M2K": "Micro E-mini Russell 2000 Futures",
	"FDAX": "DAX Futures", "FDXM": "Mini-DAX Futures"}
POINTVALUES = {"NQ": 20, "MNQ": 2, "ES": 50, "MES": 5, "YM": 5, "MYM": 0.5, "RTY": 50, "M2K": 5}
