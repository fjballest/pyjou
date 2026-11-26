"""Pine indicators on the data charts: the scripts imported (kept in DIR,
for every journal), which of them are on (remembered in the settings), and
what they draw on a chart, run up to its last candle shown (see pine).

The rest of the program only calls overlay() and the menu functions here,
so taking this file and pine/ out leaves it as it was."""

import os
import shutil
import time

import numpy as np

import m15

DIR = None	# set by the main window: …/DayJournal/indicators
EXTS = (".txt", ".pine")
KEEP = 24	# runs kept

_settings = None
_cache = {}

def setup(dirpath, settings):
	"""where the scripts are kept, and a function giving the QSettings"""
	global DIR, _settings
	DIR = dirpath
	_settings = settings

def scripts():
	"""[(name, path)] of the imported scripts, by name"""
	if not DIR or not os.path.isdir(DIR):
		return []
	out = []
	for f in sorted(os.listdir(DIR), key=str.lower):
		if f.lower().endswith(EXTS) and not f.startswith("."):
			out.append((os.path.splitext(f)[0], os.path.join(DIR, f)))
	return out

def enabled():
	"""the names of the scripts that are on"""
	if _settings is None:
		return []
	v = _settings().value("indicators/on", [])
	if isinstance(v, str):
		v = [v] if v else []
	have = {n for n, _ in scripts()}
	return [n for n in (v or []) if n in have]

def setenabled(names):
	if _settings is not None:
		_settings().setValue("indicators/on", list(names))

def toggle(name, on):
	names = [n for n in enabled() if n != name]
	if on:
		names.append(name)
	setenabled(names)

def importfiles(paths):
	"""copy the scripts at paths into DIR, turned on: [names]"""
	os.makedirs(DIR, exist_ok=True)
	names = []
	for p in paths:
		base = os.path.basename(p)
		if not base.lower().endswith(EXTS):
			base += ".txt"
		dest = os.path.join(DIR, base)
		if os.path.abspath(dest) != os.path.abspath(p):
			shutil.copyfile(p, dest)
		names.append(os.path.splitext(base)[0])
	setenabled(list(dict.fromkeys(enabled() + names)))
	return names

def remove(name):
	for n, p in scripts():
		if n == name:
			os.remove(p)
	setenabled([n for n in enabled() if n != name])

def lastend(g, tf):
	"""the UTC time (s) where the last candle shown on the chart of
	geometry g in tf minutes ends, or None"""
	wall, o, h, l, c, zero = g.bars
	if not len(wall):
		return None
	unit = 3600 if g.kind == "d" else 86400
	t = (wall - zero) / unit
	k = int(np.searchsorted(t, g.t1, "left")) - 1	# the last starting before the right edge
	if k < 0:
		return None
	start = int(wall[k])
	return start - m15.nyoffset(start + 5 * 3600) + tf * 60

def results(data, low, g, tf):
	"""the runs of the scripts that are on for the chart of geometry g:
	[pine.Result]; low is the data of the lowest time frame, or a function
	giving it (called only when needed)"""
	on = enabled()
	if not on or data is None or not len(data):
		return []
	import pine
	from pine.feed import Feed
	upto = lastend(g, tf)
	if upto is None:
		return []
	paths = dict(scripts())
	if callable(low):
		low = low()
	out = []
	feed = None
	chart = None
	for name in on:
		p = paths[name]
		try:
			st = os.stat(p)
		except OSError:
			continue
		key = (p, st.st_mtime, st.st_size, tf, upto, len(data), len(low) if low is not None else 0, data.symbol)
		r = _cache.get(key)
		if r is None:
			if feed is None:
				feed = Feed(data, low, upto)
				chart = feed.chart(tf, pine.NBARS)
			with open(p, encoding="utf-8", errors="replace") as f:
				script = pine.Script(f.read(), name)
			r = pine.run(script, chart, feed, symbol=data.symbol or "NQ")
			if len(_cache) >= KEEP:
				_cache.pop(next(iter(_cache)))
			_cache[key] = r
		out.append(r)
	return out

def overlay(data, low, g, tf):
	"""a function painting the indicators that are on over the chart of
	geometry g in tf minutes (fn(painter, geometry)), or None"""
	rs = results(data, low, g, tf)
	if not rs:
		return None
	from pine.draw import paint
	from PySide6.QtCore import QRectF, Qt
	from PySide6.QtGui import QColor, QFont

	def fn(p, geom):
		for r in rs:
			paint(p, geom, r, tf)
		bad = [r for r in rs if r.error]
		if bad:
			p.save()
			f = QFont()
			f.setPixelSize(13)
			p.setFont(f)
			p.setPen(QColor(200, 30, 30))
			y = geom.T + geom.ph - 18 * len(bad) - 4
			for r in bad:
				p.drawText(QRectF(geom.L + 6, y, geom.pw - 12, 18), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
					f"{r.title}: {r.error}")
				y += 18
			p.restore()
	return fn

def errors(data, low, g, tf):
	return [f"{r.title}: {r.error}" for r in results(data, low, g, tf) if r.error]
