#
# an image view that fits the image, zooms with the buttons or double
# clicks (zoom in, zoom in again, back to fit) and pans by dragging
#
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea

DCLICKZOOM = 2.0

class ImageView(QScrollArea):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.label = QLabel()
		self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
		self.setWidget(self.label)
		self.setWidgetResizable(True)
		self.viewport().installEventFilter(self)
		self.pixmap = None
		self.path = None
		self.scale = 1.0
		self.mode = "fit"	# "fit", "real", or "zoom" to keep the scale
		self.dstep = 0
		self.dragpos = None

	def setimage(self, path):
		self.path = path
		p = QPixmap(path) if path else QPixmap()
		self.pixmap = None if p.isNull() else p
		if self.pixmap is None:
			self.label.clear()
			self.label.setText(f"no image {path}" if path else "")
			return
		if self.mode == "fit":
			self.fitscale()
		elif self.mode == "real":
			self.scale = 1.0
		self.update()

	def fitscale(self):
		v = self.maximumViewportSize()
		s = self.pixmap.size()
		self.scale = min(v.width() / s.width(), v.height() / s.height())

	def update(self):
		if self.pixmap:
			self.label.setPixmap(self.pixmap.scaled(self.pixmap.size() * self.scale,
				Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
			self.label.adjustSize()

	def zoom(self, factor):
		if self.pixmap:
			self.mode = "zoom"
			self.scale *= factor
			self.update()

	def zoomat(self, factor, pos):
		"""zoom keeping the image point at viewport pos in place"""
		if not self.pixmap:
			return
		h, v = self.horizontalScrollBar(), self.verticalScrollBar()
		x = (pos.x() + h.value()) / self.scale
		y = (pos.y() + v.value()) / self.scale
		self.zoom(factor)
		h.setValue(round(x * self.scale - pos.x()))
		v.setValue(round(y * self.scale - pos.y()))

	def fit(self):
		if self.pixmap:
			self.mode = "fit"
			self.dstep = 0
			self.fitscale()
			self.update()

	def realsize(self):
		if self.pixmap:
			self.mode = "real"
			self.scale = 1.0
			self.update()

	def resizeEvent(self, ev):
		super().resizeEvent(ev)
		if self.mode == "fit" and self.pixmap:
			self.fitscale()
			self.update()

	def eventFilter(self, src, ev):
		if src is self.viewport():
			t = ev.type()
			if t == QEvent.Type.MouseButtonDblClick and ev.button() == Qt.MouseButton.LeftButton:
				if self.dstep < 2:
					self.dstep += 1
					self.zoomat(DCLICKZOOM, ev.position().toPoint())
				else:
					self.fit()
				return True
			if t == QEvent.Type.MouseButtonPress and ev.buttons() & Qt.MouseButton.LeftButton:
				self.dragpos = ev.pos()
				return True
			if t == QEvent.Type.MouseMove and self.dragpos is not None:
				d = ev.pos() - self.dragpos
				self.dragpos = ev.pos()
				self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
				self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
				return True
			if t == QEvent.Type.MouseButtonRelease:
				self.dragpos = None
				return True
		return super().eventFilter(src, ev)
