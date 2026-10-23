#
# search expressions, as in pylg's text filter: words one after another
# must all match, ! is not, | is or, and parentheses group: "(a b) | !(c d)".
# A word matches, ignoring case, a tag or a whole word of the notes. A final
# lowercase s is optional (EQL finds EQLs) and * matches any letters within
# a word (EQ*). An empty search matches everything.
#
import re

def wordpattern(word):
	wild = "*" in word
	if word.endswith("s") and len(word) > 1:
		word = word[:-1]
	p = r"\w*".join(re.escape(x) for x in word.split("*")) if wild else re.escape(word)
	if not word.endswith("*"):
		p += "(?-i:s)?"
	return re.compile(rf"(?<!\w)(?:{p})(?!\w)", re.IGNORECASE)

class Search:
	"""raises ValueError for a bad expression"""
	def __init__(self, text):
		self.text = text or ""
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
		return ("word", wordpattern(tok))

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
		return self.eval(self.expr, list(entry.tags) + [entry.notes or ""])

	@staticmethod
	def error(text):
		try:
			Search(text)
		except ValueError as e:
			return str(e)
		return None
