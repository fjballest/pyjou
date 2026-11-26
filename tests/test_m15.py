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
check(os.listdir(d) == ["MNQ-261116.m15.csv.gz"], "kept compressed, named after its first day")
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
check(data.end("d", date(2026, 11, 16)) >= 17, "a whole day ends at 17:00 or later")
check(data.readdrawing("d", date(2026, 11, 16)) is None, "nothing drawn at first")
shapes = {"version": 1, "shapes": [{"kind": "line", "p1": [1, 2], "p2": [3, 4], "color": "#e53935", "width": 3.0}]}
data.savedrawing("d", date(2026, 11, 16), shapes)
check(data.readdrawing("d", date(2026, 11, 16)) == shapes and data.drawn("d", date(2026, 11, 16)), "a drawing kept for a day")
data.savedrawing("d", date(2026, 11, 16), {"shapes": []})
check(not data.drawn("d", date(2026, 11, 16)), "and removed when empty")
old = tempfile.mkdtemp()
csvfile(os.path.join(old, "ES.m15.csv"), start, 50)
od = m15.Data(old)
check(len(od) == 50 and os.listdir(old) == ["ES-261116.m15.csv.gz"], "a plain data file is compressed and renamed")
os.rename(os.path.join(old, "ES-261116.m15.csv.gz"), os.path.join(old, "ES.m15.csv.gz"))
check(len(m15.Data(old)) == 50 and os.listdir(old) == ["ES-261116.m15.csv.gz"], "a data file named otherwise is renamed")
# files of limited size: a new one starts when the last one is full
big = tempfile.mkdtemp()
m15.MAXFILE = 2000
bd = m15.Data(big)
bd.add(os.path.join(src, "MNQ.m15.csv.zip"))
files = sorted(os.listdir(big))
check(len(files) > 1 and all(os.path.getsize(os.path.join(big, f)) <= 2600 for f in files), "the data is split in files of limited size")
check(len(m15.Data(big)) == 300 and files[0] == "MNQ-261116.m15.csv.gz", "and read back whole")
n = len(files)
bd.add(os.path.join(src, "MNQ2.csv"))
check(len(m15.Data(big)) == 400 and len(os.listdir(big)) >= n, "more data goes on in the last file or new ones")
m15.MAXFILE = 512 * 1024
check("Asia" in data.summary("d", date(2026, 11, 16)), "a summary of the day")

# m1 candles as a TradingView dump writes them: ; and the UTC time of their close
low = tempfile.mkdtemp()
m1 = os.path.join(src, "MNQ.m1.dump.csv")
with open(m1, "w") as f:
	f.write("time_utc_close;open;high;low;close;volume\n")
	for k in range(60 * 30):	# 30 hours from Sunday 18:00 New York
		t = start + 60 * (k + 1)
		p = 100 + k / 60
		f.write(f"{datetime.fromtimestamp(t, timezone.utc):%Y-%m-%d %H:%M:%S};{p};{p + 1};{p - 1};{p + .5};10\n")
rows = m15.readrows(m1)
check(len(rows) == 1800 and rows[0][0] == start and m15.tfof(rows) == 1, "an m1 dump read, times at the open")
done = m15.importfile(low, m1)
check(done == [(1, 1800, 0), (15, 120, 0)], "m1 imported, and made m15 too")
check(sorted(os.listdir(low)) == ["MNQ-261116.m1.csv.gz", "MNQ-261116.m15.csv.gz"], "kept in files of each time frame")
check(m15.lowtfs(low) == [1], "the lower time frames there")
m1d, m15d = m15.Data(low, 1), m15.Data(low)
r = m15.resample(m1d.rows()[:15], 15)[0]
check(tuple(r) == tuple(m15d.rows()[0]) and r[2] == max(x[2] for x in m1d.rows()[:15]), "the m15 candles made from m1")
w5 = m1d.bars("d", date(2026, 11, 16), 5)
check(len(w5[0]) == 24 * 12 and (w5[0][1] - w5[0][0]) == 300, "a day in m5 from m1")
check(len(m15d.bars("d", date(2026, 11, 16), 60)[0]) == 24, "and in h1 from m15")
check(m15.importfile(low, m1) == [(1, 0, 1800), (15, 0, 120)], "nothing twice")

# an m1 dump of another feed, whose prices differ from the stored m15 by an
# offset that changes when the contract rolls (here, on Wednesday 18 Nov)
rd, rsrc = tempfile.mkdtemp(), tempfile.mkdtemp()
wed = int(datetime(2026, 11, 17, 23, 0, tzinfo=timezone.utc).timestamp())	# Tue 18:00 NY, Wednesday's start
def px(t):
	return 1000 + ((t - start) // 60) % 50
def feed(t):	# the dump: 8.5 above the m15 up to Tuesday, 5.5 from Wednesday, a bad tick on Wednesday
	return px(t) + (8.5 if t < wed else 5.5)
with open(os.path.join(rsrc, "MNQ.m15.csv"), "w") as f:	# Monday 16 Nov to Thursday 19 Nov, m15
	f.write("time,open,high,low,close\n")
	for k in range(24, 4 * 24 * 4):
		t = start + 900 * k
		f.write(f"{t},{px(t)},{px(t) + 2},{px(t) - 2},{px(t + 840)}\n")
m15.importfile(rd, os.path.join(rsrc, "MNQ.m15.csv"))
dump = os.path.join(rsrc, "MNQ.m1.csv")
with open(dump, "w") as f:	# from Sunday 18:00, before the m15, to Thursday
	f.write("time_utc_close;open;high;low;close;volume\n")
	for k in range(60 * 24 * 4):
		t = start + 60 * k
		hi = feed(t) + 2 + (90 if t == wed + 3600 * 15 else 0)
		f.write(f"{datetime.fromtimestamp(t + 60, timezone.utc):%Y-%m-%d %H:%M:%S};{feed(t)};{hi};{feed(t) - 2};{feed(t)};1\n")
offs = []
m15.importfile(rd, dump, None, offs)
check([(d, o) for d, o in offs] == [(date(2026, 11, 16), -8.5), (date(2026, 11, 18), -5.5)], "an offset for each contract, found where the data overlap")
r1 = m15.Data(rd, 1).rows()
check(r1[0][1] == px(start) and r1[-1][4] == px(int(r1[-1][0])), "the m1 candles moved to match the m15")
rm = m15.Data(rd).rows()
check(rm[0][0] == start and rm[0][1] == px(start) and len(rm) == 4 * 24 * 4, "the m15 made of them, before the stored ones, matches too")
check(m15.rolls(rm, rm) == [(m15.daynos([start])[0], 0.0)], "no offset for the same data")

from PySide6.QtGui import QGuiApplication
app = QGuiApplication([])
import dataview
out = os.path.join(src, "w.png")
img = dataview.render(data, "w", date(2026, 11, 16), out)
check(img is not None and os.path.exists(out), "the week drawn")
check(dataview.render(data, "d", date(2026, 11, 17)) is not None, "a day drawn")
check(dataview.render(data, "d", date(2026, 12, 1)) is None, "nothing for a day without data")
g = dataview.Geom(m15d, "d", date(2026, 11, 16), 1, m1d)
check(g.ok and g.W > 1800 and dataview.render(m15d, "d", date(2026, 11, 16), None, 1, m1d) is not None, "a day drawn in m1, wider")
