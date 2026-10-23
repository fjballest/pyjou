#
# turning OCR text into tags: keep what looks like words, drop the noise
#
import re

# chart and platform words that are in every snapshot
NOISE = {
	"vender", "comprar", "micro", "e-mini", "mini", "index", "futures", "cme", "cbot",
	"nasdaq-100", "tradingview", "germany", "cash", "ig",
}
MONTHS = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
	"ene", "abr", "ago", "dic", "sept"}
WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun",
	"lun", "mar", "mié", "mie", "jue", "vie", "sáb", "sab", "dom"}
STOP = {
	# spanish
	"de", "del", "la", "las", "el", "los", "lo", "un", "una", "unos", "unas", "y", "o", "en",
	"con", "por", "para", "que", "se", "al", "su", "sus", "es", "como", "más", "mas", "pero",
	"sin", "sobre", "hasta", "desde", "muy", "ya", "le", "les", "me", "mi", "tu", "si", "no",
	# english
	"the", "a", "an", "of", "to", "in", "on", "and", "or", "at", "by", "for", "is", "it",
	"with", "from", "as", "be", "this", "that",
}
VOWELS = set("aeiouyáéíóúü")
TIMEFRAME = re.compile(r"^[mhdw]\d{1,3}$", re.IGNORECASE)	# m15, h1, d1
SPLIT = re.compile(r"[\s/\\,;:()\[\]{}\"'“”‘’!?¡¿|=<>*#@&._-]+")
EDGES = "-.+_~`^%$"

def words(text):
	"""the candidate words of an OCR text"""
	for w in SPLIT.split(text):
		w = w.strip(EDGES)
		if w:
			yield w

def isword(w):
	"""does w look like a word worth a tag?"""
	if len(w) > 24:
		return False
	low = w.lower()
	if low in NOISE or low in MONTHS or low in WEEKDAYS:
		return False
	if low in STOP and not w.isupper():
		return False	# ES (the future) is a tag, es is not
	if TIMEFRAME.match(w):
		return True
	letters = sum(c.isalpha() for c in w)
	if letters < 2 or letters < len(w) / 2:
		return False
	if len(w) == 2 and not w.isupper():
		return False
	if not w.isupper() and not (VOWELS & set(low)):
		return False	# lowercase without vowels is OCR noise
	if re.search(r"(.)\1\1", low):
		return False	# three of the same letter in a row
	if re.search(r"[a-z][A-Z]", w):
		return False	# PtHOG, RfhoG: misread capitals
	return True

def cleantags(raw, minconf=0.3):
	"""tags from OCR results [(text, confidence)...]: the words that look
	like words, without repeating one (ignoring case), in reading order"""
	seen = set()
	tags = []
	for text, conf in raw:
		if conf < minconf:
			continue
		for w in words(text):
			if not isword(w):
				continue
			k = w.lower()
			if k not in seen:
				seen.add(k)
				tags.append(w)
	return tags
