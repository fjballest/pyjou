#
# reads the tags of the images that don't have them yet. The OCR runs in a
# separate process (this same program with --ocr), so the window keeps
# working while easyocr runs: in a thread of the Qt app, torch can
# deadlock and takes the interpreter's lock for long stretches.
#
import json
import os
import sys

from PySide6.QtCore import QObject, QProcess, Signal

OCRFLAG = "--ocr"	# as in dj.py

def ocrcommand():
	"""program and arguments to start the OCR process"""
	if getattr(sys, "frozen", False):	# the app built by pyinstaller
		return sys.executable, [OCRFLAG]
	dj = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dj.py")
	return sys.executable, [dj, OCRFLAG]

class OCRWorker(QObject):
	progress = Signal(int, int)		# done, total
	tagged = Signal(str, str, list)	# journal dir, image name, OCR results [[text, conf]...]
	failed = Signal(str, str)		# image name, error
	finished = Signal()

	def __init__(self, dir, paths, parent=None):
		super().__init__(parent)
		self.dir = dir
		self.paths = list(paths)	# [(name, path)...]
		self.names = {p: n for n, p in self.paths}
		self.done = 0
		self.buf = b""
		self.proc = QProcess(self)
		self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedErrorChannel)
		self.proc.readyReadStandardOutput.connect(self.readout)
		self.proc.finished.connect(self.ended)
		self.proc.errorOccurred.connect(self.error)

	def start(self):
		prog, args = ocrcommand()
		self.proc.start(prog, args)
		for _, p in self.paths:
			self.proc.write((p + "\n").encode("utf-8"))
		self.proc.closeWriteChannel()
		self.progress.emit(0, len(self.paths))

	def readout(self):
		self.buf += bytes(self.proc.readAllStandardOutput())
		while b"\n" in self.buf:
			line, self.buf = self.buf.split(b"\n", 1)
			try:
				r = json.loads(line.decode("utf-8"))
			except ValueError:
				continue	# something else printed by the libraries
			name = self.names.get(r.get("path"))
			if name is None:
				continue
			self.done += 1
			if "error" in r:
				self.failed.emit(name, r["error"])
			else:
				self.tagged.emit(self.dir, name, r["raw"])
			self.progress.emit(self.done, len(self.paths))

	def error(self, err):
		if err == QProcess.ProcessError.FailedToStart:
			print("ocr: can't start", ocrcommand(), file=sys.stderr)
			self.finished.emit()

	def ended(self, *_):
		self.readout()
		self.finished.emit()

	def stop(self):
		try:
			self.proc.finished.disconnect(self.ended)
		except (RuntimeError, TypeError):
			pass
		self.proc.kill()
		self.proc.waitForFinished(2000)

def startocr(owner, dir, paths, tagged, progress, done):
	"""start an OCRWorker for paths [(name, path)...]; returns it"""
	w = OCRWorker(dir, paths, owner)
	w.tagged.connect(tagged)
	w.progress.connect(progress)
	w.finished.connect(done)
	w.start()
	return w
