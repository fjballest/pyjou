#
# a scroll rail: a thin column on the left of a tree of groups (years,
# months, weeks, days) with a line and a little circle by each row that
# can open or close. Scrolling on it opens the rows around the point
# scrolled (up, more detail) or closes them (down, less), keeping the row
# under the mouse where it is, so it zooms the list in and out there.
#
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QWidget
from shiboken6 import isValid

WIDTH = 14
STEP = 120	# wheel units a step takes (trackpads send less at a time)

class ScrollRail(QWidget):
	def __init__(self, tree, parent=None):
		super().__init__(parent)
		self.tree = tree
		self.acc = 0
		self.setFixedWidth(WIDTH)
		self.setMouseTracking(True)
		self.hot = None	# the row under the mouse
		self.setToolTip("scroll here to open (up) or close (down) the groups of the list there")
		tree.verticalScrollBar().valueChanged.connect(self.changed)
		tree.itemExpanded.connect(self.changed)
		tree.itemCollapsed.connect(self.changed)
		m = tree.model()
		for s in (m.rowsInserted, m.rowsRemoved, m.modelReset, m.layoutChanged):
			s.connect(self.changed)

	def changed(self, *_):
		if isValid(self):
			self.update()

	def fromtree(self, y):
		"""the rail y for tree viewport y"""
		return self.mapFromGlobal(self.tree.viewport().mapToGlobal(QPoint(0, int(y)))).y()

	def ytotree(self, y):
		"""the tree viewport y for rail y"""
		return self.tree.viewport().mapFromGlobal(self.mapToGlobal(QPoint(0, int(y)))).y()

	def itemat(self, y):
		vp = self.tree.viewport()
		return self.tree.itemAt(QPoint(vp.width() // 2, self.ytotree(y)))

	def rows(self):
		"""the visible rows that can open or close, and the rail y of their middles"""
		out = []
		vp = self.tree.viewport()
		it = self.tree.itemAt(QPoint(4, 1))
		while it is not None:
			r = self.tree.visualItemRect(it)
			if r.top() > vp.height():
				break
			if it.childCount() or it.parent() is not None:
				y = self.fromtree(r.center().y())
				out.append((it, y))
			it = self.tree.itemBelow(it)
		return out

	def paintEvent(self, ev):
		p = QPainter(self)
		p.setRenderHint(QPainter.RenderHint.Antialiasing)
		pal = self.palette()
		line = QColor(pal.mid().color())
		top = self.fromtree(0)
		bottom = self.fromtree(self.tree.viewport().height())
		x = WIDTH / 2
		p.setPen(QPen(line, 1))
		p.drawLine(int(x), top, int(x), bottom)
		for it, y in self.rows():
			if not top <= y <= bottom:
				continue
			r = 3.5 if it.childCount() else 2.5
			hot = it is self.hot
			p.setPen(QPen(pal.highlight().color() if hot else line, 1.2))
			p.setBrush(pal.highlight().color() if hot else (pal.base().color() if it.childCount() and not it.isExpanded() else line))
			p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
		p.end()

	def mouseMoveEvent(self, ev):
		it = self.itemat(ev.position().y())
		if it is not self.hot:
			self.hot = it
			self.update()

	def leaveEvent(self, ev):
		self.hot = None
		self.update()

	def wheelEvent(self, ev):
		d = ev.angleDelta().y() or ev.angleDelta().x()
		self.acc += d
		y = ev.position().y()
		while abs(self.acc) >= STEP:
			up = self.acc > 0
			self.acc -= STEP if up else -STEP
			self.step(y, up)
		ev.accept()

	def step(self, y, more):
		"""open (more) or close the groups at rail y, keeping the row there in place"""
		it = self.itemat(y)
		if it is None:
			return
		ty = self.ytotree(y)
		before = self.tree.visualItemRect(it).top()
		anchor = it
		if more:
			if it.childCount() and not it.isExpanded():
				it.setExpanded(True)
			else:	# open its groups, or those of its group
				g = it if it.childCount() else it.parent()
				if g is not None:
					for k in range(g.childCount()):
						c = g.child(k)
						if c.childCount():
							c.setExpanded(True)
		else:
			kids = [it.child(k) for k in range(it.childCount()) if it.child(k).isExpanded()]
			if kids:
				for c in kids:
					c.setExpanded(False)
			elif it.childCount() and it.isExpanded():
				it.setExpanded(False)
			elif it.parent() is not None:
				anchor = it.parent()
				anchor.setExpanded(False)
		# the row scrolled stays under the mouse
		r = self.tree.visualItemRect(anchor)
		sb = self.tree.verticalScrollBar()
		want = before if anchor is it else ty - r.height() // 2
		if r.isValid():
			sb.setValue(sb.value() + r.top() - want)
		self.hot = self.itemat(y)
		self.update()

def withrail(tree):
	"""a widget with tree and its ScrollRail on the left"""
	w = QWidget()
	lay = QHBoxLayout(w)
	lay.setContentsMargins(0, 0, 0, 0)
	lay.setSpacing(0)
	tree.setVerticalScrollMode(tree.ScrollMode.ScrollPerPixel)	# so the row scrolled stays put
	rail = ScrollRail(tree, w)
	lay.addWidget(rail)
	lay.addWidget(tree, 1)
	w.rail = rail
	return w
