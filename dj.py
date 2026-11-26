#
# DayJournal: browse a directory of day and week chart snapshots
#
#	python3 dj.py [journaldir]
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
	args = [a for a in sys.argv[1:] if not a.startswith("-")]
	w = MainWindow(args[0] if args else None)
	w.show()
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
		from PySide6.QtCore import QSettings
		QSettings("pyjou", "DayJournal").sync()
	except Exception:
		pass
	sys.stdout.flush()
	sys.stderr.flush()

if __name__ == "__main__":
	main()
