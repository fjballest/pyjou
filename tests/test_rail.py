#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_rail.py
# the scroll rail by the lists: scrolling on it opens and closes the groups
# around the row scrolled, which stays in place.
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

app = QApplication.instance() or QApplication([])
from rail import ScrollRail, withrail

tree = QTreeWidget()
tree.setHeaderHidden(True)
months = []
for m in range(6):
	mi = QTreeWidgetItem([f"Month {m}"])
	tree.addTopLevelItem(mi)
	for w in range(4):
		wi = QTreeWidgetItem([f"Week {m}.{w}"])
		mi.addChild(wi)
		for d in range(5):
			wi.addChild(QTreeWidgetItem([f"Day {m}.{w}.{d}"]))
	months.append(mi)
box = withrail(tree)
box.resize(300, 400)
box.show()
app.processEvents()
rail = box.rail

def y(it):
	"""the rail y of row it"""
	return rail.fromtree(tree.visualItemRect(it).center().y())

def wheel(it, dy):
	pos = QPointF(rail.width() / 2, y(it))
	ev = QWheelEvent(pos, QPointF(rail.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, dy),
		Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
	QApplication.sendEvent(rail, ev)
	app.processEvents()

check(len(rail.rows()) == 6, "a point by each month")
m2 = months[2]
at = y(m2)
wheel(m2, 120)
check(m2.isExpanded() and not months[1].isExpanded() and abs(y(m2) - at) <= 1, "scrolling up on a month opens it, and it stays put")
wheel(m2, 120)
check(all(m2.child(k).isExpanded() for k in range(4)), "and then its weeks")
w1 = m2.child(1)
at = y(w1)
wheel(w1, -120)
check(not w1.isExpanded() and m2.child(0).isExpanded() and abs(y(w1) - at) <= 1, "scrolling down on a week closes it")
d = m2.child(0).child(3)
wheel(d, -120)
check(not m2.child(0).isExpanded(), "on a day, its week")
wheel(m2, -60)
check(m2.child(2).isExpanded(), "half a step does nothing")
wheel(m2, -60)
check(not any(m2.child(k).isExpanded() for k in range(4)) and m2.isExpanded(), "a whole one closes the weeks open first")
wheel(m2, -120)
check(not m2.isExpanded(), "then the month")
rail.grab()
print("ALL OK")
