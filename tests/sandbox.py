#
# keeps the tests away from the user's settings (the recent journals, the
# panels shown, the custom fib levels, the indicators on) and data (the
# indicators imported, the news fetched): on macOS QSettings and
# QStandardPaths ignore HOME and XDG_*, so the tests use files and folders
# of their own. Every test that makes windows imports it before making them.
#
import os
import tempfile

from PySide6.QtCore import QSettings, QStandardPaths

import drawbar
import mainwin

DIR = tempfile.mkdtemp()

def ini(name):
	return lambda: QSettings(os.path.join(DIR, name + ".ini"), QSettings.Format.IniFormat)

mainwin.settings = ini("DayJournal")
drawbar.fibsettings = ini("drawing")

class Paths:
	"""QStandardPaths, with the writable locations in DIR"""
	StandardLocation = QStandardPaths.StandardLocation

	@staticmethod
	def writableLocation(loc):
		d = os.path.join(DIR, "paths", str(int(loc.value)))
		os.makedirs(d, exist_ok=True)
		return d

	def __getattr__(self, name):
		return getattr(QStandardPaths, name)

mainwin.QStandardPaths = Paths
