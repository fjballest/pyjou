#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_link.py
# RoadBook asks DayJournal to show a trade: the journal of its instrument
# is found among the recent ones and the day shown, at the trade.
#
import faulthandler
faulthandler.dump_traceback_later(50, exit=True)
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

import numpy as np
import m15
import link

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

def journal(sym, days):
	d = tempfile.mkdtemp()
	rows = []
	for k, n in enumerate(days):
		for c in range(92):
			wall = n * 86400 + int((-6 + c / 4) * 3600)
			t = wall - m15.nyoffset(wall + 5 * 3600)
			p = 100 + k * 10 + c / 10
			rows.append([t, p, p + 1, p - 1, p + 0.5])
	m15.writerows(os.path.join(d, m15.filename(sym, rows[0][0])), np.array(rows, dtype=float))
	return d

import query
days = [n for n in range(query.dayn(date(2026, 3, 2)), query.dayn(date(2026, 3, 14))) if (n + 3) % 7 < 5]
nq, es = journal("MNQ", days), journal("ES", days)

check(link.symbolof(nq) == "MNQ", "the symbol of a journal's data")
check(link.matches("MNQ", ["NASDAQ", "*nasdaq*", "MNQ*", "NQ*"]) and not link.matches("ES", ["NASDAQ", "NQ*"]),
	"a symbol is one of an instrument's names")
check(link.journalfor(["NASDAQ", "NQ*", "MNQ*"], [es, nq]) == nq, "the journal of the instrument")
check(link.parse("nonsense") is None and link.parse('{"at": 5, "instrument": "X", "names": ["Y"]}')["names"] == ["X", "Y"],
	"requests read")

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
import mainwin
mainwin.recentjournals = lambda: [es, nq]	# the tests' journals are in temporary folders, kept out of the recent ones
w = mainwin.MainWindow(es)
w.show()
app.processEvents()
got = []
srv = link.serve(app, lambda r: got.append(mainwin.gotorequest(r, w)))
check(srv is not None, "DayJournal listens")
# a trade on the third day at 10:00 New York, out at 11:00
n = days[2]
wall = n * 86400 + 10 * 3600
at = wall - m15.nyoffset(wall + 5 * 3600)
req = json.dumps({"instrument": "NASDAQ", "names": ["*nasdaq*", "MNQ*", "NQ*"], "at": at, "exitat": at + 3600, "dir": 1, "trade": 7})
client = ("import sys\nfrom PySide6.QtCore import QCoreApplication\nfrom PySide6.QtNetwork import QLocalSocket\n"
	"a = QCoreApplication([])\ns = QLocalSocket()\ns.connectToServer('DayJournal-goto')\n"
	"assert s.waitForConnected(3000)\ns.write((sys.argv[1] + '\\n').encode())\ns.flush()\ns.waitForBytesWritten(3000)\n"
	"s.waitForReadyRead(3000)\nprint(bytes(s.readAll()).decode().strip())\n")
p = subprocess.Popen([sys.executable, "-c", client, req], stdout=subprocess.PIPE, text=True)
t0 = time.time()
while p.poll() is None and time.time() - t0 < 20:
	app.processEvents()
	time.sleep(0.01)
for _ in range(50):
	app.processEvents()
out = p.stdout.read().strip()
check(out == "ok" and got == [True], "a trade sent from another program is shown")
wins = [x for x in QApplication.topLevelWidgets() if isinstance(x, mainwin.MainWindow) and x.isVisible()]
shown = [x for x in wins if x.journal is not None and os.path.realpath(x.journal.dir) == os.path.realpath(nq)]
check(len(shown) == 1, "in a window with the journal of the instrument, opened for it")
x = shown[0]
check(x.datamode and x.datakey == ("d", m15.dayof(at)) and x.tradeshown["mark"], "at the day of the trade, marked")
z = x.datazooms.get(("d", x.datakey[1], x.datashowntf))
check(z is not None, "zoomed on it")
x.grab().save(os.path.join(tempfile.gettempdir(), "link.png"))
# again: the same window, no new one
got.clear()
mainwin.gotorequest(link.parse(req), w)
wins2 = [x for x in QApplication.topLevelWidgets() if isinstance(x, mainwin.MainWindow) and x.isVisible()]
check(len(wins2) == len(wins), "a second one goes to the window that has the journal")
r = link.parse(json.dumps({"instrument": "DAX", "names": ["*dax*"], "at": at}))
from PySide6.QtWidgets import QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: got.append("told"))
check(mainwin.gotorequest(r, w) is False and got == ["told"], "an instrument with no journal says so")
