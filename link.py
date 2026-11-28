#
# Other programs ask DayJournal to show a time: RoadBook's DayJournal button
# sends a trade (its instrument, the names it goes by, its entry and exit
# times) to the local socket DayJournal listens on, or starts DayJournal
# with --goto and the same text when it is not running. DayJournal finds the
# journal with data of that instrument and shows the day, zoomed on the
# trade, with lines at its entry and exit.
#
import fnmatch
import glob
import json
import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtNetwork import QLocalServer

import m15

SERVER = "DayJournal-goto"
GOTOFLAG = "--goto"

def symbolof(dir):
	"""the symbol of the data in journal dir (MNQ), or None"""
	for p in sorted(glob.glob(os.path.join(glob.escape(dir), "*.m*.csv*"))):
		return m15.symbolin(os.path.basename(p))
	return None

def matches(sym, names):
	"""whether symbol sym is one of names: an instrument's name and the
	names it goes by, with * for any letters (NQ*, *nasdaq*)"""
	if not sym:
		return False
	s = sym.lower()
	for n in names:
		n = (n or "").strip().lower()
		if n and (fnmatch.fnmatchcase(s, n) or s == n):
			return True
	return False

def journalfor(names, dirs):
	"""the first of journal dirs with data of the instrument of names"""
	for d in dirs:
		if d and os.path.isdir(d) and matches(symbolof(d), names):
			return d
	return None

def parse(text):
	"""the request in text: {instrument, names, at, exitat, dir, trade},
	times in seconds since 1970; None if it is not one"""
	try:
		r = json.loads(text)
	except (TypeError, ValueError):
		return None
	if not isinstance(r, dict) or not isinstance(r.get("at"), (int, float)):
		return None
	names = [str(x) for x in r.get("names") or [] if x]
	if r.get("instrument"):
		names = [str(r["instrument"])] + names
	r["names"] = names
	return r

def serve(app, handle):
	"""listen for requests, calling handle(request) for each one; the
	server, or None if another DayJournal is listening"""
	from PySide6.QtNetwork import QLocalSocket
	probe = QLocalSocket()
	probe.connectToServer(SERVER)
	if probe.waitForConnected(200):
		probe.abort()
		return None	# another one answers
	QLocalServer.removeServer(SERVER)	# one left by a DayJournal that crashed
	srv = QLocalServer(app)
	if not srv.listen(SERVER):
		return None

	def accept():
		while srv.hasPendingConnections():
			s = srv.nextPendingConnection()
			buf = bytearray()

			def read(s=s, buf=buf):
				buf.extend(bytes(s.readAll()))
				if b"\n" in buf:
					line = bytes(buf).split(b"\n")[0].decode("utf-8", "replace")
					s.write(b"ok\n")
					s.flush()
					s.disconnectFromServer()
					r = parse(line)
					if r is not None:
						handle(r)
			s.readyRead.connect(read)
	srv.newConnection.connect(accept)
	return srv

BLUE = QColor(37, 125, 224)

def markpainter(info):
	"""fn(painter, geom) drawing lines at the entry and the exit of a trade
	of RoadBook, with a tag on each"""
	def fn(p, g):
		p.save()
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		f = QFont()
		f.setPixelSize(13)
		p.setFont(f)
		fm = QFontMetricsF(f)
		for at, text in ((info["at"], info.get("label") or "in"), (info.get("exitat"), "out")):
			if at is None:
				continue
			x = g.X(g.tx(at / 1000))
			if not (g.L - 1 <= x <= g.L + g.pw + 1):
				continue
			y0, y1 = g.T, g.T + g.ph
			p.setPen(QPen(BLUE, 1.4, Qt.PenStyle.DashLine))
			p.drawLine(QPointF(x, y0), QPointF(x, y1))
			w, h = fm.horizontalAdvance(text) + 10, fm.height() + 4
			r = QRectF(x - w / 2, y0 + 4, w, h)
			p.fillRect(r, BLUE)
			p.setPen(QColor("white"))
			p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
		p.restore()
	return fn
