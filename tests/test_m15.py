#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_m15.py
# m15 data imported from CSV files that overlap, its days, weeks, profiles
# and sessions, and the chart drawn from it.
#
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import date, datetime, timezone

import m15

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

def csvfile(path, start, n, zipped=False):
	"""n candles from UTC time start, going up then down, with TradingView's extra columns"""
	lines = ["time,open,high,low,close,SHORT,LONG"]
	for k in range(n):
		p = 100 + (k if k < n // 2 else n - k)
		lines.append(f"{start + 900*k},{p},{p + 1.5},{p - 1.25},{p + 0.5},0,0")
	text = "\n".join(lines) + "\n"
	if zipped:
		with zipfile.ZipFile(path, "w") as z:
			z.writestr("MNQ.m15.csv", text)
	else:
		with open(path, "w") as f:
			f.write(text)

d = tempfile.mkdtemp()
src = tempfile.mkdtemp()
# Sunday 15 Nov 2026 18:00 New York (EST) is 23:00 UTC
start = int(datetime(2026, 11, 15, 23, 0, tzinfo=timezone.utc).timestamp())
csvfile(os.path.join(src, "MNQ.m15.csv.zip"), start, 300, zipped=True)
csvfile(os.path.join(src, "MNQ2.csv"), start + 900*200, 200)
data = m15.Data(d)
check(len(data) == 0 and data.symbol is None, "no data at first")
check(data.add(os.path.join(src, "MNQ.m15.csv.zip")) == (300, 0), "a zip imported")
check(os.path.exists(os.path.join(d, "MNQ.m15.csv.gz")), "kept compressed, as MNQ.m15.csv.gz")
check(data.add(os.path.join(src, "MNQ2.csv")) == (100, 100), "only the candles after the last one are added")
data = m15.Data(d)
check(len(data) == 400 and len(set(data.t.tolist())) == 400, "no duplicates")
check(data.days()[0] == date(2026, 11, 16), "Sunday evening is Monday's")
check(data.weeks() == [date(2026, 11, 16)], "one week")
check(data.walltime(0).hour == 18, "New York time")
p = data.profile("w", date(2026, 11, 16))
check(p and min(v for _, v in p) == 0 and max(v for _, v in p) == 1, "a week profile from 0 to 1")
check(p[0][0] < 0, "the week starts on Sunday evening")
dp = data.profile("d", date(2026, 11, 16))
check(dp and -6 <= dp[0][0] < -5.5, "a day profile in hours, from 18:00 the day before")
s = data.sessions(date(2026, 11, 16))
check([x[0] for x in s] == ["Asia", "London", "NY AM"], "the sessions of a day")
check(all(x[3] >= x[4] for x in s), "with their highs and lows")
wk = data.profile("w", date(2026, 11, 16), upto=date(2026, 11, 16))
check(wk and wk[-1][0] < 1, "a week profile up to the end of Monday")
dt = data.profile("d", date(2026, 11, 16), until=3)
check(dt and dt[-1][0] <= 3, "a day profile up to 03:00")
check(abs(data.end("d", date(2026, 11, 16)) - 17) < 0.01, "a whole day ends at 17:00")
check(data.readdrawing("d", date(2026, 11, 16)) is None, "nothing drawn at first")
shapes = {"version": 1, "shapes": [{"kind": "line", "p1": [1, 2], "p2": [3, 4], "color": "#e53935", "width": 3.0}]}
data.savedrawing("d", date(2026, 11, 16), shapes)
check(data.readdrawing("d", date(2026, 11, 16)) == shapes and data.drawn("d", date(2026, 11, 16)), "a drawing kept for a day")
data.savedrawing("d", date(2026, 11, 16), {"shapes": []})
check(not data.drawn("d", date(2026, 11, 16)), "and removed when empty")
old = tempfile.mkdtemp()
csvfile(os.path.join(old, "ES.m15.csv"), start, 50)
od = m15.Data(old)
check(len(od) == 50 and os.listdir(old) == ["ES.m15.csv.gz"], "a plain data file is compressed")
check("Asia" in data.summary("d", date(2026, 11, 16)), "a summary of the day")

from PySide6.QtGui import QGuiApplication
app = QGuiApplication([])
import dataview
out = os.path.join(src, "w.png")
img = dataview.render(data, "w", date(2026, 11, 16), out)
check(img is not None and os.path.exists(out), "the week drawn")
check(dataview.render(data, "d", date(2026, 11, 17)) is not None, "a day drawn")
check(dataview.render(data, "d", date(2026, 12, 1)) is None, "nothing for a day without data")
