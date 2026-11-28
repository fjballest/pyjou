#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_toolbar.py
# The icons of the toolbars, View ▸ Toolbar, and the gear's menu.
#
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["HOME"] = tempfile.mkdtemp()

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import sandbox
import mainwin

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

app = QApplication(sys.argv)
win = mainwin.MainWindow()
win.show()
app.processEvents()
S = Qt.ToolButtonStyle
tb, db = win.journaltb, win.drawbar
style = lambda bar, a: bar.widgetForAction(a).toolButtonStyle()

for a in (win.fitact, win.realact, win.zoominact, win.zoomoutact, win.copyimgact, db.hideact, win.toolsact):
	check(not a.icon().isNull(), f"{a.iconText()} has an icon")
names = [a.text() for a in win.toolsmenu.actions()]
check(names == ["S&wing Times…", "Strategy &Tester…", "Match &Day…", "&Match Week…"], "the gear's menu")

check(style(tb, win.zoominact) == S.ToolButtonTextBesideIcon, "icons and text at first")
check(style(tb, win.toolsact) == S.ToolButtonIconOnly, "the gear is an icon")
check(style(tb, win.dataact) == S.ToolButtonTextOnly or not win.dataact.icon().isNull(), "a button without an icon keeps its text")
win.styleacts["icons"].trigger()
check(style(tb, win.zoominact) == S.ToolButtonIconOnly and style(db, db.copyimgact) == S.ToolButtonIconOnly, "icons only")
if win.dataact.icon().isNull():
	check(style(tb, win.dataact) == S.ToolButtonTextOnly, "still the text of one without an icon")
check(mainwin.settings().value("buttonstyle") == "icons", "kept in the settings")
win.styleacts["text"].trigger()
check(style(tb, win.zoominact) == S.ToolButtonTextOnly and style(tb, win.toolsact) == S.ToolButtonTextOnly
	and style(db, db.undoact) == S.ToolButtonTextOnly, "text only, the gear and undo too")
check(win.styleacts["text"].isChecked() and not win.styleacts["both"].isChecked(), "the menu shows the style")
win2 = mainwin.MainWindow()
check(style(win2.journaltb, win2.zoominact) == S.ToolButtonTextOnly, "a new window has it too")
win.styleacts["both"].trigger()
check(style(win2.journaltb, win2.zoominact) == S.ToolButtonTextBesideIcon, "and follows a change")

key = lambda a: a.icon().pixmap(18, 18).toImage()
shown = key(db.hideact)
win.view.togglehidden()
app.processEvents()
check(db.hideact.text() == "Show" and key(db.hideact) != shown, "the eye changes when the drawings are hidden")
win.view.togglehidden()
app.processEvents()
check(db.hideact.text() == "Hide" and key(db.hideact) == shown, "and back")

# the drawing tools have icons too, and follow the style
tools = list(db.toolacts.values())
check(all(not a.icon().isNull() for a in tools) and not db.detachact.icon().isNull(), "each drawing tool has an icon")
check(len({key(a).bits().tobytes() for a in tools}) == len(tools), "all different")
win.styleacts["icons"].trigger()
check(all(style(db, a) == S.ToolButtonIconOnly for a in tools), "icons only for the tools")
win.styleacts["text"].trigger()
check(all(style(db, a) == S.ToolButtonTextOnly for a in tools) and db.toolacts["line"].text() == "Line",
	"text only, with their plain names")
win.styleacts["both"].trigger()
check(all(style(db, a) == S.ToolButtonTextBesideIcon for a in tools)
	and style(db, db.detachact) == S.ToolButtonIconOnly, "both, and detach keeps to its icon")
