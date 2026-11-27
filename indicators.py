"""Pine indicators on the data charts: the scripts imported (kept in DIR,
for every journal), which of them are on and their inputs (remembered in
the settings), and what they draw on a chart, run up to its last candle
shown (see pine). Runs are made in the background: a chart shows what it
has (the last run of the same chart) and is drawn again when they are
done (runner().done).

The rest of the program only calls the functions here, so taking this file
and pine/ out leaves it as it was."""

import json
import os
import shutil
import threading

import numpy as np

import m15

DIR = None	# set by the main window: …/DayJournal/indicators
EXTS = (".txt", ".pine")
KEEP = 40	# runs kept

_settings = None
_cache = {}		# {run key: pine.Result}
_latest = {}	# {(script name, chart key): pine.Result}, the last run of a chart
_lock = threading.Lock()

def setup(dirpath, settings):
	"""where the scripts are kept, and a function giving the QSettings"""
	global DIR, _settings
	DIR = dirpath
	_settings = settings

def folders():
	"""the other folders searched for scripts, in order (after DIR)"""
	if _settings is None:
		return []
	v = _settings().value("indicators/folders", [])
	if isinstance(v, str):
		v = [v] if v else []
	return [str(f) for f in (v or []) if f]

def setfolders(paths):
	if _settings is not None:
		_settings().setValue("indicators/folders", [p for p in dict.fromkeys(paths) if p])

def searched():
	"""the folders scripts are looked for in, in order: DIR, then folders()"""
	return [f for f in [DIR] + folders() if f]

def scripts():
	"""[(name, path)] of the scripts, by name: those imported (in DIR) and
	those in the other folders; the first one found of a name, in the order
	of searched(), is the one"""
	found = {}
	for d in searched():
		try:
			files = os.listdir(d)
		except OSError:
			continue
		for f in files:
			if f.lower().endswith(EXTS) and not f.startswith("."):
				name = os.path.splitext(f)[0]
				p = os.path.join(d, f)
				if name not in found and os.path.isfile(p):
					found[name] = p
	return sorted(found.items(), key=lambda x: x[0].lower())

def imported(name):
	"""whether script name is one imported (in DIR), which can be removed"""
	p = dict(scripts()).get(name)
	return p is not None and DIR is not None and os.path.dirname(os.path.abspath(p)) == os.path.abspath(DIR)

def enabled():
	"""the names of the scripts that are on"""
	if _settings is None:
		return []
	v = _settings().value("indicators/on", [])
	if isinstance(v, str):
		v = [v] if v else []
	have = {n for n, _ in scripts()}
	return [n for n in (v or []) if n in have]

def setenabled(names):
	if _settings is not None:
		_settings().setValue("indicators/on", list(names))

def toggle(name, on):
	names = [n for n in enabled() if n != name]
	if on:
		names.append(name)
	setenabled(names)

def inputs(name):
	"""{input key: value} of script name, where not its default"""
	if _settings is None:
		return {}
	v = _settings().value("indicators/inputs/" + name, "")
	try:
		d = json.loads(v) if v else {}
	except (ValueError, TypeError):
		return {}
	return {k: tuple(x) if isinstance(x, list) else x for k, x in d.items()}

def setinputs(name, values):
	if _settings is not None:
		if values:
			_settings().setValue("indicators/inputs/" + name, json.dumps(values))
		else:
			_settings().remove("indicators/inputs/" + name)

def importfiles(paths):
	"""copy the scripts at paths into DIR, turned on: [names]"""
	os.makedirs(DIR, exist_ok=True)
	names = []
	for p in paths:
		base = os.path.basename(p)
		if not base.lower().endswith(EXTS):
			base += ".txt"
		dest = os.path.join(DIR, base)
		if os.path.abspath(dest) != os.path.abspath(p):
			shutil.copyfile(p, dest)
		names.append(os.path.splitext(base)[0])
	setenabled(list(dict.fromkeys(enabled() + names)))
	return names

def remove(name):
	"""remove script name, if imported (the other folders are left alone)"""
	for n, p in scripts():
		if n == name and imported(n):
			os.remove(p)
	setenabled([n for n in enabled() if n != name])
	setinputs(name, {})

def lastend(g, tf):
	"""the UTC time (s) where the last candle shown on the chart of
	geometry g ends, or None"""
	return g.lastend()

class Job:
	"""the runs a chart needs: todo [(name, path, run key, inputs)]"""
	def __init__(self, chart, data, low, tf, upto, todo):
		self.chart, self.data, self.low, self.tf, self.upto, self.todo = chart, data, low, tf, upto, todo
		self.stop = threading.Event()	# set by cancel()

def compute(job):
	"""make the runs of job (in any thread): {run key: Result}"""
	import pine
	from pine.feed import Feed
	feed = Feed(job.data, job.low, job.upto)
	chart = None
	out = {}
	for name, path, key, values in job.todo:
		if job.stop.is_set():
			break
		with _lock:
			if key in _cache:
				continue
		if chart is None:
			chart = feed.chart(job.tf, pine.NBARS)
		try:
			with open(path, encoding="utf-8", errors="replace") as f:
				script = pine.Script(f.read(), name)
		except OSError as x:
			script = pine.Script("", name)
			script.error = str(x)
		r = pine.run(script, chart, feed, symbol=job.data.symbol or "NQ", inputs=values, stop=job.stop)
		if r.cancelled:
			break
		r.name = name
		with _lock:
			while len(_cache) >= KEEP:
				_cache.pop(next(iter(_cache)))
			_cache[key] = r
			_latest[(name, job.chart)] = r
		out[key] = r
	return out

_runner = None

def runner():
	"""the background runner: its done signal says some runs are done"""
	global _runner
	if _runner is None:
		from PySide6.QtCore import QObject, Signal

		class Runner(QObject):
			done = Signal()

			def __init__(self):
				super().__init__()
				self.jobs = {}	# {chart key: Job}, the last asked for each chart
				self.current = None	# the Job being made
				self.quit = False	# set by shutdown
				self.cond = threading.Condition()
				self.thread = threading.Thread(target=self.loop, daemon=True, name="indicators")
				self.thread.start()

			def submit(self, job):
				with self.cond:
					self.jobs.pop(job.chart, None)
					self.jobs[job.chart] = job
					self.cond.notify()

			def loop(self):
				while True:
					with self.cond:
						while not self.jobs and not self.quit:
							self.cond.wait()
						if self.quit:
							return
						chart = next(iter(self.jobs))
						job = self.current = self.jobs[chart]
					try:
						compute(job)
					except Exception:	# a bug: the chart is left as it is
						import traceback
						traceback.print_exc()
					with self.cond:
						self.current = None
						if self.jobs.get(chart) is job:
							del self.jobs[chart]
					if not job.stop.is_set():
						self.done.emit()

			def cancel(self):
				"""drop the runs asked for, and stop the one being made"""
				with self.cond:
					for job in self.jobs.values():
						job.stop.set()
					self.jobs.clear()
					if self.current is not None:
						self.current.stop.set()

		_runner = Runner()
	return _runner

def needed(data, low, g, tf, names=None):
	"""(chart key, upto, [(name, path, run key, inputs)]) of the scripts on
	for the chart of g: names, or those on (enabled)"""
	upto = lastend(g, tf)
	if upto is None:
		return None, None, []
	chart = (id(data), g.kind, g.d, tf)
	paths = dict(scripts())
	todo = []
	for name in (enabled() if names is None else names):
		p = paths.get(name)
		if p is None:
			continue
		try:
			st = os.stat(p)
		except OSError:
			continue
		values = inputs(name)
		key = (p, st.st_mtime, st.st_size, tf, upto, len(data), len(low) if low is not None else 0, data.symbol,
			json.dumps(values, sort_keys=True))
		todo.append((name, p, key, values))
	return chart, upto, todo

def shutdown(timeout=2):
	"""stop the runs and the background thread, on quitting"""
	r = _runner
	if r is None:
		return
	r.cancel()
	with r.cond:
		r.quit = True
		r.cond.notify_all()
	r.thread.join(timeout)

def cancel():
	"""stop the runs in the background (the chart is being moved)"""
	if _runner is not None:
		_runner.cancel()

def results(data, low, g, tf, wait=True, run=True, names=None):
	"""(the runs of the scripts that are on for the chart of geometry g,
	whether some are still to come): [pine.Result]. Without wait the
	missing ones are run in the background and the last ones of this chart
	are given meanwhile; without run nothing is run, and the last ones of
	the chart are given (while it is being moved). low is the data of the
	lowest time frame, or a function giving it (called only when needed)"""
	if not (enabled() if names is None else names) or data is None or not len(data):
		return [], False
	if callable(low):
		low = low()
	chart, upto, todo = needed(data, low, g, tf, names)
	if not todo:
		return [], False
	with _lock:
		missing = [t for t in todo if t[2] not in _cache]
	if missing and not run:
		pass
	elif missing:
		job = Job(chart, data, low, tf, upto, missing)
		if wait:
			compute(job)
		else:
			runner().submit(job)
	out = []
	with _lock:
		for name, p, key, values in todo:
			r = _cache.get(key)
			if r is None:
				r = _latest.get((name, chart))
			if r is not None:
				out.append(r)
		pending = run and any(key not in _cache for _, _, key, _ in todo)
	return out, pending

def painter(rs, tf):
	"""a function painting runs rs over a chart (fn(painter, geometry)), or None"""
	if not rs:
		return None
	from pine.draw import paint, reach
	from PySide6.QtCore import QRectF, Qt
	from PySide6.QtGui import QColor, QFont

	def fn(p, geom):
		for r in rs:
			paint(p, geom, r, tf)
		bad = [r for r in rs if r.error]
		if bad:
			p.save()
			f = QFont()
			f.setPixelSize(13)
			p.setFont(f)
			p.setPen(QColor(200, 30, 30))
			y = geom.T + geom.ph - 18 * len(bad) - 4
			for r in bad:
				p.drawText(QRectF(geom.L + 6, y, geom.pw - 12, 18), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
					f"{r.title}: {r.error}")
				y += 18
			p.restore()
	far = [x for x in (reach(r, tf) for r in rs) if x is not None]
	fn.reach = max(far) if far else None	# the latest time drawn past the last bar (ms), for room there
	fn.last = max(int(r.S.t[-1]) for r in rs if r.S is not None and r.S.n) if any(r.S is not None and r.S.n for r in rs) else None
	return fn

def overlay(data, low, g, tf, wait=True, run=True, names=None):
	"""(a function painting the indicators that are on over the chart of
	geometry g in tf minutes, or None; whether runs are still to come;
	[error messages]); see results for run"""
	rs, pending = results(data, low, g, tf, wait, run, names)
	return painter(rs, tf), pending, [f"{r.title}: {r.error}" for r in rs if r.error]

def inputsof(name, data, low, g, tf):
	"""([pine.runtime.Input], title) of script name, from its last run
	(made now on the chart of g when there is none)"""
	with _lock:
		for (n, _), r in reversed(list(_latest.items())):
			if n == name and r.inputs:
				return r.inputs, r.title
	path = dict(scripts()).get(name)
	if path is None or g is None or data is None:
		return [], name
	if callable(low):
		low = low()
	chart, upto, todo = needed(data, low, g, tf)
	todo = [t for t in todo if t[0] == name] or [(name, path, ("inputs", path, upto), inputs(name))]
	compute(Job(chart, data, low, tf, upto, todo))
	with _lock:
		r = _cache.get(todo[0][2])
	return (r.inputs, r.title) if r is not None else ([], name)

# ---------------------------------------------------------------- the inputs, as TradingView shows them

def inputsdialog(parent, name, specs, title, accept=None):
	"""ask for the inputs specs of script name: True when they changed.
	accept, for tests, is called with the dialog instead of showing it"""
	from PySide6.QtCore import QDateTime, QTimeZone
	from PySide6.QtGui import QColor, QIcon, QPixmap
	from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox,
		QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox,
		QVBoxLayout, QWidget)
	from pine import runtime as R

	values = inputs(name)
	dlg = QDialog(parent)
	dlg.setWindowTitle(f"{title} — Inputs")
	dlg.resize(600, 680)
	top = QVBoxLayout(dlg)
	area = QScrollArea()
	area.setWidgetResizable(True)
	inner = QWidget()
	form = QFormLayout(inner)
	form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
	area.setWidget(inner)
	top.addWidget(area)
	ny = QTimeZone(b"America/New_York")
	editors = []	# (spec, get, put, widget)

	def qc(c):
		if c is None or R.isna(c):
			return QColor(0, 0, 0, 0)
		return QColor(int(c[0]), int(c[1]), int(c[2]), int(round(255 * (1 - c[3] / 100))))

	def swatch(c):
		pm = QPixmap(28, 16)
		pm.fill(qc(c))
		return QIcon(pm)

	def editor(spec):
		v = values.get(spec.key, spec.defval)
		a = spec.args
		k = spec.kind
		opts = a.get("options")
		if opts and k not in ("bool", "color"):
			w = QComboBox()
			opts = list(opts)
			for o in opts:
				w.addItem(R.tostring(o))
			def get(w=w, opts=opts):
				return opts[w.currentIndex()]
			def put(x, w=w, opts=opts):
				w.setCurrentIndex(opts.index(x) if x in opts else 0)
		elif k == "bool":
			w = QCheckBox(spec.title or "")
			get = w.isChecked
			def put(x, w=w):
				w.setChecked(bool(x))
		elif k == "int":
			w = QSpinBox()
			lo, hi = a.get("minval"), a.get("maxval")
			w.setRange(-10 ** 9 if lo is None or R.isna(lo) else int(lo), 10 ** 9 if hi is None or R.isna(hi) else int(hi))
			w.setSingleStep(int(a.get("step") or 1))
			get = w.value
			def put(x, w=w):
				w.setValue(0 if R.isna(x) else int(x))
		elif k == "float":
			w = QDoubleSpinBox()
			step = str(a.get("step") or "")
			w.setDecimals(min(4, max(2, len(step.split(".")[1].rstrip("0")) if "." in step else 2)))
			lo, hi = a.get("minval"), a.get("maxval")
			w.setRange(-1e12 if lo is None or R.isna(lo) else float(lo), 1e12 if hi is None or R.isna(hi) else float(hi))
			w.setSingleStep(float(a.get("step") or 0.1))
			get = w.value
			def put(x, w=w):
				w.setValue(0.0 if R.isna(x) else float(x))
		elif k == "color":
			w = QPushButton()
			state = {"c": v}
			def get(state=state):
				c = state["c"]
				return R.na if c is None or R.isna(c) else tuple(c)
			def put(x, w=w, state=state):
				state["c"] = x
				w.setIcon(swatch(x))
				w.setText("none" if x is None or R.isna(x) else R.tostring(x) + ("" if not x[3] else f" {100 - x[3]:.0f}%"))
			def pick(_=False, w=w, state=state, put=put):
				q = QColorDialog.getColor(qc(state["c"]), dlg, spec.title or "Color",
					QColorDialog.ColorDialogOption.ShowAlphaChannel)
				if q.isValid():
					put((q.red(), q.green(), q.blue(), round((255 - q.alpha()) / 255 * 100, 2)))
			w.clicked.connect(pick)
		elif k == "time":
			w = QDateTimeEdit()
			w.setDisplayFormat("yyyy-MM-dd HH:mm")
			w.setTimeZone(ny)
			def get(w=w):
				return int(w.dateTime().toMSecsSinceEpoch())
			def put(x, w=w):
				if not R.isna(x):
					w.setDateTime(QDateTime.fromMSecsSinceEpoch(int(x), ny))
		elif k == "source":
			w = QLabel("the chart's")
			w.setEnabled(False)
			get = None
			def put(x):
				pass
		else:
			w = QLineEdit()
			w.setMinimumWidth(180)
			get = w.text
			def put(x, w=w):
				w.setText("" if R.isna(x) else str(x))
		put(v)
		tip = a.get("tooltip")
		if tip and not R.isna(tip):
			w.setToolTip(str(tip))
		if get is not None:
			editors.append((spec, get, put, w))
		return w

	group = None
	row = None
	lastinline = None
	for spec in specs:
		g = spec.args.get("group") or ""
		if g != group:
			group = g
			if g:
				h = QLabel(f"<b>{g}</b>")
				h.setContentsMargins(0, 10, 0, 2)
				form.addRow(h)
			lastinline = None
		inline = spec.args.get("inline")
		w = editor(spec)
		label = "" if spec.kind == "bool" else (spec.title or "")
		if inline and inline == lastinline and row is not None:
			if label:
				row.insertWidget(row.count() - 1, QLabel(label))
			row.insertWidget(row.count() - 1, w)
			continue
		box = QWidget()
		row = QHBoxLayout(box)
		row.setContentsMargins(0, 0, 0, 0)
		if label and inline:
			row.addWidget(QLabel(label))
			label = ""
		row.addWidget(w)
		row.addStretch(1)
		lastinline = inline
		if label:
			form.addRow(QLabel(label), box)
		else:
			form.addRow(box)
	if not specs:
		form.addRow(QLabel("This indicator has no inputs."))

	buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
		| QDialogButtonBox.StandardButton.RestoreDefaults)
	buttons.accepted.connect(dlg.accept)
	buttons.rejected.connect(dlg.reject)
	buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
		lambda: [put(spec.defval) for spec, get, put, w in editors])
	top.addWidget(buttons)
	dlg.editors = editors
	ok = accept(dlg) if accept is not None else dlg.exec() == QDialog.DialogCode.Accepted
	if not ok:
		return False
	out = {}
	for spec, get, put, w in editors:
		x = get()
		d = spec.defval
		same = x == d or (R.isna(x) and R.isna(d)) or (isinstance(d, (int, float)) and isinstance(x, (int, float))
			and not isinstance(d, bool) and not isinstance(x, bool) and abs(x - d) < 1e-9)
		if not same:
			out[spec.key] = list(x) if isinstance(x, tuple) else x
	old = {k: list(v) if isinstance(v, tuple) else v for k, v in inputs(name).items()}
	setinputs(name, out)
	return out != old

# ---------------------------------------------------------------- the other folders

def foldersdialog(parent):
	"""edit the other folders searched for indicators: True when they changed"""
	from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
		QPushButton, QVBoxLayout)
	dlg = QDialog(parent)
	dlg.setWindowTitle("Indicator Folders")
	lay = QVBoxLayout(dlg)
	note = QLabel("Indicators (.txt or .pine) are looked for in the imported ones first, then in these "
		"folders, in this order: the first one found of a name is the one used.")
	note.setWordWrap(True)
	lay.addWidget(note)
	first = QLabel(f"1. {DIR}  (imported)")
	first.setEnabled(False)
	lay.addWidget(first)
	row = QHBoxLayout()
	lst = QListWidget()
	lst.addItems(folders())
	row.addWidget(lst, 1)
	col = QVBoxLayout()
	def add():
		d = QFileDialog.getExistingDirectory(dlg, "Add Indicator Folder", os.path.expanduser("~"))
		if d and d not in [lst.item(i).text() for i in range(lst.count())]:
			lst.addItem(d)
			lst.setCurrentRow(lst.count() - 1)
	def drop():
		r = lst.currentRow()
		if r >= 0:
			lst.takeItem(r)
	def move(k):
		r = lst.currentRow()
		if 0 <= r + k < lst.count() and r >= 0:
			it = lst.takeItem(r)
			lst.insertItem(r + k, it)
			lst.setCurrentRow(r + k)
	for text, fn in (("Add…", add), ("Remove", drop), ("Up", lambda: move(-1)), ("Down", lambda: move(1))):
		b = QPushButton(text)
		b.clicked.connect(fn)
		col.addWidget(b)
	col.addStretch(1)
	row.addLayout(col)
	lay.addLayout(row)
	bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
	bb.accepted.connect(dlg.accept)
	bb.rejected.connect(dlg.reject)
	lay.addWidget(bb)
	dlg.resize(560, 320)
	dlg.list = lst	# for the tests
	if parent is not None:
		parent.foldersdlg = dlg
	ok = dlg.exec()
	if parent is not None:
		parent.foldersdlg = None
	if not ok:
		return False
	new = [lst.item(i).text() for i in range(lst.count())]
	if new == folders():
		return False
	setfolders(new)
	return True
