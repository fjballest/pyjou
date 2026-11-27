#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_quit.py
# quitting with several data windows and indicators running ends cleanly.
#
import os
import subprocess
import sys
import tempfile

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.join(here, "..")
env = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_CONFIG_HOME=tempfile.mkdtemp(), HOME=tempfile.mkdtemp(),
	XDG_DATA_HOME=tempfile.mkdtemp())
j = tempfile.mkdtemp()
src = tempfile.mkdtemp()
driver = os.path.join(src, "driver.py")
with open(driver, "w") as f:
	f.write(r'''
import os, sys, time
sys.path.insert(0, %r)
from datetime import date
import numpy as np
import m15
j, src = %r, %r
rows, p = [], 1000.0
rng = np.random.default_rng(1)
for day in range(20):
	if day %% 7 in (5, 6):
		continue
	for k in range(92):
		t = int(m15.daystart([m15.Data.dayn(date(2026, 9, 7)) + day])[0]) + k * 900
		o = p
		p = round(p + rng.normal(0, 2), 2)
		rows.append((t, o, max(o, p) + 1, min(o, p) - 1, p))
with open(os.path.join(src, "MNQ.m15.csv"), "w") as f:
	f.write("time,open,high,low,close\n")
	for r in rows:
		f.write("%%d,%%g,%%g,%%g,%%g\n" %% r)
m15.importfile(j, os.path.join(src, "MNQ.m15.csv"))
with open(os.path.join(src, "Slow.txt"), "w") as f:
	f.write('indicator("Slow", overlay = true)\nvar float s = 0.0\nfor i = 0 to 20000\n    s := s + math.sin(i)\nplot(close + s * 0)\n')
import dj
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import mainwin, indicators, ocrworker
sys.path.insert(0, os.path.join(%r, "tests"))
import sandbox
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])
real = mainwin.MainWindow
class Opened(real):
	def __init__(self, *a, **k):
		super().__init__(*a, **k)
		QTimer.singleShot(200, self.go)

	def go(self):
		w = self
		indicators.importfiles([os.path.join(src, "Slow.txt")])
		w.setdatamode(True)
		w.showdata(("d", date(2026, 9, 9)), force=True)
		for tf in (5, 60):
			w2 = real(j)
			w2.show()
			w2.setdatamode(True)
			w2.setdatatf(tf)
			w2.showdata(("d", date(2026, 9, 9)), force=True)
		QTimer.singleShot(300, QApplication.closeAllWindows)	# Cmd-Q, with runs going on
mainwin.MainWindow = Opened
sys.argv = ["dj.py", j]
dj.main()
''' % (root, j, src, root))
r = subprocess.run([sys.executable, driver], env=env, capture_output=True, text=True, timeout=90)
check(r.returncode == 0, "quitting with data windows and indicators running exits cleanly: %d %s" % (r.returncode, r.stderr[-800:]))
print("ALL OK")
