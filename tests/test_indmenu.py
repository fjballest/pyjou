#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_indmenu.py
# the Ind menu of the drawing bar: indicators on or off in each window,
# the menu open while clicking, settings on a right click; the bar's icons.
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
import time
from datetime import date, datetime, timezone

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
import m15
import mainwin
import sandbox
import indicators
import ocrworker
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])

j, src = tempfile.mkdtemp(), tempfile.mkdtemp()
start = int(datetime(2026, 11, 22, 23, 0, tzinfo=timezone.utc).timestamp())
with open(os.path.join(src, "MNQ.m15.csv"), "w") as f:
	f.write("time,open,high,low,close\n")
	for k in range(96 * 5):
		p = 1000 + (k % 40)
		f.write(f"{start + 900 * k},{p},{p + 2},{p - 2},{p + 1}\n")
m15.importfile(j, os.path.join(src, "MNQ.m15.csv"))

w = mainwin.MainWindow(j)
for nm in ("Aind", "Bind"):
	with open(os.path.join(src, nm + ".txt"), "w") as f:
		f.write('indicator("%s", overlay = true)\nlabel.new(bar_index, high, "%s")\n' % (nm, nm))
indicators.importfiles([os.path.join(src, "Aind.txt"), os.path.join(src, "Bind.txt")])
w.windowind()	# they appear, on
w.indon = ["Aind"]
w.resize(2200, 800)
w.show()
app.processEvents()
check(not w.indbtnact.isVisible(), "no Ind menu with the captures")
w.setdatamode(True)
w.showdata(("d", date(2026, 11, 24)), force=True)
app.processEvents()
check(w.indbtnact.isVisible() and w.indbtn.text() == "Ind", "the Ind menu on the drawing bar in the data view")
bar = w.drawbar
for a in (bar.undoact, bar.redoact, bar.delact):
	b = bar.widgetForAction(a)
	check(not a.icon().isNull() and b.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly and b.width() < 40,
		a.text() + " as an icon")

def settle():
	end = time.time() + 30
	while w.datapending and time.time() < end:
		app.processEvents()
		time.sleep(0.01)
	app.processEvents()

settle()
def drawn():
	rs, _ = indicators.results(w.data, w.getlow, w.datageom, w.datashowntf, names=w.windowind())
	assert all(r.error is None for r in rs), [r.error for r in rs]
	return sorted(r.title for r in rs)
check(drawn() == ["Aind"], "the window shows the indicators on in it")

m = w.indpopup
m.popup(w.indbtn.mapToGlobal(QPoint(0, w.indbtn.height())))
app.processEvents()
acts = {a.data(): a for a in m.actions() if a.isCheckable()}
check(set(acts) == {"Aind", "Bind"} and acts["Aind"].isChecked() and not acts["Bind"].isChecked(), "the menu lists them, checked when on")
def click(a, button=Qt.MouseButton.LeftButton):
	r = m.actionGeometry(a)
	pos = QPointF(r.center())
	for t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
		ev = QMouseEvent(t, pos, QPointF(m.mapToGlobal(pos.toPoint())), button, button if t == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton,
			Qt.KeyboardModifier.NoModifier)
		QApplication.sendEvent(m, ev)
	app.processEvents()
click(acts["Bind"])
settle()
check(m.isVisible() and acts["Bind"].isChecked() and w.windowind() == ["Aind", "Bind"], "a click turns one on, and the menu stays open")
click(acts["Aind"])
settle()
check(m.isVisible() and w.windowind() == ["Bind"] and drawn() == ["Bind"], "another turns one off, still open")
w2 = w.newwindow()
app.processEvents()
check(w2.windowind() == ["Bind"], "a new window starts with this one's")
w2.setindicator("Aind", True)
check(w.windowind() == ["Bind"] and w2.windowind() == ["Bind", "Aind"], "and each window has its own")
asked = []
w.indicatorinputs = lambda name, accept=None: asked.append(name)
click(acts["Bind"], Qt.MouseButton.RightButton)
end = time.time() + 2
while not asked and time.time() < end:
	app.processEvents()
check(asked == ["Bind"] and not m.isVisible() and w.windowind() == ["Bind"], "a right click opens its settings, without turning it off")
w.fillindicators()
check([a.text() for a in w.indmenu.actions() if a.isCheckable() and a.isChecked()] == ["Bind"], "View ▸ Indicators shows this window's")
w2.close()
print("ALL OK")
os._exit(0)
