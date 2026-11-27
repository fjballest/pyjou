#
# headless tests: QT_QPA_PLATFORM=offscreen python3 tests/test_holidays.py
# market and bank holidays and special days: reckoned, read from the NYSE's
# and the Fed's calendars, as tags and on the data and capture lists.
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

# the NYSE's calendar and the Fed's, as their pages had them (Nov 2026)
NYSE = """<html><body><table class="x"><thead><tr><th>Holiday</th><th>2026</th><th>2027</th><th>2028</th></tr></thead><tbody>
<tr><th>New Year’s Day</th><td>Thursday, January 1</td><td>Friday, January 1</td><td>—*</td></tr>
<tr><th>Martin Luther King, Jr. Day</th><td>Monday, January 19</td><td>Monday, January 18</td><td>Monday, January 17</td></tr>
<tr><th>Washington&#x27;s Birthday</th><td>Monday, February 16</td><td>Monday, February 15</td><td>Monday, February 21</td></tr>
<tr><th>Good Friday</th><td>Friday, April 3</td><td>Friday, March 26</td><td>Friday, April 14</td></tr>
<tr><th>Memorial Day</th><td>Monday, May 25</td><td>Monday, May 31</td><td>Monday, May 29</td></tr>
<tr><th>Juneteenth National Independence Day</th><td>Friday, June 19</td><td>Friday, June 18 (Juneteenth National Independence Day observed)</td><td>Monday, June 19</td></tr>
<tr><th>Independence Day</th><td>Friday, July 3 (Independence Day observed) </td><td>Monday, July 5 (Independence Day observed) </td><td>Tuesday, July 4**</td></tr>
<tr><th>Labor Day</th><td>Monday, September 7</td><td>Monday, September 6</td><td>Monday, September 4</td></tr>
<tr><th>Thanksgiving Day</th><td>Thursday, November 26***</td><td>Thursday, November 25***</td><td>Thursday, November 23*** </td></tr>
<tr><th>Christmas Day</th><td>Friday, December 25****</td><td>Friday, December 24 (Christmas Day observed)</td><td>Monday, December 25</td></tr>
</tbody></table>
<p>* Because the holiday falls on Saturday, January 1, 2028, no New Year's Day holiday is observed.</p>
<p>** Early close at 1:00 p.m. (1:15 p.m. for eligible options) on Monday, July 3, 2028. Late sessions close at 5:00 p.m.</p>
<p>*** Early close at 1:00 p.m. on Friday, November 27, 2026, Friday, November 26, 2027, and Friday, November 24, 2028 (the day after Thanksgiving). Late sessions close at 5:00 p.m.</p>
<p>**** Early close at 1:00 p.m. on Thursday, December 24, 2026. Late sessions close at 5:00 p.m.</p></body></html>"""
FED = """<table class="table table--noBorder table-layout"><thead><tr><td>&nbsp;</td>
<th scope="col"><h6>2026</h6></th><th scope="col"><h6>2027</h6></th><th scope="col"><h6>2028</h6></th><th scope="col"><h6>2029</h6></th><th scope="col"><h6>2030</h6></th></tr></thead><tbody>
<tr><th scope="row">New Year's Day</th><td>January 1</td><td>January 1</td><td>January 1*</td><td>January 1</td><td>January 1</td></tr>
<tr><th scope="row">Birthday of Martin Luther King, Jr.</th><td>January 19</td><td>January 18</td><td>January 17</td><td>January 15</td><td>January 21</td></tr>
<tr><th scope="row">Washington's Birthday</th><td>February 16</td><td>February 15</td><td>February 21</td><td>February 19</td><td>February 18</td></tr>
<tr><th scope="row">Memorial Day</th><td>May 25</td><td>May 31</td><td>May 29</td><td>May 28</td><td>May 27</td></tr>
<tr><th scope="row">Juneteenth National Independence Day</th><td>June 19</td><td>June 19*</td><td>June 19</td><td>June 19</td><td>June 19</td></tr>
<tr><th scope="row">Independence Day</th><td>July 4*</td><td>July 4**</td><td>July 4</td><td>July 4</td><td>July 4</td></tr>
<tr><th scope="row">Labor Day</th><td>September 7</td><td>September 6</td><td>September 4</td><td>September 3</td><td>September 2</td></tr>
<tr><th scope="row">Columbus Day</th><td>October 12</td><td>October 11</td><td>October 9</td><td>October 8</td><td>October 14</td></tr>
<tr><th scope="row">Veterans Day</th><td>November 11</td><td>November 11</td><td>November 11*</td><td>November 11**</td><td>November 11</td></tr>
<tr><th scope="row">Thanksgiving Day</th><td>November 26</td><td>November 25</td><td>November 23</td><td>November 22</td><td>November 28</td></tr>
<tr><th scope="row">Christmas Day</th><td>December 25</td><td>December 25*</td><td>December 25</td><td>December 25</td><td>December 25</td></tr>
</tbody></table>"""

h = news.holidays(2026)
check(h[date(2026, 11, 26)] == "Thanksgiving" and h[date(2026, 11, 27)] == "BlackFriday" and h[date(2026, 4, 3)] == "GoodFriday",
	"holidays reckoned from their rules, with the special days")
check(h[date(2026, 7, 3)] == "IndependenceDay" and date(2026, 7, 4) not in h and h[date(2026, 12, 24)] == "ChristmasEve",
	"kept on the Friday when on a Saturday")
check(news.holidays(2027)[date(2027, 12, 24)] == "Christmas" and date(2027, 12, 31) not in news.holidays(2027)
	and date(2028, 1, 1) not in news.holidays(2028), "no New Year's Day kept when it is a Saturday, as the NYSE does")
check(news.holidays(2025)[date(2025, 1, 9)] == "Mourning", "and the days closed out of the rules")
nyse = news.tabledates(NYSE) + news.earlycloses(NYSE)
reckoned = {}
for y in (2026, 2027, 2028):
	reckoned.update(news.holidays(y))
check(len(nyse) == 34 and all(reckoned.get(d) == n for d, n in nyse), "the NYSE's calendar, its early closes too, as reckoned")
check((date(2028, 7, 3), "July3") in nyse and (date(2027, 11, 26), "BlackFriday") in nyse, "the early closes named")
fed = news.tabledates(FED, fed=True)
check((date(2027, 7, 5), "IndependenceDay") in fed and (date(2026, 10, 12), "ColumbusDay") in fed
	and not any(d == date(2028, 1, 1) or d == date(2027, 12, 31) for d, _ in fed), "the Fed's: Sunday's on Monday, Saturday's not kept")

# fetched, kept, read
def fake(url):
	if "nyse" in url:
		return NYSE
	if "federalreserve.gov/aboutthefed" in url:
		return FED.replace("October 12", "October 13")	# a day the page moved
	raise OSError("refused")
dd = tempfile.mkdtemp()
news.FETCHED = os.path.join(dd, "news.txt")
res = news.fetchholidays(news.holpath(), fake)
check(res == {"Holidays (NYSE)": 34, "Holidays (Fed)": 50}, "both calendars read: " + str(res))
n = news.News()
check(n.holiday(date(2026, 10, 13)) == "ColumbusDay", "the days fetched are used")
res = news.fetch(None, fake)
check(res["Holidays (NYSE)"] == 34 and res["FOMC"] == "refused", "Update News Dates reads the holidays too")
j0 = tempfile.mkdtemp()
with open(os.path.join(j0, news.NEWSFILE), "w") as f:
	f.write("2026-12-31 Hday\n-2026-11-27 BlackFriday\n2026-11-20 Mourning\n")
n = news.News(j0)
check(n.holiday(date(2026, 12, 31)) == "Hday" and n.holiday(date(2026, 11, 27)) is None and n.holiday(date(2026, 11, 20)) == "Mourning",
	"a journal adds or takes away holidays in its news.txt")
n = news.News()
check(n.names(date(2026, 11, 26)) == ["Thanksgiving", "Holiday"], "a holiday's tags: its name, and Holiday")
check(n.marks(date(2026, 11, 26)) == "Thksg" and n.marks(date(2026, 11, 10)) == "CPI", "on the lists, abbreviated")
check(n.marks(date(2026, 11, 23), True) == "Thksg BlkFri", "a week's: those of its days")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
import journal
import mainwin
import sandbox
import m15
import ocrworker
ocrworker.ocrcommand = lambda: (sys.executable, ["-c", "import sys\nfor l in sys.stdin: pass"])

j = tempfile.mkdtemp()
img = QImage(800, 450, QImage.Format.Format_RGB32)
img.fill(QColor(240, 240, 230))
img.save(os.path.join(j, "day261126.png"))
img.save(os.path.join(j, "day261110.png"))
img.save(os.path.join(j, "day261122weekprof.png"))
jj = journal.Journal(j)
check(jj.find("day261126.png").tags == ["Thanksgiving", "Holiday"], "a capture on a holiday has its name as a tag")
src = tempfile.mkdtemp()
start = int(datetime(2026, 11, 22, 23, 0, tzinfo=timezone.utc).timestamp())	# Sunday 22 Nov 18:00 New York
with open(os.path.join(src, "MNQ.m15.csv"), "w") as f:
	f.write("time,open,high,low,close\n")
	for k in range(96 * 5):
		p = 1000 + (k % 40)
		f.write(f"{start + 900 * k},{p},{p + 2},{p - 2},{p + 1}\n")
m15.importfile(j, os.path.join(src, "MNQ.m15.csv"))

w = mainwin.MainWindow(j)
w.show()
app.processEvents()
texts = {}
def walk(it):
	texts[it.data(0, 0x0100)] = it.text(0)
	for k in range(it.childCount()):
		walk(it.child(k))
for k in range(w.list.topLevelItemCount()):
	walk(w.list.topLevelItem(k))
check(texts.get("day261126.png", "").startswith("Thu 26  · Thksg"), "the captures list marks it: " + texts.get("day261126.png", ""))
check("· CPI" in texts.get("day261110.png", ""), "and the news days")
check("· Thksg BlkFri" in texts.get("day261122weekprof.png", ""), "and a week profile, those of its week")
w.setdatamode(True)
w.showdata(("d", date(2026, 11, 26)), force=True)
app.processEvents()
row = w.datapanel.rows[("d", date(2026, 11, 26))].text(0)
check("· Thksg" in row, "the data list too: " + row)
check("· Thksg BlkFri" in w.datapanel.rows[("w", date(2026, 11, 23))].text(0), "and its weeks")
check("Thanksgiving" in w.tagslabel.text(), "the chart's tags name it")
from PySide6.QtCore import QDate
def bg(d):
	return w.calendar.dateTextFormat(QDate(d.year, d.month, d.day)).background().color()
check(bg(date(2026, 11, 26)) == w.HOLIDAYBG and bg(date(2026, 11, 10)) == w.NEWSBG and bg(date(2026, 11, 24)) not in (w.HOLIDAYBG, w.NEWSBG),
	"the calendar: holidays in red, news days in green")
check(w.calendar.dateTextFormat(QDate(2026, 11, 26)).fontWeight() == 700, "still bold where there is data")
w.setdatamode(False)
app.processEvents()
check(bg(date(2026, 11, 26)) == w.HOLIDAYBG and w.calendar.dateTextFormat(QDate(2026, 11, 26)).fontWeight() == 700, "and with the captures")
print("ALL OK")
os._exit(0)
