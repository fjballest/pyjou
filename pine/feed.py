"""The bars a script runs on, from the journal's data (m15.Data): the
chart's, and those of the time frames it requests, all cut at the end of
the last candle shown."""

import numpy as np

import m15
from . import runtime as R

def series(t, o, h, l, c, tc, tfp):
	"""a runtime.Series of times t (seconds), prices and close times tc (seconds)"""
	return R.Series(np.asarray(t, dtype=np.int64) * 1000, o, h, l, c, np.asarray(tc, dtype=np.int64) * 1000, tfp)

def sesstart(dayno):
	"""the UTC seconds when trading days dayno (an array) start, 18:00 New York the day before"""
	wall = np.asarray(dayno, dtype=np.int64) * 86400 + m15.DAYSTART * 3600
	return wall - m15.nyoffsets(wall)

def sesend(dayno):
	wall = np.asarray(dayno, dtype=np.int64) * 86400 + m15.DAYEND * 3600
	return wall - m15.nyoffsets(wall)

class Feed:
	"""the bars of data (m15) and low (a lower time frame, or None) up to
	time upto (seconds, the end of the last candle shown)"""
	def __init__(self, data, low, upto):
		self.data, self.low, self.upto = data, low, int(upto)

	def rows(self, src, since=None):
		j = int(np.searchsorted(src.t, self.upto, "left"))
		i = 0 if since is None else int(np.searchsorted(src.t, since, "left"))
		return np.column_stack([src.t[i:j].astype(float), src.o[i:j], src.h[i:j], src.l[i:j], src.c[i:j]])

	def source(self, minutes):
		"""the data candles of minutes are made from"""
		low = self.low
		if low is not None and len(low) and (minutes < self.data.tf or minutes % self.data.tf) and minutes % low.tf == 0:
			return low
		if minutes % self.data.tf == 0 or low is None:
			return self.data
		return low

	def minutes(self, n, nbars=None, since=None):
		src = self.source(n)
		if nbars is not None and since is None:
			since = self.upto - (nbars + 2) * n * 60 * 3	# room for the closed hours
		a = self.rows(src, since)
		if n != src.tf:
			a = m15.resample(a, n)
		if nbars is not None and len(a) > nbars:
			a = a[-nbars:]
		t = a[:, 0].astype(np.int64)
		return series(t, a[:, 1], a[:, 2], a[:, 3], a[:, 4], t + n * 60, str(n))

	def chart(self, tf, nbars):
		"""the chart's bars: the last nbars candles of tf minutes"""
		s = self.minutes(tf, nbars)
		return s

	def periods(self, kind, n):
		"""bars of days, weeks or months ("D", "W", "M") from the m15 data"""
		a = self.rows(self.data)
		if not len(a):
			return series([], [], [], [], [], [], R.tfstring(kind, n))
		t = a[:, 0].astype(np.int64)
		day = m15.daynos(t)
		if kind == "D":
			key = day // n
		elif kind == "W":
			key = (day - 4) // (7 * n)
		else:
			d = day.astype("datetime64[D]").astype("datetime64[M]").astype(np.int64)
			key = d // n
		starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
		ends = np.r_[starts[1:] - 1, len(a) - 1]
		o = a[starts, 1]
		h = np.maximum.reduceat(a[:, 2], starts)
		l = np.minimum.reduceat(a[:, 3], starts)
		c = a[ends, 4]
		bt = sesstart(day[starts])
		if kind == "D":
			lastday = (key[starts] + 1) * n - 1
		elif kind == "W":
			lastday = (key[starts] + 1) * 7 * n + 4 - 3	# the Friday
		else:
			nextm = ((key[starts] + 1) * n).astype("datetime64[M]").astype("datetime64[D]").astype(np.int64)
			lastday = nextm - 1
			wd = (lastday + 3) % 7	# 0 Monday
			lastday = lastday - np.where(wd == 5, 1, np.where(wd == 6, 2, 0))
		tc = sesend(lastday)
		return series(bt, o, h, l, c, tc, R.tfstring(kind, n))

	def __call__(self, key):
		kind, n = key
		if kind == "m":
			return self.minutes(n, nbars=20000)
		if kind == "S":
			return self.minutes(1, nbars=20000)
		return self.periods(kind, n)
