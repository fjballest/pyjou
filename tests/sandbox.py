#
# keeps the tests away from the user's settings (the recent journals, the
# panels shown, the custom fib levels): on macOS QSettings ignores HOME and
# XDG_CONFIG_HOME, so the tests use files of their own. Import it before
# making windows.
#
import os
import tempfile

from PySide6.QtCore import QSettings

import drawbar
import mainwin

DIR = tempfile.mkdtemp()

def ini(name):
	return lambda: QSettings(os.path.join(DIR, name + ".ini"), QSettings.Format.IniFormat)

mainwin.settings = ini("DayJournal")
drawbar.fibsettings = ini("drawing")
