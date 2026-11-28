#
# DayJournal: browse a directory of day and week chart snapshots
#
#	python3 dj.py [journaldir] [--goto '{"instrument": "NASDAQ", "names": ["NQ*"], "at": 1764340200}']
#
# With --ocr it is the OCR process the window starts (see ocrworker.py).
#
import os
import sys

OCRFLAG = "--ocr"

def main():
	if OCRFLAG in sys.argv:
		# before importing Qt, so torch loads without PySide's import hook
		import ocr
		ocr.serve()
		return
	from PySide6.QtWidgets import QApplication
	from mainwin import MainWindow
	app = QApplication(sys.argv)
	app.setApplicationName("DayJournal")
	app.setOrganizationName("pyjou")
	import link
	goto = None
	if link.GOTOFLAG in sys.argv:	# from RoadBook: a trade to show
		k = sys.argv.index(link.GOTOFLAG)
		goto = link.parse(sys.argv[k + 1]) if k + 1 < len(sys.argv) else None
		del sys.argv[k:k + 2]
	args = [a for a in sys.argv[1:] if not a.startswith("-")]
	w = MainWindow(args[0] if args else None)
	w.show()
	import mainwin
	app.gotoserver = link.serve(app, lambda r: mainwin.gotorequest(r, w))
	if goto is not None:
		from PySide6.QtCore import QTimer
		QTimer.singleShot(0, lambda: mainwin.gotorequest(goto, w))
	code = app.exec()
	finish()
	os._exit(code)

def finish():
	"""what quitting leaves done before the process ends: the indicators'
	thread stopped and the settings written. The process then ends at once
	(os._exit): PySide's own clean up at exit deletes again widgets Qt had
	already deleted with their windows, and crashed on macOS"""
	try:
		import indicators
		indicators.shutdown()
	except Exception:
		pass
	try:
		import mainwin
		mainwin.settings().sync()
	except Exception:
		pass
	sys.stdout.flush()
	sys.stderr.flush()

if __name__ == "__main__":
	main()
