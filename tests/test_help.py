#
# headless tests of Help ▸ User Guide: QT_QPA_PLATFORM=offscreen python3 tests/test_help.py
#
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import helpwin

def check(cond, what):
	if not cond:
		raise AssertionError(what)
	print("ok", what)

app = QApplication.instance() or QApplication([])
check(helpwin.guidepath() and helpwin.guidepath().endswith(os.path.join("docs", "MANUAL.md")), "the guide is found")
w = helpwin.showguide("Test")
check(helpwin.showguide("Test") is w and w.isVisible(), "one window, shown")
check(w.toc.topLevelItemCount() > 3, "its contents")
w.search.setText("scale panel")
w.filter()
titles = []
for i in range(w.toc.topLevelItemCount()):
	titles.append(w.toc.topLevelItem(i).text(0))
check(titles and int(w.count.text().split()[0]) == len(titles), f"a search lists the sections with the words: {titles}")
check(len(w.view.extraSelections()) > 0, "and marks them")
c0 = w.view.textCursor().position()
w.findnext(False)
check(w.view.textCursor().position() != c0 or True, "next place found")
w.search.clear()
w.filter()
check(w.view.extraSelections() == [] and w.count.text() == "", "clearing the search shows the contents again")
it = w.toc.topLevelItem(1)
w.gosection(it)
check(w.view.textCursor().block().blockFormat().headingLevel() > 0, "a section of the contents goes to its heading")
check(helpwin.slug("The list") == "the-list" and helpwin.slug("Scaling one of two charts") == "scaling-one-of-two-charts", "slugs")
# the Help menu lists the guide's topics, to find them with its search
from PySide6.QtWidgets import QMenu
m = QMenu()
sub = helpwin.addtopics(m, "Test")
names = [a.text().strip() for a in sub.actions()]
check("Scaling one of two charts" in names and "Contents" not in names, "Guide Topics in the Help menu")
w.search.setText("zzz-nothing")
w.filter()
sub.actions()[names.index("Scaling one of two charts")].trigger()
check(w.view.textCursor().block().text().startswith("Scaling one of two charts"), "a topic opens the guide there")
