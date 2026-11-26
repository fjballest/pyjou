#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_news.py
# the news days (news.py), as tags and on the data charts, and the data
# charts scaled on their axes, with what is drawn on them, in the window.
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()
from datetime import date, datetime, timezone

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

import news
n = news.News()
check(n.of(date(2024, 6, 12)) == [(8.5, "CPI"), (14.0, "FOMC")], "CPI and FOMC the same day, by time")
check(n.names(date(2026, 11, 13)) == ["PPI"] and n.names(date(2026, 11, 16)) == [], "PPI days, and days without news")
d = tempfile.mkdtemp()
with open(os.path.join(d, news.NEWSFILE), "w") as f:
	f.write("# mine\n2026-11-16 NFP 08:30\n-2026-11-13 PPI\n2026-11-17 cpi\nnonsense\n")
n = news.News(d)
check(n.names(date(2026, 11, 16)) == ["NFP"] and n.names(date(2026, 11, 13)) == [] and n.of(date(2026, 11, 17)) == [(8.5, "CPI")],
	"news added and taken away in the journal's file")
check(n.bad == ["nonsense"], "lines not understood kept apart")
check([x[2] for x in news.News().inweek(date(2026, 11, 9))] == ["CPI", "PPI"], "the news of a week")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QWheelEvent
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

import journal
import mainwin
import m15
import dataview
import ocrworker
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])

# a journal with a capture on a CPI day, and m15 data for that week
j = tempfile.mkdtemp()
img = QImage(800, 450, QImage.Format.Format_RGB32)
img.fill(QColor(240, 240, 230))
img.save(os.path.join(j, "day261110.png"))
img.save(os.path.join(j, "day261109.png"))
jj = journal.Journal(j)
check(jj.find("day261110.png").tags == ["CPI"] and jj.find("day261109.png").tags == [], "the news of its day a tag of a capture")
jj.settext(jj.find("day261110.png"), [["MNQ", 0.9], ["cpi", 0.9]])
check(jj.find("day261110.png").tags == ["CPI", "MNQ"], "with the tags read, once")

start = int(datetime(2026, 11, 8, 23, 0, tzinfo=timezone.utc).timestamp())	# Sunday 8 Nov 18:00 New York
src = tempfile.mkdtemp()
with open(os.path.join(src, "MNQ.m15.csv"), "w") as f:
	f.write("time,open,high,low,close\n")
	for k in range(96 * 5):
		p = 1000 + (k % 40)
		f.write(f"{start + 900 * k},{p},{p + 2},{p - 2},{p + 1}\n")
m15.importfile(j, os.path.join(src, "MNQ.m15.csv"))
data = m15.Data(j)

g = dataview.Geom(data, "d", date(2026, 11, 10))
check(g.view() is None and g.inplot(g.L + g.pw + 10, g.T + 50) == "p" and g.inplot(g.L + 50, g.T + g.ph + 10) == "t"
	and g.inplot(g.L + 50, g.T + 50) == "c", "where the axes are")
v = g.zoomed("p", 1020, 0.5)
check(abs((v[0] - v[1]) - (g.top - g.bot) / 2) < 1e-6 and v[2:] == (g.t0, g.t1), "the prices zoomed in")
z = dataview.Geom(data, "d", date(2026, 11, 10), view=v)
check(abs(z.Y(1020) - g.Y(1020)) < 1e-6, "around the price under the mouse")
t = g.zoomed("t", 9.5, 0.25)
check(abs((t[3] - t[2]) - (g.t1 - g.t0) / 4) < 1e-6, "the times zoomed in")
check(g.zoomed("t", 0, 4) is None, "no more than the whole day")
drw = {"version": 1, "shapes": [{"kind": "line", "p1": [g.X(2), g.Y(1010)], "p2": [g.X(9), g.Y(1030)]},
	{"kind": "rect", "rect": [g.X(3), g.Y(1035), g.X(5) - g.X(3), g.Y(1015) - g.Y(1035)]}]}
m = dataview.mapdrawing(drw, g, z)
check(abs(m["shapes"][0]["p1"][1] - z.Y(1010)) < 0.1 and abs(m["shapes"][1]["rect"][1] - z.Y(1035)) < 0.1, "drawings moved with the prices")
back = dataview.mapdrawing(m, z, z.unzoomed())
check(all(abs(a - b) < 0.2 for a, b in zip(back["shapes"][0]["p1"] + back["shapes"][0]["p2"], drw["shapes"][0]["p1"] + drw["shapes"][0]["p2"])), "and back")
check(dataview.render(data, "d", date(2026, 11, 10), None, 15, None, t, False, jj.news) is not None, "a day drawn zoomed, with its news, without its profile")
check(dataview.render(data, "w", date(2026, 11, 9), None, 15, None, dataview.Geom(data, "w", date(2026, 11, 9)).zoomed("t", 1.5, 0.2), True, jj.news) is not None,
	"a week zoomed in to its hours")

# in the window
w = mainwin.MainWindow(j)
w.show()
app.processEvents()
w.setdatamode(True)
w.showdata(("d", date(2026, 11, 10)), force=True)
app.processEvents()
check("CPI" in w.datapanel.rows[("d", date(2026, 11, 10))].text(0), "the news in the data list")
check(w.notes.toPlainText().startswith("News: Tue 10  08:30 CPI"), "and in the summary")
g = w.datageom
d0 = {"version": 1, "shapes": [{"kind": "line", "p1": [g.X(2), g.Y(1010)], "p2": [g.X(9), g.Y(1030)], "color": "#e53935", "width": 3}]}
w.view.setimage(w.datapath, d0)
w.view.loading = False
w.drawchanged()
key = w.drawkey(w.datakey, 15)
check(key in w.pending, "drawn on the chart")
def wheel(x, y, dy):
	pos = QPointF(w.view.mapFromScene(QPointF(x, y)))
	ev = QWheelEvent(pos, QPointF(w.view.viewport().mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, dy),
		Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
	return w.eventFilter(w.view.viewport(), ev)
check(wheel(g.L + g.pw + 20, g.Y(1020), 120), "a scroll on the price axis taken")
z = w.datageom
check(z.view() is not None and z.top - z.bot < g.top - g.bot, "the prices zoomed in")
line = w.view.drawingdata()["shapes"][0]
check(abs(line["p1"][1] - z.Y(1010)) < 0.5, "the drawing at the same prices")
check(abs(w.pending[key]["shapes"][0]["p1"][1] - g.Y(1010)) < 0.5, "and kept as on the whole chart")
check(not wheel(g.L + 100, g.T + 100, 120), "a scroll on the chart left to the view")
check(wheel(g.L + 300, g.T + g.ph + 15, -120) and w.datageom.view()[2:] == (z.t0, z.t1), "zooming out the times no wider than the day")
w.view.setdrawingsshown(False)
app.processEvents()
check(w.view.hidden and w.datageom is not None, "the profile hidden with the drawings")
w.view.setdrawingsshown(True)
w.savedrawings()
check(abs(data.readdrawing("d", date(2026, 11, 10))["shapes"][0]["p1"][1] - g.Y(1010)) < 0.5, "saved as on the whole chart")
w.pending.clear()
print("ALL OK")
sys.stdout.flush()
os._exit(0)
