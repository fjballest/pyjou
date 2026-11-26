"""Pine (the tree of parse.py) to Python source run by runtime.py.

The script's top level becomes _bar(_c), run once a bar, its variables
module globals (var ones kept from bar to bar), and the declarations that
do not change from bar to bar (inputs, constants) _init(_c), run once.
User functions are Python functions; those that keep state (ta calls, var,
history) take the Ctx of their call site first."""

import keyword

from . import runtime as R
from .parse import PineError, parse

F, STATEFUL, K, D = R.builtins()
NAMESPACES = {"array", "map", "line", "label", "box", "table", "linefill", "polyline", "matrix", "chart.point",
	"str", "math", "ta", "color", "input", "request", "timeframe", "syminfo", "barstate", "chart", "runtime", "log", "ticker", "strategy", "settlement_as_close"}
OBJECTNS = {"array", "map", "line", "label", "box", "table", "linefill", "polyline", "matrix", "chart.point"}
BUILTINMETHODS = set()
for cls in (R.PArray, R.PMap, R.Line, R.Label, R.Box, R.Table, R.Linefill, R.Point, R.UDT):
	BUILTINMETHODS.update(n for n in dir(cls) if not n.startswith("_"))
PURE = ("input.", "color.", "math.", "str.", "timeframe.in_seconds", "timeframe.from_seconds")
PUREFN = {"na", "nz", "int", "float", "bool", "string", "color", "timestamp"}
INVDYN = ("timeframe.", "syminfo.")
SAFE = {"delete", "copy"}

def v(n):
	return "v_" + n

def fld(n):
	return n + "_" if keyword.iskeyword(n) else n

def dotted(e):
	"""a.b.c for an attribute chain of names, else None"""
	if e[0] == "name":
		return e[1]
	if e[0] == "attr":
		d = dotted(e[1])
		return d and d + "." + e[2]
	return None

def walk(node):
	"""every tuple under node (statements and expressions)"""
	stack = [node]
	while stack:
		n = stack.pop()
		if isinstance(n, tuple):
			if not n or not isinstance(n[0], str):
				continue
			yield n
			stack.extend(x for x in n if isinstance(x, (tuple, list)))
		elif isinstance(n, list):
			stack.extend(x for x in n if isinstance(x, (tuple, list)))

class Scoper:
	"""gives the variables declared in inner blocks of a unit (the top level
	or a function) their own names (x__2) when the name is declared more
	than once there (or, in a function, is a global), so that Pine's block
	scopes survive Python's function scope"""
	def __init__(self, counts, avoid=()):
		self.counts = counts
		self.avoid = set(avoid)
		self.scopes = [{}]
		self.n = 0

	def bind(self, name, depth):
		if depth > 0 and (self.counts.get(name, 0) > 1 or name in self.avoid):
			self.n += 1
			new = f"{name}__{self.n}"
		else:
			new = name
		self.scopes[-1][name] = new
		return new

	def look(self, name):
		for sc in reversed(self.scopes):
			if name in sc:
				return sc[name]
		return name

	def block(self, stmts):
		self.scopes.append({})
		out = [self.stmt(x) for x in stmts]
		self.scopes.pop()
		return out

	@property
	def depth(self):
		return len(self.scopes) - 1

	def stmt(self, s):
		k = s[0]
		if k == "decl":
			_, mode, typ, name, rhs, line = s
			rhs = self.expr(rhs)
			return (k, mode, typ, self.bind(name, self.depth), rhs, line)
		if k == "tdecl":
			_, names, rhs, op, line = s
			rhs = self.expr(rhs)
			if op == ":=":
				return (k, [self.look(n) for n in names], rhs, op, line)
			return (k, [self.bind(n, self.depth) for n in names], rhs, op, line)
		if k == "assign":
			return (k, self.expr(s[1]), s[2], self.expr(s[3]), s[4])
		if k in ("expr", "indicator"):
			return (k, self.expr(s[1]), s[2])
		if k == "if":
			return (k, self.expr(s[1]), self.block(s[2]), self.block(s[3]), s[4])
		if k == "for":
			_, var, a, b, step, body, line = s
			a, b = self.expr(a), self.expr(b)
			step = None if step is None else self.expr(step)
			self.scopes.append({})
			var = self.bind(var, self.depth)
			body = [self.stmt(x) for x in body]
			self.scopes.pop()
			return (k, var, a, b, step, body, line)
		if k == "forin":
			_, i, var, it, body, line = s
			it = self.expr(it)
			self.scopes.append({})
			i = None if i is None else self.bind(i, self.depth)
			var = self.bind(var, self.depth)
			body = [self.stmt(x) for x in body]
			self.scopes.pop()
			return (k, i, var, it, body, line)
		if k == "while":
			return (k, self.expr(s[1]), self.block(s[2]), s[3])
		if k == "switch":
			_, subject, cases, line = s
			subject = None if subject is None else self.expr(subject)
			return (k, subject, [(None if c is None else self.expr(c), self.block(b)) for c, b in cases], line)
		return s

	def expr(self, e):
		k = e[0]
		if k == "name":
			return ("name", self.look(e[1]))
		if k == "hist":
			return (k, self.expr(e[1]), self.expr(e[2]), e[3])
		if k == "attr":
			return (k, self.expr(e[1]), e[2])
		if k == "call":
			_, f, args, kw, targs, site, line = e
			if f[0] != "name":
				f = self.expr(f)
			return (k, f, [self.expr(a) for a in args], [(n, self.expr(a)) for n, a in kw], targs, site, line)
		if k == "bin":
			return (k, e[1], self.expr(e[2]), self.expr(e[3]))
		if k in ("and", "or"):
			return (k, self.expr(e[1]), self.expr(e[2]))
		if k in ("not", "neg"):
			return (k, self.expr(e[1]))
		if k == "tern":
			return (k, self.expr(e[1]), self.expr(e[2]), self.expr(e[3]))
		if k == "tuple":
			return (k, [self.expr(x) for x in e[1]])
		if k == "block":
			return (k, self.stmt(e[1]))
		return e

def declcounts(stmts):
	counts = {}
	for s in walk(stmts):
		names = ()
		if s[0] == "decl":
			names = (s[3],)
		elif s[0] == "tdecl" and s[3] != ":=":
			names = s[1]
		elif s[0] == "for":
			names = (s[1],)
		elif s[0] == "forin":
			names = (s[2],) + ((s[1],) if s[1] else ())
		for n in names:
			counts[n] = counts.get(n, 0) + 1
	return counts

class Func:
	def __init__(self, node, index):
		_, self.name, self.params, self.body, self.method, self.line = node
		self.node = node
		self.index = index
		self.pyname = f"f_{self.name}_{index}"
		self.locals = {p[1] for p in self.params}
		self.vars = set()
		for s in walk(self.body):
			if s[0] == "decl":
				self.locals.add(s[3])
				if s[1]:
					self.vars.add(s[3])
			elif s[0] == "tdecl":
				self.locals.update(s[1])
			elif s[0] == "for":
				self.locals.add(s[1])
			elif s[0] == "forin":
				self.locals.add(s[2])
				if s[1]:
					self.locals.add(s[1])
		self.hists = {s[1][1] for s in walk(self.body) if s[0] == "hist" and s[1][0] == "name" and s[1][1] in self.locals}
		self.stateful = None
		first = self.params[0] if self.params else None
		self.key = R.typename(first[0]) if first and first[0] else None
		self.nmin = sum(1 for p in self.params if p[2] is None)
		self.nmax = len(self.params)

class Compiler:
	def __init__(self, prog):
		self.prog = prog
		self.types = {}
		self.funcs = {}
		self.top = []
		for s in prog:
			if s[0] == "type":
				self.types[s[1]] = s[2]
			elif s[0] == "func":
				lst = self.funcs.setdefault(s[1], [])
				lst.append(Func(s, len(lst)))
			else:
				self.top.append(s)
		sc = Scoper(declcounts(self.top))
		self.top = [sc.stmt(x) for x in self.top]
		topnames = set(declcounts(self.top))
		for fs in self.funcs.values():
			for f in fs:
				sc = Scoper(declcounts(f.body), topnames)
				for p in f.params:
					sc.scopes[0][p[1]] = p[1]
				sc.scopes.append({})
				f.body = [sc.stmt(x) for x in f.body]
				f.__init__((f.node[0], f.name, f.params, f.body, f.method, f.line), f.index)
		self.globals = set()
		self.gvars = set()
		for s in walk(self.top):
			if s[0] == "decl":
				self.globals.add(s[3])
				if s[1]:
					self.gvars.add(s[3])
			elif s[0] == "tdecl":
				self.globals.update(s[1])
			elif s[0] == "for":
				self.globals.add(s[1])
			elif s[0] == "forin":
				self.globals.add(s[2])
				if s[1]:
					self.globals.add(s[1])
		self.ghists = set()
		for s in walk(self.top):
			if s[0] == "hist" and s[1][0] == "name" and s[1][1] in self.globals:
				self.ghists.add(s[1][1])
		for fs in self.funcs.values():
			for f in fs:
				for s in walk(f.body):
					if s[0] == "hist" and s[1][0] == "name" and s[1][1] not in f.locals and s[1][1] in self.globals:
						self.ghists.add(s[1][1])
		self.statefulness()
		self.hoisting()
		self.out = []
		self.ind = 0
		self.fn = None
		self.tmp = 0
		self.consts = {}
		self.lines = []	# (generated line, Pine line)

	# analysis
	def statefulness(self):
		for fs in self.funcs.values():
			for f in fs:
				f.stateful = bool(f.vars or f.hists) or any(self.direct(s, f) for s in walk(f.body))
		changed = True
		while changed:
			changed = False
			for fs in self.funcs.values():
				for f in fs:
					if f.stateful:
						continue
					for s in walk(f.body):
						if s[0] == "call":
							n = self.username(s, f)
							if n and self.groupstateful(n):
								f.stateful = changed = True
								break

	def direct(self, s, f):
		if s[0] == "hist" and s[1][0] != "name":
			return True
		if s[0] == "call":
			d = dotted(s[1])
			if d in STATEFUL and not (s[1][0] == "name" and s[1][1] in self.funcs):
				return True
		return False

	def groupstateful(self, n):
		return any(f.stateful for f in self.funcs.get(n, ()))

	def username(self, call, f=None):
		"""the user function a call node calls, or None"""
		e = call[1]
		if e[0] == "name":
			return e[1] if e[1] in self.funcs else None
		if e[0] == "attr":
			d = dotted(e)
			if d in F:
				return None
			if e[2] in self.funcs:
				return e[2]
		return None

	def hoisting(self):
		assigned = {s[1][1] for s in walk(self.top) if s[0] == "assign" and s[1][0] == "name"}
		count = {}
		for s in walk(self.top):
			if s[0] == "decl":
				count[s[3]] = count.get(s[3], 0) + 1
		cands = [s for s in self.top if s[0] == "decl" and s[3] not in assigned and count[s[3]] == 1
			and s[3] not in self.ghists and s[4][0] != "block"]
		self.pure = set(self.funcs)
		self.hoisted = set()
		while True:
			hoisted = set()
			for s in cands:
				if self.inv(s[4], None, hoisted):
					hoisted.add(s[3])
			pure = {n for n in self.pure if all(self.purefn(f, hoisted) for f in self.funcs[n])}
			if hoisted == self.hoisted and pure == self.pure:
				break
			self.hoisted, self.pure = hoisted, pure
		self.hoistnodes = {id(s) for s in cands if s[3] in self.hoisted}

	def purefn(self, f, hoisted):
		if f.stateful:
			return False
		for s in walk(f.body):
			k = s[0]
			if k in ("hist", "block") or (k == "decl" and s[1]):
				return False
			if k == "assign" and s[1][0] != "name":
				return False
			if k == "call" and not self.invcall(s, f, hoisted):
				return False
			if k == "name" and s[1] not in f.locals and not self.invname(s[1], hoisted):
				return False
			if k == "attr" and dotted(s) is None and False:
				return False
		return True

	def invname(self, n, hoisted):
		if n in self.globals:
			return n in hoisted
		return n == "na"

	def invcall(self, e, f, hoisted):
		d = dotted(e[1])
		if e[1][0] == "name" and e[1][1] in self.funcs:
			return e[1][1] in self.pure
		if d is not None and (d in PUREFN or (d.startswith(PURE) and d in F and d not in STATEFUL)):
			return True
		return False

	def inv(self, e, f, hoisted):
		k = e[0]
		if k in ("num", "str", "bool", "color"):
			return True
		if k == "name":
			if f is not None and e[1] in f.locals:
				return True
			return self.invname(e[1], hoisted)
		if k == "attr":
			d = dotted(e)
			if d in K:
				return True
			if d in D:
				return d.startswith(INVDYN)
			return False
		if k == "call":
			if not self.invcall(e, f, hoisted):
				return False
			return all(self.inv(a, f, hoisted) for a in e[2]) and all(self.inv(a, f, hoisted) for _, a in e[3])
		if k in ("bin",):
			return self.inv(e[2], f, hoisted) and self.inv(e[3], f, hoisted)
		if k in ("and", "or"):
			return self.inv(e[1], f, hoisted) and self.inv(e[2], f, hoisted)
		if k in ("not", "neg"):
			return self.inv(e[1], f, hoisted)
		if k == "tern":
			return all(self.inv(x, f, hoisted) for x in e[1:])
		if k == "tuple":
			return all(self.inv(x, f, hoisted) for x in e[1])
		return False

	# output
	def emit(self, s):
		self.out.append("\t" * self.ind + s)

	def newtmp(self):
		self.tmp += 1
		return f"_t{self.tmp}"

	def const(self, value):
		k = f"_k{len(self.consts)}"
		self.consts[k] = value
		return k

	def program(self):
		e = self.emit
		e("# generated from Pine")
		for name, fields in self.types.items():
			e(f"class T_{name}(_UDT):")
			self.ind += 1
			slots = tuple(fld(f[1]) for f in fields)
			e(f"__slots__ = {slots!r}")
			e(f"_pine = {name!r}")
			args = ", ".join(f"{fld(f[1])}={self.expr(f[2]) if f[2] is not None else '_na'}" for f in fields)
			e(f"def __init__(self{', ' if args else ''}{args}):")
			self.ind += 1
			for f in fields:
				e(f"self.{fld(f[1])} = {fld(f[1])}")
			if not fields:
				e("pass")
			self.ind -= 2
		for name, fs in self.funcs.items():
			for f in fs:
				self.function(f)
			self.dispatcher(name, fs)
		for n in sorted(self.globals):
			e(f"{v(n)} = {'_UNSET' if n in self.gvars else '_na'}")
		for n in sorted(self.ghists):
			e(f"_H_{n} = _Hist()")
		gl = ", ".join(v(n) for n in sorted(self.globals))
		e("def _init(_c):")
		self.ind += 1
		if gl:
			e(f"global {gl}")
		e("pass")
		for s in self.top:
			if id(s) in self.hoistnodes or s[0] == "indicator":
				self.stmt(s)
		self.ind -= 1
		e("def _bar(_c):")
		self.ind += 1
		if gl:
			e(f"global {gl}")
		e("pass")
		for s in self.top:
			if id(s) not in self.hoistnodes and s[0] != "indicator":
				self.stmt(s)
		self.ind -= 1
		return "\n".join(self.out) + "\n"

	def function(self, f):
		self.fn = f
		group = self.groupstateful(f.name)
		params = []
		for typ, name, default in f.params:
			params.append(f"{v(name)}={self.expr(default)}" if default is not None else v(name))
		if group:
			params.insert(0, "_c")
		self.emit(f"def {f.pyname}({', '.join(params)}):")
		self.ind += 1
		if f.vars:
			self.emit("_v = _c.v")
		for n in sorted(f.hists):
			self.emit(f"_hx_{n} = _c.h({n!r})")
		for typ, name, default in f.params:
			if name in f.hists:
				self.emit(f"_hx_{name}.set({v(name)})")
		self.body(f.body, "_r", ret=True)
		self.ind -= 1
		self.fn = None

	def dispatcher(self, name, fs):
		if len(fs) == 1 and name not in BUILTINMETHODS:
			self.emit(f"f_{name} = {fs[0].pyname}")
			return
		group = self.groupstateful(name)
		entries = ", ".join(f"({f.key!r}, {f.nmin}, {f.nmax}, {f.pyname})" for f in fs)
		self.emit(f"f_{name} = _Over({name!r}, [{entries}], {group})")

	def body(self, stmts, target=None, ret=False):
		"""statements; with target, the value of the last one into it (and
		returned, with ret)"""
		if not stmts:
			if target:
				self.emit(f"{'return' if ret else target + ' ='} _na")
			else:
				self.emit("pass")
			return
		for s in stmts[:-1]:
			self.stmt(s)
		last = stmts[-1]
		if target is None:
			self.stmt(last)
			return
		if ret and last[0] == "expr":
			self.emit(f"return {self.expr(last[1])}")
			return
		self.valued(last, target)
		if ret:
			self.emit(f"return {target}")

	def valued(self, s, target):
		k = s[0]
		if k == "expr":
			self.emit(f"{target} = {self.expr(s[1])}")
		elif k == "decl":
			self.stmt(s)
			self.emit(f"{target} = {self.name(s[3])}")
		elif k == "tdecl":
			self.stmt(s)
			self.emit(f"{target} = ({', '.join(self.name(n) for n in s[1])},)")
		elif k == "assign":
			self.stmt(s)
			self.emit(f"{target} = {self.lvalue(s[1])}")
		elif k == "if":
			self.ifst(s, target)
		elif k == "switch":
			self.switchst(s, target)
		elif k in ("for", "forin", "while"):
			self.emit(f"{target} = _na")
			self.loop(s, target)
		else:
			self.stmt(s)
			self.emit(f"{target} = _na")

	# statements
	def stmt(self, s):
		line = s[-1] if isinstance(s[-1], int) else None
		if line:
			self.lines.append((len(self.out) + 1, line))
		try:
			self._stmt(s)
		except PineError as x:
			if x.line is None and line:
				raise PineError(str(x), line) from None
			raise
		except Exception as x:	# pragma: no cover
			raise PineError(f"{type(x).__name__}: {x}", s[-1] if isinstance(s[-1], int) else None)

	def _stmt(self, s):
		k = s[0]
		e = self.emit
		if k == "decl":
			_, mode, typ, name, rhs, line = s
			py = self.name(name)
			if rhs[0] == "block":
				val = self.newtmp()
				if mode:
					cond = self.varcond(name)
					e(f"if {cond}:")
					self.ind += 1
					self.valued(rhs[1], val)
					self.assignvar(name, py, val)
					self.ind -= 1
					self.varload(name, py)
				else:
					self.valued(rhs[1], val)
					e(f"{py} = {val}")
			elif mode:
				if self.fn is None:
					e(f"if {py} is _UNSET:")
					self.ind += 1
					e(f"{py} = {self.expr(rhs)}")
					self.ind -= 1
				else:
					e(f"if {name!r} in _v:")
					self.ind += 1
					e(f"{py} = _v[{name!r}]")
					self.ind -= 1
					e("else:")
					self.ind += 1
					e(f"{py} = _v[{name!r}] = {self.expr(rhs)}")
					self.ind -= 1
			else:
				e(f"{py} = {self.expr(rhs)}")
			self.sethist(name)
		elif k == "tdecl":
			_, names, rhs, op, line = s
			if rhs[0] == "block":
				val = self.newtmp()
				self.valued(rhs[1], val)
				src = val
			else:
				src = self.expr(rhs, arity=len(names))
			e(f"{', '.join(self.name(n) for n in names)}, = {src}")
			for n in names:
				self.storevar(n)
				self.sethist(n)
		elif k == "assign":
			_, target, op, rhs, line = s
			if rhs[0] == "block":
				val = self.newtmp()
				self.valued(rhs[1], val)
				value = val
			else:
				value = self.expr(rhs)
			lv = self.lvalue(target)
			if op != ":=":
				o = op[0]
				if o == "/":
					value = f"_div({lv}, {value})"
				elif o == "%":
					value = f"_mod({lv}, {value})"
				else:
					value = f"({lv} {o} {value})"
			e(f"{lv} = {value}")
			if target[0] == "name":
				self.storevar(target[1])
				self.sethist(target[1])
		elif k == "expr":
			e(self.expr(s[1]))
		elif k == "if":
			self.ifst(s, None)
		elif k == "switch":
			self.switchst(s, None)
		elif k in ("for", "forin", "while"):
			self.loop(s, None)
		elif k == "break":
			e("break")
		elif k == "continue":
			e("continue")
		elif k == "indicator":
			e(self.expr(s[1]))
		elif k == "type" or k == "func":
			raise PineError("a definition inside a block", s[-1])
		else:
			raise PineError(f"unknown statement {k}")

	def varcond(self, name):
		return f"{self.name(name)} is _UNSET" if self.fn is None else f"{name!r} not in _v"

	def assignvar(self, name, py, val):
		self.emit(f"{py} = {val}")
		if self.fn is not None:
			self.emit(f"_v[{name!r}] = {py}")

	def varload(self, name, py):
		if self.fn is not None:
			self.emit(f"{py} = _v[{name!r}]")

	def storevar(self, name):
		if self.fn is not None and name in self.fn.vars:
			self.emit(f"_v[{name!r}] = {v(name)}")

	def sethist(self, name):
		if self.fn is not None and name in self.fn.locals:
			if name in self.fn.hists:
				self.emit(f"_hx_{name}.set({v(name)})")
		elif name in self.ghists:
			self.emit(f"_H_{name}.set({v(name)})")

	def ifst(self, s, target):
		_, cond, body, other, line = s
		self.emit(f"if {self.expr(cond)}:")
		self.ind += 1
		self.body(body, target)
		self.ind -= 1
		if other or target:
			self.emit("else:")
			self.ind += 1
			self.body(other, target)
			self.ind -= 1

	def switchst(self, s, target):
		_, subject, cases, line = s
		sw = None
		if subject is not None:
			sw = self.newtmp()
			self.emit(f"{sw} = {self.expr(subject)}")
		first = True
		default = None
		for cond, body in cases:
			if cond is None:
				default = body
				continue
			c = f"{sw} == {self.expr(cond)}" if sw else self.expr(cond)
			self.emit(f"{'if' if first else 'elif'} {c}:")
			first = False
			self.ind += 1
			self.body(body, target)
			self.ind -= 1
		if default is not None or target:
			if first:
				self.emit("if True:")
			else:
				self.emit("else:")
			self.ind += 1
			self.body(default or [], target)
			self.ind -= 1

	def loop(self, s, target):
		k = s[0]
		if k == "for":
			_, var, a, b, step, body, line = s
			st = f", {self.expr(step)}" if step is not None else ""
			self.emit(f"for {self.name(var)} in _frange({self.expr(a)}, {self.expr(b)}{st}):")
		elif k == "forin":
			_, i, var, it, body, line = s
			if i:
				self.emit(f"for {self.name(i)}, {self.name(var)} in _enumof({self.expr(it)}):")
			else:
				self.emit(f"for {self.name(var)} in _iterof({self.expr(it)}):")
		else:
			_, cond, body, line = s
			self.emit(f"while {self.expr(cond)}:")
		self.ind += 1
		self.body(body, target)
		self.ind -= 1

	def lvalue(self, e):
		if e[0] == "name":
			return self.name(e[1])
		if e[0] == "attr":
			return f"{self.expr(e[1])}.{fld(e[2])}"
		raise PineError(f"cannot assign to {e[0]}")

	def name(self, n):
		if self.fn is not None and n in self.fn.locals:
			return v(n)
		if n in self.globals:
			return v(n)
		if n in R.SERIESVARS:
			return n
		if n == "na":
			return "_na"
		raise PineError(f"unknown name {n!r}")

	# expressions
	def expr(self, e, arity=0):
		k = e[0]
		if k == "num":
			return repr(e[1])
		if k == "str":
			return repr(e[1])
		if k == "bool":
			return "True" if e[1] else "False"
		if k == "color":
			return repr(e[1])
		if k == "name":
			return self.name(e[1])
		if k == "bin":
			op, a, b = e[1], self.expr(e[2]), self.expr(e[3])
			if op == "/":
				return f"_div({a}, {b})"
			if op == "%":
				return f"_mod({a}, {b})"
			return f"({a} {op} {b})"
		if k == "and":
			return f"({self.expr(e[1])} and {self.expr(e[2])})"
		if k == "or":
			return f"({self.expr(e[1])} or {self.expr(e[2])})"
		if k == "not":
			return f"(not {self.expr(e[1])})"
		if k == "neg":
			return f"(-{self.expr(e[1])})"
		if k == "tern":
			return f"({self.expr(e[2])} if {self.expr(e[1])} else {self.expr(e[3])})"
		if k == "tuple":
			return "(" + "".join(self.expr(x) + ", " for x in e[1]) + ")"
		if k == "hist":
			return self.hist(e)
		if k == "attr":
			return self.attr(e)
		if k == "call":
			return self.call(e, arity)
		if k == "block":
			raise PineError("an if or switch inside an expression")
		raise PineError(f"unknown expression {k}")

	def isvar(self, n):
		return (self.fn is not None and n in self.fn.locals) or n in self.globals

	def hist(self, e):
		_, x, n, site = e
		ne = self.expr(n)
		if x[0] == "name" and not self.isvar(x[1]) and x[1] in R.SERIESVARS:
			return f"_sh({x[1]!r}, {ne})"
		if x[0] == "name" and self.fn is not None and x[1] in self.fn.locals:
			return f"_hx_{x[1]}.get({ne})"
		if x[0] == "name" and x[1] in self.globals:
			return f"_H_{x[1]}.get({ne})"
		return f"_hx(_c, {site}, {self.expr(x)}, {ne})"

	def attr(self, e):
		d = dotted(e)
		if d is not None and not self.isvar(d.split(".")[0]):
			if d in D:
				return D[d]
			if d in K:
				return self.const(K[d])
			if d.split(".")[0] in NAMESPACES or d in F:
				raise PineError(f"unknown built-in {d}")
		return f"{self.expr(e[1])}.{fld(e[2])}"

	def args(self, e, skip=0):
		_, f, args, kw, targs, site, line = e
		out = [self.expr(a) for a in args[skip:]]
		out += [f"{n}={self.expr(a)}" for n, a in kw]
		return out

	def call(self, e, arity=0):
		_, f, args, kw, targs, site, line = e
		d = dotted(f)
		if f[0] == "name" and f[1] in self.funcs:
			return self.usercall(f[1], self.userargs(e), site)
		if d is not None and not self.isvar(d.split(".")[0]):
			if d in ("request.security", "request.security_lower_tf"):
				return self.request(d, e, arity)
			if d in F:
				py = "_b_" + d.replace(".", "_")
				a = self.args(e)
				if targs:
					a.append(f"_t={tuple(targs)!r}")
				if d in STATEFUL:
					a = ["_c", str(site)] + a
				elif d == "input" or d.startswith("input."):
					a.append(f"_site={site}")
				return f"{py}({', '.join(a)})"
			parts = d.split(".")
			head, m = ".".join(parts[:-1]), parts[-1]
			if head in self.types:
				if m == "new":
					a = [self.expr(x) for x in args] + [f"{fld(n)}={self.expr(x)}" for n, x in kw]
					return f"T_{head}({', '.join(a)})"
				if m == "copy":
					return f"({self.expr(args[0])}).copy()"
				if m in self.funcs:
					return self.usercall(m, self.userargs(e), site)
			if head in OBJECTNS:
				if m in self.funcs:
					return self.usercall(m, self.userargs(e), site)
				if not args:
					raise PineError(f"unknown built-in {d}", line)
				return f"_nsm({self.expr(args[0])}, {m!r})({', '.join(self.args(e, 1))})"
			if head in NAMESPACES or (f[0] == "name"):
				raise PineError(f"unknown built-in {d}", line)
		if f[0] == "attr":	# a method of a value
			obj, m = f[1], f[2]
			o = self.expr(obj)
			if m in self.funcs:
				return self.usercall(m, [o] + self.userargs(e), site)
			a = ", ".join(self.args(e))
			if m in SAFE or m.startswith("set_") or m.startswith("get_"):
				return f"_nsm({o}, {m!r})({a})"
			return f"{o}.{m}({a})"
		raise PineError(f"cannot call {f[0]}", line)

	def userargs(self, e):
		_, f, args, kw, targs, site, line = e
		return [self.expr(a) for a in args] + [f"{v(n)}={self.expr(a)}" for n, a in kw]

	def usercall(self, name, args, site):
		if self.groupstateful(name):
			args = [f"_c.sub({site})"] + args
		return f"f_{name}({', '.join(args)})"

	def request(self, d, e, arity):
		_, f, args, kw, targs, site, line = e
		args = list(args)
		kw = list(kw)
		names = ["symbol", "timeframe", "expression"]
		pos = {}
		for i, a in enumerate(args[:3]):
			pos[names[i]] = a
		rest = args[3:]
		for n, a in kw:
			if n in names:
				pos[n] = a
		kw = [(n, a) for n, a in kw if n not in names]
		x = pos["expression"]
		ar = len(x[1]) if x[0] == "tuple" else arity
		out = [self.expr(pos["symbol"]), self.expr(pos["timeframe"]), f"lambda _c: {self.expr(x)}"]
		out += [self.expr(a) for a in rest]
		out += [f"{n}={self.expr(a)}" for n, a in kw]
		out.append(f"_n={ar}")
		return f"_b_{d.replace('.', '_')}(_c, {site}, {', '.join(out)})"

class Over:
	"""the overloads of a user function or method, picked by the type of
	the first argument (and how many there are)"""
	def __init__(self, name, entries, ctx):
		self.name, self.entries, self.ctx = name, entries, ctx
		self.cache = {}

	def __call__(self, *a, **k):
		c = None
		if self.ctx:
			c, a = a[0], a[1:]
		n = len(a) + len(k)
		first = a[0] if a else None
		key = (R.typeof(first) if a else None, n)
		f = self.cache.get(key)
		if f is None:
			f = self.pick(first, key[0], n)
			self.cache[key] = f
		if f is False:
			if a and self.name in dir(first):
				return getattr(first, self.name)(*a[1:], **k)
			raise R.PineRuntimeError(f"no {self.name} for {key[0]}")
		return f(c, *a, **k) if self.ctx else f(*a, **k)

	def pick(self, first, t, n):
		fits = [e for e in self.entries if e[1] <= n <= e[2]]
		if not fits:
			return False
		if len(fits) == 1 and (fits[0][0] is None or not isinstance(first, (R.UDT, R.PArray, R.PMap, R.Line, R.Label, R.Box, R.Table))):
			return fits[0][3]
		for e in fits:
			if e[0] == t:
				return e[3]
		if t and t.startswith("array"):
			for e in fits:
				if e[0] and e[0].startswith("array") and (t == "array" or e[0] == "array"):
					return e[3]
		if t == "int":
			for e in fits:
				if e[0] == "float":
					return e[3]
		for e in fits:
			if e[0] is None:
				return e[3]
		if len(fits) == 1 and t is None:
			return fits[0][3]
		return False

def namespace():
	"""the names the generated code is run with"""
	ns = {"_na": R.na, "_UNSET": R.UNSET, "_div": R.div, "_mod": R.mod, "_Hist": R.Hist, "_hx": R.hx,
		"_frange": R.frange, "_iterof": R.iterof, "_enumof": R.enumof, "_nsm": R.nsm, "_sh": R.sh, "_RT": R.RT,
		"_UDT": R.UDT, "_Over": Over}
	for name, fn in F.items():
		ns["_b_" + name.replace(".", "_")] = fn
	return ns

def compile_script(src, name="<pine>"):
	"""(python source, code object, constants, [(generated line, Pine
	line)]) of the Pine script src"""
	prog = parse(src)
	c = Compiler(prog)
	py = c.program()
	try:
		code = compile(py, name, "exec")
	except SyntaxError as x:	# pragma: no cover
		raise PineError(f"internal: {x}")
	return py, code, c.consts, c.lines
