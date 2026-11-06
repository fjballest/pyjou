#
# search expressions, as in pylg's text filter: words one after another
# must all match, ! is not, | is or, and parentheses group: "(a b) | !(c d)".
# A word matches, ignoring case, a tag or a whole word of the notes or
# of the text boxes drawn on the image. A final
# lowercase s is optional (EQL finds EQLs) and * matches any letters within
# a word (EQ*). An empty search matches everything. A word with aliases
# (see parsealiases) also matches any of them, in the same way.
#
import re

def wordre(word):
	"""the regular expression for a word, without the word boundaries"""
	wild = "*" in word
	if word.endswith("s") and len(word) > 1:
		word = word[:-1]
	p = r"\w*".join(re.escape(x) for x in word.split("*")) if wild else re.escape(word)
	if not word.endswith("*"):
		p += "(?-i:s)?"
	return p

def aliaskey(word):
	"""how a word is looked up in the aliases: ignoring case and a final s"""
	w = word.lower()
	return w[:-1] if w.endswith("s") and len(w) > 1 else w

def wordpattern(word, aliases=None):
	"""a whole word, or any of its aliases"""
	words = [word] + list((aliases or {}).get(aliaskey(word), [])) if "*" not in word else [word]
	alts = "|".join(wordre(w) for w in words)
	return re.compile(rf"(?<!\w)(?:{alts})(?!\w)", re.IGNORECASE)

def parsealiases(text):
	"""the aliases in text: lines like "news: NFP, PPI, CPI", where the
	word before : also matches the ones after it (separated by , or ;).
	# starts a comment. A word with several lines gets them all.
	Returns {aliaskey(word): [aliases...]} and the lines it didn't understand."""
	aliases, bad = {}, []
	for n, line in enumerate(text.splitlines(), 1):
		line = line.split("#", 1)[0].strip()
		if not line:
			continue
		word, colon, rest = line.partition(":")
		word = word.strip()
		names = [x.strip() for x in re.split(r"[,;]", rest) if x.strip()]
		if not colon or not word or " " in word or not names:
			bad.append(n)
			continue
		l = aliases.setdefault(aliaskey(word), [])
		l += [x for x in names if x not in l]
	return aliases, bad

class Search:
	"""raises ValueError for a bad expression. aliases are the words each
	word also matches, as parsealiases returns them"""
	def __init__(self, text, aliases=None):
		self.text = text or ""
		self.aliases = aliases or {}
		self.toks = re.findall(r"[!|()]|[^\s!|()]+", self.text)
		self.pos = 0
		self.expr = None
		if self.toks:
			self.expr = self.parseor()
			if self.pos < len(self.toks):
				raise ValueError(f"unexpected {self.toks[self.pos]!r}")

	def peek(self):
		return self.toks[self.pos] if self.pos < len(self.toks) else None

	def parseor(self):
		terms = [self.parseand()]
		while self.peek() == "|":
			self.pos += 1
			terms.append(self.parseand())
		return terms[0] if len(terms) == 1 else ("or", terms)

	def parseand(self):
		terms = []
		while self.peek() not in (None, "|", ")"):
			terms.append(self.parsenot())
		if not terms:
			tok = self.peek()
			raise ValueError("expression missing " + (f"before {tok!r}" if tok else "at the end"))
		return terms[0] if len(terms) == 1 else ("and", terms)

	def parsenot(self):
		tok = self.peek()
		if tok == "!":
			self.pos += 1
			if self.peek() in (None, "|", ")"):
				raise ValueError("! needs something after it")
			return ("not", self.parsenot())
		if tok == "(":
			self.pos += 1
			e = self.parseor()
			if self.peek() != ")":
				raise ValueError("missing )")
			self.pos += 1
			return e
		self.pos += 1
		return ("word", wordpattern(tok, self.aliases))

	@staticmethod
	def eval(e, texts):
		op, arg = e
		if op == "word":
			return any(arg.search(x) for x in texts)
		if op == "not":
			return not Search.eval(arg, texts)
		if op == "and":
			return all(Search.eval(x, texts) for x in arg)
		return any(Search.eval(x, texts) for x in arg)

	def match(self, entry):
		if self.expr is None:
			return True
		return self.eval(self.expr, list(entry.tags) + [entry.notes or "", entry.drawtext or ""])

	@staticmethod
	def error(text, aliases=None):
		try:
			Search(text, aliases)
		except ValueError as e:
			return str(e)
		return None
