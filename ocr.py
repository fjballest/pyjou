#
# OCR of the journal images, with easyocr as in pylg. The engine is loaded
# on first use, because it takes a while to start.
#
import json
import os
import sys

LANGS = ["es", "en"]
_reader = None

def reader():
	global _reader
	if _reader is None:
		import easyocr
		try:
			_reader = easyocr.Reader(LANGS, verbose=False)
		except Exception as e:
			print("ocr: falling back to english:", e, file=sys.stderr)
			_reader = easyocr.Reader(["en"], verbose=False)
	return _reader

def readimage(path):
	"""the texts in the image at path, as [(text, confidence)...]"""
	import cv2
	import numpy as np
	# imdecode, because imread doesn't like some paths
	data = np.fromfile(path, dtype=np.uint8)
	img = cv2.imdecode(data, cv2.IMREAD_COLOR)
	if img is None:
		raise ValueError(f"can't read {path}")
	# small text reads better a bit larger
	h, w = img.shape[:2]
	if max(h, w) < 2500:
		img = cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
	return [(text, conf) for _, text, conf in reader().readtext(img)]

def serve(inp=sys.stdin, out=sys.stdout):
	"""the OCR process: reads image paths, one per line, and writes a JSON
	line for each one with what was read, or the error"""
	for line in inp:
		path = line.rstrip("\n")
		if not path:
			continue
		try:
			raw = [[t, float(c)] for t, c in readimage(path)]
			r = {"path": path, "raw": raw}
		except Exception as e:
			r = {"path": path, "error": str(e)}
		out.write(json.dumps(r, ensure_ascii=False) + "\n")
		out.flush()

if __name__ == "__main__":
	# python3 ocr.py image.png...	prints the text and the tags found
	from tags import cleantags
	for p in sys.argv[1:]:
		raw = readimage(p)
		print(f"== {os.path.basename(p)}")
		for t, c in raw:
			print(f"{c:.2f} {t}")
		print("tags:", " ".join(cleantags(raw)))
