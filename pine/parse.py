"""The subset of Pine Script v6 the indicators use, parsed into a tree of
tuples: statements and expressions whose first item is their kind.

Lines: a line indented by a multiple of 4 spaces (a tab is 4) more than
its block starts a block; one indented otherwise, one inside open brackets,
one that starts with a binary operator or follows a line ending in one or
in a comma continues the line before."""

import re

class PineError(Exception):
	def __init__(self, msg, line=None):
		super().__init__(f"line {line}: {msg}" if line else msg)
		self.line = line

TOKEN = re.compile(r"""
 (?P<ws>[ \t]+)
|(?P<comment>//.*)
|(?P<num>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
|(?P<str>"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')
|(?P<color>\#[0-9a-fA-F]{8}|\#[0-9a-fA-F]{6})
|(?P<id>[A-Za-z_][A-Za-z_0-9]*)
|(?P<op>:=|\+=|-=|\*=|/=|%=|=>|==|!=|<=|>=|[-+*/%<>=?:,.()\[\]])
""", re.X)

BINARY = {"and", "or", "?", ":", "*", "/", "%", "==", "!=", "<", ">", "<=", ">=", "+", "-"}
ENDING = BINARY | {",", "=", ":=", "+=", "-=", "*=", "/=", "%=", "("}
ASSIGN = {":=", "+=", "-=", "*=", "/=", "%="}

class Tok:
	__slots__ = ("k", "v", "line")
	def __init__(self, k, v, line):
		self.k, self.v, self.line = k, v, line
	def __repr__(self):
		return f"{self.k}:{self.v}"

def unquote(s):
	body = s[1:-1]
	out = []
	i = 0
	while i < len(body):
		ch = body[i]
		if ch == "\\" and i + 1 < len(body):
			n = body[i + 1]
			out.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'"}.get(n, "\\" + n))
			i += 2
		else:
			out.append(ch)
			i += 1
	return "".join(out)

def tokenize(line, no):
	toks = []
	pos = 0
	while pos < len(line):
		m = TOKEN.match(line, pos)
		if not m:
			raise PineError(f"unexpected {line[pos]!r}", no)
		pos = m.end()
		k = m.lastgroup
		if k in ("ws", "comment"):
			continue
		v = m.group()
		if k == "num":
			v = float(v) if any(c in v for c in ".eE") else int(v)
		elif k == "str":
			v = unquote(v)
		toks.append(Tok(k, v, no))
	return toks

class Line:
	__slots__ = ("indent", "toks", "no")
	def __init__(self, indent, toks, no):
		self.indent, self.toks, self.no = indent, toks, no

def lines(src):
	"""the logical lines of src: [Line(indent level, tokens, line number)]"""
	out = []
	depth = 0
	for no, raw in enumerate(src.replace("\r", "").split("\n"), 1):
		raw = raw.expandtabs(4)
		toks = tokenize(raw, no)
		if not toks:
			continue
		spaces = len(raw) - len(raw.lstrip(" "))
		first = toks[0]
		cont = out and (depth > 0 or spaces % 4 != 0
			or (first.k in ("op", "id") and first.v in BINARY and first.v not in ("-", "+") and spaces > 0)
			or (out[-1].toks[-1].k in ("op", "id") and out[-1].toks[-1].v in ENDING))
		for t in toks:
			if t.k == "op":
				if t.v in "([":
					depth += 1
				elif t.v in ")]":
					depth = max(0, depth - 1)
		if cont:
			out[-1].toks.extend(toks)
		else:
			out.append(Line(spaces // 4, toks, no))
	return out

END = Tok("end", None, 0)

class Parser:
	def __init__(self, src):
		self.lines = lines(src)
		self.li = 0
		self.toks = []
		self.p = 0
		self.site = 0

	# tokens of the current line
	def peek(self, k=0):
		i = self.p + k
		return self.toks[i] if i < len(self.toks) else END

	def isop(self, v, k=0):
		t = self.peek(k)
		return t.k == "op" and t.v == v

	def isid(self, v=None, k=0):
		t = self.peek(k)
		return t.k == "id" and (v is None or t.v == v)

	def next(self):
		t = self.peek()
		self.p += 1
		return t

	def err(self, msg):
		t = self.peek()
		no = t.line or (self.lines[self.li].no if self.li < len(self.lines) else None)
		raise PineError(msg, no)

	def expect(self, v):
		t = self.next()
		if t.v != v or t.k not in ("op", "id"):
			self.p -= 1
			self.err(f"expected {v!r}, found {t.v!r}")
		return t

	def ident(self):
		t = self.next()
		if t.k != "id":
			self.p -= 1
			self.err(f"expected a name, found {t.v!r}")
		return t.v

	def atend(self):
		return self.p >= len(self.toks)

	def newsite(self):
		self.site += 1
		return self.site

	# lines and blocks
	def program(self):
		body = self.block(0)
		if self.li < len(self.lines):
			self.li, self.toks, self.p = self.li, self.lines[self.li].toks, 0
			self.err("unexpected indentation")
		return body

	def block(self, level):
		out = []
		while self.li < len(self.lines):
			ln = self.lines[self.li]
			if ln.indent < level:
				break
			if ln.indent > level:
				self.toks, self.p = ln.toks, 0
				self.err("unexpected indentation")
			self.li += 1
			self.toks, self.p = ln.toks, 0
			s = self.statement(level)
			if s is not None:
				out.append(s)
				if not self.atend():
					self.err(f"unexpected {self.peek().v!r}")
		return out

	def sub(self, level):
		"""the block under the current line, at level + 1"""
		if self.li < len(self.lines) and self.lines[self.li].indent > level:
			toks, p = self.toks, self.p
			b = self.block(level + 1)
			self.toks, self.p = toks, p
			return b
		return []

	def restline(self, level):
		"""the statements after => on this line, or the block under it"""
		if not self.atend():
			return [self.simple(level)]
		return self.sub(level)

	# statements
	def statement(self, level):
		line = self.peek().line
		if self.isid("import"):
			self.p = len(self.toks)
			return None
		if self.isid("export"):
			self.next()
		if self.isid("type") and self.peek(1).k == "id" and not self.isop("=", 1):
			return self.typedef(level)
		if self.isid("method") and self.peek(1).k == "id":
			self.next()
			return self.funcdef(level, True, line)
		if self.peek().k == "id" and self.isop("(", 1) and self.isfuncdef():
			return self.funcdef(level, False, line)
		if self.isid("indicator") or self.isid("strategy") or self.isid("library"):
			e = self.expr()
			return ("indicator", e, line)
		return self.simple(level)

	def isfuncdef(self):
		depth = 0
		i = self.p + 1
		while i < len(self.toks):
			t = self.toks[i]
			if t.k == "op" and t.v in "([":
				depth += 1
			elif t.k == "op" and t.v in ")]":
				depth -= 1
				if depth == 0:
					return i + 1 < len(self.toks) and self.toks[i + 1].k == "op" and self.toks[i + 1].v == "=>"
			i += 1
		return False

	def typedef(self, level):
		line = self.next().line
		name = self.ident()
		fields = []
		toks, p = self.toks, self.p
		while self.li < len(self.lines) and self.lines[self.li].indent > level:
			ln = self.lines[self.li]
			self.li += 1
			self.toks, self.p = ln.toks, 0
			if self.isid("varip"):
				self.next()
			typ = self.typ()
			fname = self.ident()
			default = None
			if self.isop("="):
				self.next()
				default = self.expr()
			fields.append((typ, fname, default))
		self.toks, self.p = toks, p
		return ("type", name, fields, line)

	def typ(self):
		"""a type: float, array<line>, map<string, float>, chart.point, int[]"""
		name = self.ident()
		while self.isop(".") and self.peek(1).k == "id":
			self.next()
			name += "." + self.ident()
		args = []
		if self.isop("<"):
			self.next()
			args.append(self.typ())
			while self.isop(","):
				self.next()
				args.append(self.typ())
			self.expect(">")
		if self.isop("[") and self.isop("]", 1):
			self.next()
			self.next()
			args = [name]
			name = "array"
		return (name, tuple(args))

	def funcdef(self, level, method, line):
		name = self.ident()
		self.expect("(")
		params = []
		while not self.isop(")"):
			while self.isid() and self.peek().v in ("simple", "series", "const"):
				self.next()
			if self.peek(1).k == "id" or self.isop("<", 1) or self.isop(".", 1) or (self.isop("[", 1) and self.isop("]", 2)):
				typ = self.typ()
			else:
				typ = None
			pname = self.ident()
			default = None
			if self.isop("="):
				self.next()
				default = self.expr()
			params.append((typ, pname, default))
			if self.isop(","):
				self.next()
		self.expect(")")
		self.expect("=>")
		body = self.restline(level)
		return ("func", name, params, body, method, line)

	def simple(self, level):
		"""a statement that is not a definition"""
		line = self.peek().line
		t = self.peek()
		if t.k == "id":
			if t.v == "if":
				return self.ifst(level)
			if t.v == "for":
				return self.forst(level)
			if t.v == "while":
				self.next()
				cond = self.expr()
				return ("while", cond, self.sub(level), line)
			if t.v == "switch":
				return self.switchst(level)
			if t.v == "break":
				self.next()
				return ("break", line)
			if t.v == "continue":
				self.next()
				return ("continue", line)
		if self.isop("["):
			names = self.tuplenames()
			if names is not None:
				op = self.next().v
				return ("tdecl", names, self.rhs(level), op, line)
		d = self.decl()
		if d is not None:
			mode, typ, name = d
			return ("decl", mode, typ, name, self.rhs(level), line)
		e = self.expr()
		if self.peek().k == "op" and self.peek().v in ASSIGN:
			op = self.next().v
			return ("assign", e, op, self.rhs(level), line)
		return ("expr", e, line)

	def tuplenames(self):
		"""[a, b, c] = ...: the names, or None (the tokens are left as they were)"""
		p = self.p
		self.next()
		names = []
		while True:
			if not self.isid():
				self.p = p
				return None
			names.append(self.next().v)
			if self.isop(","):
				self.next()
				continue
			if self.isop("]"):
				self.next()
				break
			self.p = p
			return None
		if self.isop("=") or self.isop(":="):
			return names
		self.p = p
		return None

	def decl(self):
		"""a declaration's start: (var/varip/None, type, name) before its =, or None"""
		p = self.p
		mode = None
		if self.isid("var") or self.isid("varip"):
			mode = self.next().v
		while self.isid() and self.peek().v in ("const", "simple", "series"):
			self.next()
		if self.isid() and self.isop("=", 1):
			name = self.next().v
			self.next()
			return mode, None, name
		if self.isid():
			q = self.p
			try:
				typ = self.typ()
				if self.isid() and self.isop("=", 1):
					name = self.next().v
					self.next()
					return mode, typ, name
			except PineError:
				pass
			self.p = q
		if mode is not None:
			self.err("expected a declaration")
		self.p = p
		return None

	def rhs(self, level):
		"""the value of a declaration or assignment: an expression or an if,
		switch, for or while block"""
		t = self.peek()
		if t.k == "id" and t.v in ("if", "switch", "for", "while"):
			return ("block", self.simple(level))
		return self.expr()

	def ifst(self, level):
		line = self.next().line
		cond = self.expr()
		body = self.sub(level)
		other = []
		if self.li < len(self.lines):
			ln = self.lines[self.li]
			if ln.indent == level and ln.toks[0].k == "id" and ln.toks[0].v == "else":
				self.li += 1
				toks, p = self.toks, self.p
				self.toks, self.p = ln.toks, 1
				if self.isid("if"):
					other = [self.ifst(level)]
				else:
					other = self.sub(level)
				if not self.atend():
					self.err(f"unexpected {self.peek().v!r}")
				self.toks, self.p = toks, len(toks)
		return ("if", cond, body, other, line)

	def forst(self, level):
		line = self.next().line
		if self.isop("["):
			self.next()
			i = self.ident()
			self.expect(",")
			v = self.ident()
			self.expect("]")
			self.expect("in")
			return ("forin", i, v, self.expr(), self.sub(level), line)
		v = self.ident()
		if self.isid("in"):
			self.next()
			return ("forin", None, v, self.expr(), self.sub(level), line)
		self.expect("=")
		a = self.expr()
		self.expect("to")
		b = self.expr()
		step = None
		if self.isid("by"):
			self.next()
			step = self.expr()
		return ("for", v, a, b, step, self.sub(level), line)

	def switchst(self, level):
		line = self.next().line
		subject = None if self.atend() else self.expr()
		cases = []
		toks, p = self.toks, self.p
		while self.li < len(self.lines) and self.lines[self.li].indent == level + 1:
			ln = self.lines[self.li]
			self.li += 1
			self.toks, self.p = ln.toks, 0
			if self.isop("=>"):
				self.next()
				cond = None
			else:
				cond = self.expr()
				self.expect("=>")
			cases.append((cond, self.restline(level + 1)))
			if not self.atend():
				self.err(f"unexpected {self.peek().v!r}")
		self.toks, self.p = toks, p
		return ("switch", subject, cases, line)

	# expressions
	def expr(self):
		c = self.orx()
		if self.isop("?"):
			self.next()
			a = self.expr()
			self.expect(":")
			b = self.expr()
			return ("tern", c, a, b)
		return c

	def orx(self):
		a = self.andx()
		while self.isid("or"):
			self.next()
			a = ("or", a, self.andx())
		return a

	def andx(self):
		a = self.eqx()
		while self.isid("and"):
			self.next()
			a = ("and", a, self.eqx())
		return a

	def eqx(self):
		a = self.relx()
		while self.isop("==") or self.isop("!="):
			op = self.next().v
			a = ("bin", op, a, self.relx())
		return a

	def relx(self):
		a = self.addx()
		while self.peek().k == "op" and self.peek().v in ("<", ">", "<=", ">="):
			op = self.next().v
			a = ("bin", op, a, self.addx())
		return a

	def addx(self):
		a = self.mulx()
		while self.isop("+") or self.isop("-"):
			op = self.next().v
			a = ("bin", op, a, self.mulx())
		return a

	def mulx(self):
		a = self.unary()
		while self.peek().k == "op" and self.peek().v in ("*", "/", "%"):
			op = self.next().v
			a = ("bin", op, a, self.unary())
		return a

	def unary(self):
		if self.isop("-") or self.isop("+"):
			op = self.next().v
			e = self.unary()
			if op == "-" and e[0] == "num":
				return ("num", -e[1])
			return ("neg", e) if op == "-" else e
		if self.isid("not"):
			self.next()
			return ("not", self.unary())
		return self.postfix()

	def postfix(self):
		e = self.primary()
		while True:
			if self.isop("."):
				self.next()
				e = ("attr", e, self.ident())
			elif self.isop("<") and e[0] in ("attr", "name") and self.isgeneric():
				self.next()
				targs = [self.typ()]
				while self.isop(","):
					self.next()
					targs.append(self.typ())
				self.expect(">")
				if not self.isop("("):
					self.err("expected (")
				e = self.call(e, targs)
			elif self.isop("("):
				e = self.call(e, [])
			elif self.isop("["):
				self.next()
				k = self.expr()
				self.expect("]")
				e = ("hist", e, k, self.newsite())
			else:
				return e

	def isgeneric(self):
		"""whether the < after a name opens type arguments: array.new<float>("""
		depth = 0
		i = self.p
		while i < len(self.toks):
			t = self.toks[i]
			if t.k == "op" and t.v == "<":
				depth += 1
			elif t.k == "op" and t.v == ">":
				depth -= 1
				if depth == 0:
					return i + 1 < len(self.toks) and self.toks[i + 1].k == "op" and self.toks[i + 1].v == "("
			elif not (t.k == "id" or (t.k == "op" and t.v in (",", ".", "[", "]"))):
				return False
			i += 1
		return False

	def call(self, f, targs):
		line = self.next().line
		args, kw = [], []
		while not self.isop(")"):
			if self.isid() and self.isop("=", 1):
				name = self.next().v
				self.next()
				kw.append((name, self.expr()))
			else:
				if kw:
					self.err("a positional argument after a named one")
				args.append(self.expr())
			if self.isop(","):
				self.next()
			elif not self.isop(")"):
				self.err(f"expected , or ), found {self.peek().v!r}")
		self.expect(")")
		return ("call", f, args, kw, targs, self.newsite(), line)

	def primary(self):
		t = self.next()
		if t.k == "num":
			return ("num", t.v)
		if t.k == "str":
			return ("str", t.v)
		if t.k == "color":
			h = t.v[1:]
			r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
			a = int(h[6:8], 16) if len(h) == 8 else 255
			return ("color", (r, g, b, round((255 - a) / 255 * 100, 4)))
		if t.k == "id":
			if t.v == "true":
				return ("bool", True)
			if t.v == "false":
				return ("bool", False)
			if t.v in ("if", "switch", "for", "while"):
				self.err(f"{t.v} inside an expression")
			return ("name", t.v)
		if t.k == "op" and t.v == "(":
			e = self.expr()
			self.expect(")")
			return e
		if t.k == "op" and t.v == "[":
			items = []
			while not self.isop("]"):
				items.append(self.expr())
				if self.isop(","):
					self.next()
			self.expect("]")
			return ("tuple", items)
		self.p -= 1
		self.err(f"unexpected {t.v!r}")

def parse(src):
	"""the statements of the script src"""
	return Parser(src).program()
