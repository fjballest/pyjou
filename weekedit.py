# adjusting a week profile by hand, on its capture: the profile is drawn
# over the image, its points can be dragged, a click on a segment adds a
# point there, a right click on a point removes it, a double click (or
# Return) keeps the result and Esc drops it. It works on the view from
# outside, with event filters, so viewer.py (shared with pylg) is untouched.
from PySide6.QtCore import QEvent, QLineF, QObject, QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsPathItem
from shiboken6 import isValid

COLOR = QColor("#e53935")
GRAB = 8	# how near, in screen pixels, a click must be to a point or segment

class ProfileEditor(QObject):
	def __init__(self, view, px, done):
		"""edit the profile px (points [x, y] of the image) on view; done
		gets the new points, or None when dropped"""
		super().__init__(view)
		self.view = view
		self.done = done
		self.pts = [QPointF(x, y) for x, y in sorted(px)]
		self.drag = None	# the index of the point being dragged
		self.line = self.marks = None
		self.redraw()
		view.viewport().installEventFilter(self)
		view.installEventFilter(self)

	def scale(self):
		"""scene units per screen pixel"""
		m = self.view.transform().m11()
		return 1 / m if m else 1

	def makeitems(self):
		"""the line and the marks of the points, again when the view showed
		the image again (which takes them away)"""
		pen = QPen(COLOR, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
		pen.setCosmetic(True)
		self.line = QGraphicsPathItem()
		self.line.setPen(pen)
		mpen = QPen(QColor("white"), 1.5)
		mpen.setCosmetic(True)
		self.marks = QGraphicsPathItem()
		self.marks.setPen(mpen)
		self.marks.setBrush(QBrush(COLOR))
		for it in (self.line, self.marks):
			it.setZValue(10000)
			self.view.scene().addItem(it)

	def redraw(self):
		if self.line is None or not isValid(self.line) or self.line.scene() is not self.view.scene():
			self.makeitems()
		p = QPainterPath()
		if self.pts:
			p.moveTo(self.pts[0])
			for q in self.pts[1:]:
				p.lineTo(q)
		self.line.setPath(p)
		r = 5 * self.scale()
		m = QPainterPath()
		for q in self.pts:
			m.addEllipse(q, r, r)
		self.marks.setPath(m)

	def pointat(self, p):
		"""the index of the point near scene position p, or None"""
		tol = GRAB * self.scale()
		best = None
		for i, q in enumerate(self.pts):
			d = QLineF(p, q).length()
			if d <= tol and (best is None or d < best[0]):
				best = (d, i)
		return best[1] if best else None

	def segmentat(self, p):
		"""the index of the segment near p (from point i to i+1), or None"""
		tol = GRAB * self.scale()
		for i, (a, b) in enumerate(zip(self.pts, self.pts[1:])):
			ab = b - a
			n = ab.x() ** 2 + ab.y() ** 2
			if n == 0:
				continue
			t = max(0.0, min(1.0, QPointF.dotProduct(p - a, ab) / n))
			if QLineF(p, a + ab * t).length() <= tol:
				return i
		return None

	def moveto(self, i, p):
		"""move point i to p, inside the image and between its neighbours,
		so the profile still goes forward in time"""
		r = self.view.sceneRect()
		x = min(max(p.x(), r.left()), r.right())
		if i > 0:
			x = max(x, self.pts[i-1].x() + 1)
		if i < len(self.pts) - 1:
			x = min(x, self.pts[i+1].x() - 1)
		self.pts[i] = QPointF(x, min(max(p.y(), r.top()), r.bottom()))

	def eventFilter(self, obj, ev):
		t = ev.type()
		if obj is self.view:
			if t == QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_Escape:
				self.finish(False)
				return True
			if t == QEvent.Type.KeyPress and ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
				self.finish(True)
				return True
			return False
		if t == QEvent.Type.MouseButtonDblClick:
			self.finish(True)
			return True
		if t == QEvent.Type.MouseButtonPress:
			p = self.view.mapToScene(ev.position().toPoint())
			i = self.pointat(p)
			if ev.button() == Qt.MouseButton.RightButton:
				if i is not None and len(self.pts) > 2:
					del self.pts[i]
					self.redraw()
				return True
			if ev.button() != Qt.MouseButton.LeftButton:
				return False
			if i is None:
				s = self.segmentat(p)
				if s is not None:	# a new point there
					self.pts.insert(s + 1, p)
					i = s + 1
			if i is not None:
				self.drag = i
				self.moveto(i, p)
				self.redraw()
			return True
		if t == QEvent.Type.MouseMove and self.drag is not None:
			self.moveto(self.drag, self.view.mapToScene(ev.position().toPoint()))
			self.redraw()
			return True
		if t == QEvent.Type.MouseButtonRelease and self.drag is not None:
			self.drag = None
			return True
		if t == QEvent.Type.ContextMenu:
			return True	# the right button removes points here
		if t == QEvent.Type.Wheel:
			self.redraw()	# the marks keep their size on the screen
		return False

	def finish(self, keep):
		"""stop editing: done gets the points kept, or None"""
		self.view.viewport().removeEventFilter(self)
		self.view.removeEventFilter(self)
		for it in (self.line, self.marks):
			if it is not None and isValid(it) and it.scene() is not None:
				it.scene().removeItem(it)
		done, self.done = self.done, None
		if done:
			done([[q.x(), q.y()] for q in self.pts] if keep else None)
