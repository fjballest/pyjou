#
# DayJournal: browse a directory of day and week chart snapshots
#
#	python3 dj.py [journaldir]
#
# With --ocr it is the OCR process the window starts (see ocrworker.py).
#
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
	sys.exit(app.exec())

if __name__ == "__main__":
	main()
