#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_patterns.py
# when swings and retracements start (patterns.py), its window, and macro
# times set in an indicator's source.
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
from datetime import date
import numpy as np

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication([])
import m15
import patterns

# a zigzag: up 10, down 6, up 2, down 9
px = np.array([0, 5, 10, 7, 4, 5, 6, 3, -3, -1], dtype=float)
z = patterns.zigzag(px + 0.5, px - 0.5, np.full(len(px), 5.0))
check(z == [(0, -1), (2, 1)], "the zigzag's turns, once confirmed: " + str(z))
small = patterns.zigzag(px + 0.5, px - 0.5, np.full(len(px), 2.0))
big = [(0, -1), (10, 1), (20, -1)]
check(patterns.retracements(big, [(0, -1), (4, 1), (6, -1), (10, 1), (13, -1), (15, 1), (20, -1)]) == [(4, 1), (13, -1)],
	"pullbacks: a high in a leg going up, a low in one going down")

# two years of m15 data, quiet but for 09:30 to 11:30
j, src = tempfile.mkdtemp(), tempfile.mkdtemp()
rng = np.random.default_rng(3)
rows, p = [], 15000.0
d0 = m15.Data.dayn(date(2024, 1, 1))
for day in range(700):
	if day % 7 in (5, 6):
		continue
	for k in range(92):
		t = int(m15.daystart([d0 + day])[0]) + k * 900
		vol = 25 if 62 <= k <= 70 else 6
		o = p
		p = round(p + rng.normal(0, vol), 2)
		rows.append((t, o, max(o, p) + 2, min(o, p) - 2, p))
with open(os.path.join(src, "MNQ.m15.csv"), "w") as f:
	f.write("time,open,high,low,close\n")
	for r in rows:
		f.write("%d,%g,%g,%g,%g\n" % r)
m15.importfile(j, os.path.join(src, "MNQ.m15.csv"))
data = m15.Data(j)

r = patterns.byday(data)
top = [n for n, _ in r.top(4)]
check(r.n == 500 and set(top) <= {"09:30", "10:00", "10:30", "11:00", "11:30"}, "the day: swings start when the market moves: " + str(top))
check(len(r.names) == 46 and r.names[0] == "18:00" and r.names[-1] == "16:30", "slots of 30 minutes, 18:00 to 17:00")
check(all(0 <= x <= 1 for x in r.swing) and r.retr.max() > 0.2, "probabilities, of retracements too")
r15 = patterns.byday(data, slot=15)
check(len(r15.names) == 92, "or of 15")
w = patterns.byweek(data)
best = w.top(1)[0][0]
check(w.n == 100 and w.rows == 5 and len(w.names) == 115 and best.split()[1] in ("09:00", "10:00", "11:00"), "the week, by day and hour: " + best)
m = patterns.bymonth(data)
check(m is not None and len(m.names) == 23 and 20 <= m.n <= 24, "the month, by trading day")
part = patterns.byday(data, first=date(2025, 6, 1))
check(part.n < r.n, "for a part of the data")

mondays = {data.dayn(d) for d in data.days() if d.weekday() == 0}
mon = patterns.byday(data, only=mondays)
check(mon.n == 100 and mon.swing.max() > 0, "only some days: " + str(mon.n))
check(patterns.byweek(data, only={min(mondays)}).n == 1 and patterns.bymonth(data, only=mondays) is not None, "or weeks")
wins = patterns.windows(r, least=0.25)
check(wins and wins[0][0].startswith(("09", "10")) and "-" in wins[0][0], "macro windows: " + str(wins[:3]))
times = patterns.sortedtimes(wins)
check(times.split(",")[0] < "12", "as macro times, by the clock: " + times)

src_ = 'indicator("M")\nstring djMacros = "0950-1010,1050-1110" // @dj-macros the journal sets them\nplot(close)\n'
check(patterns.marked(src_) == [1], "the line marked")
new, ch = patterns.withmacros(src_, "0930-1000")
check('string djMacros = "0930-1000" // @dj-macros the journal sets them' in new and len(ch) == 1, "its times replaced, the rest kept")

# the window, from the menu
import mainwin
import indicators
import ocrworker
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])
win = mainwin.MainWindow(j)
win.show()
app.processEvents()
win.swingact.trigger()
app.processEvents()
pw = win.swingwin
check(pw.isVisible() and pw.results["day"] is not None and "Most likely swing starts" in pw.summary.text(), "View ▸ Swing Times")
pw.range.setCurrentIndex(2)
pw.compute()
check(pw.results["day"].n < 140, "the last 6 months")
pw.tabs.setCurrentIndex(1)
check("weeks" in pw.summary.text(), "the week's summary")
win.datapanel.match = lambda kind, d: d.weekday() == 0
pw.range.setCurrentIndex(0)
pw.tabs.setCurrentIndex(0)
pw.compute()
check(pw.results["day"].n == 100 and "the search leaves" in pw.summary.text(), "only the days the search leaves")
win.datapanel.match = None
pw.compute()
img = pw.grab()
check(img.width() > 500, "drawn")

script = os.path.join(src, "Mac.txt")
with open(script, "w") as f:
	f.write(src_)
indicators.importfiles([script])
path = dict(indicators.scripts())["Mac"]
shown = []
def run(dlg):
	shown.append(dlg)
	dlg.least.setValue(25)
	QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
	check(dlg.target.currentText() == "Mac" and dlg.list.count() > 0, "the dialog lists the windows and the marked indicators")
	dlg.times.setText("0930-1000,1030-1100")
	check(dlg.apply(), "set in the indicator, once confirmed")
	return 0
patterns.MacrosDialog.exec = run
pw.macros()
check(shown, "Macro Times…")
txt = open(path).read()
check('"0930-1000,1030-1100" // @dj-macros' in txt and open(path + ".bak").read() == src_, "written, the old one kept as .bak")
print("ALL OK")
os._exit(0)
