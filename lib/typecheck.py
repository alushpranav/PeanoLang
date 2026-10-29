"""typecheck.py - static type checker for the Peano language.

Types, as written in function headers:
    Peano
    Boolean
    Literal
    Seq.<type>              e.g.  Seq.Peano    Seq.Literal    Seq.(Seq.Peano)
    Tuple.<type>.<type>     exactly two parts, e.g.  Tuple.Peano.Peano
                            brackets are optional:   Tuple.Peano.(Seq.Peano)

A bare 'Seq' or a bare 'Tuple' is an error.

Internal form:  ('Peano',)  ('Boolean',)  ('Literal',)  ('Seq', T)  ('Tuple', A, B)
None as the element of a Seq means "not known yet". Only MT (and []) makes it,
and it fits any Seq.

Typing rules:
    Nil, Nx.x, numbers                      -> Peano       (x must be Peano)
    named constants from literal_dict.yaml   -> Literal
    Yes, No                                  -> Boolean
    MT                                       -> Seq of anything
    Dsq.x.xs                                 -> Seq.T       (x is T, xs is Seq.T)
    Mktp.a.b                                 -> Tuple.A.B
    f.a.b                                    -> return type of f (each arg checked)
    variables get their type from the pattern position or from the suchthat expression
"""
from utils import LangError, where as at
from utils import LITERAL_DICT

PEANO = ("Peano",)
BOOLEAN = ("Boolean",)
LITERAL = ("Literal",)


class TypeMismatch(ValueError):
    """A type error (a ValueError, so the loader adds line and function)."""


# ---------------------------------------------------------------- type syntax
def parse_type(text):
    s = text.replace(" ", "")
    t, i = _parse(s, 0, text)
    if i != len(s):
        rest = s[i:].lstrip(".")
        raise ValueError(f"Unexpected '{rest}' after type '{text.strip()}'")
    return t


def _parse(s, i, text):
    """Read one type starting at s[i]. Returns (type, next position).
    A type is  Peano | Boolean | Literal | Seq.<type> | Tuple.<type>.<type>
    and any type may be wrapped in brackets, e.g.  Tuple.Peano.(Seq.Peano)."""
    if i < len(s) and s[i] == "(":
        t, i = _parse(s, i + 1, text)
        if i >= len(s) or s[i] != ")":
            raise ValueError(f"Missing ')' in type '{text.strip()}'")
        return t, i + 1
    j = i
    while j < len(s) and s[j] not in ".()":
        j += 1
    head = s[i:j]
    if not head:
        raise ValueError(f"Missing type in '{text.strip()}'")
    if head in ("Peano", "Boolean", "Literal"):
        return (head,), j
    if head == "Seq":
        if j >= len(s) or s[j] != ".":
            raise ValueError("'Seq' needs an element type, e.g. Seq.Peano")
        inner_start = j + 1
        inner, j = _parse(s, inner_start, text)
        if inner[0] == "Seq" and s[inner_start] != "(":
            raise ValueError("a nested Seq type must be parenthesized, e.g. Seq.(Seq.Peano)")
        return ("Seq", inner), j
    if head == "Tuple":
        err = "'Tuple' needs exactly two types, e.g. Tuple.Peano.Peano"
        if j >= len(s) or s[j] != ".":
            raise ValueError(err)
        a, j = _parse(s, j + 1, text)
        if j >= len(s) or s[j] != ".":
            raise ValueError(err)
        b, j = _parse(s, j + 1, text)
        return ("Tuple", a, b), j
    raise ValueError(f"Unknown type '{head}' (types are Peano, Boolean, Literal, Seq.<type>, Tuple.<type>.<type>)")


def show(t):
    if t is None:
        return "?"
    if t[0] == "Seq":
        return "Seq." + show(t[1])
    if t[0] == "Tuple":
        return "Tuple." + _show_part(t[1]) + "." + _show_part(t[2])
    return t[0]


def _show_part(t):
    """A part of a Tuple is bracketed when it is itself a Seq or a Tuple."""
    text = show(t)
    return "(" + text + ")" if t is not None and t[0] in ("Seq", "Tuple") else text


def unify(a, b):
    """Return the merged type, or raise TypeMismatch."""
    if a is None:
        return b
    if b is None:
        return a
    if a[0] != b[0]:
        raise TypeMismatch(f"{show(a)} vs {show(b)}")
    if a[0] == "Seq":
        return ("Seq", unify(a[1], b[1]))
    if a[0] == "Tuple":
        return ("Tuple", unify(a[1], b[1]), unify(a[2], b[2]))
    return a


def const_type(name):
    if name in LITERAL_DICT:
        return LITERAL
    if name == "Nil":
        return PEANO
    if name == "MT":
        return ("Seq", None)
    return BOOLEAN  # Yes, No


# ---------------------------------------------------------------- showing code in messages
def render(node):
    kind = node[0]
    if kind == "Var":
        return node[1]
    if kind == "Con":
        return node[1]
    if kind == "Num":
        return str(node[1])                # Peano number
    return node[1] + "".join("." + _wrap(c) for c in node[2])


def _wrap(node):
    text = render(node)
    return "(" + text + ")" if node[0] in ("Op", "Call") else text


def _short(text, n=70):
    return text if len(text) <= n else text[: n - 3] + "..."


def need(expected, got, where, node):
    try:
        return unify(expected, got)
    except TypeMismatch:
        hint = ""
        if expected == PEANO and got == LITERAL:
            hint = "   (a named symbol is a Literal: use d2p.<name> to get a Peano)"
        elif expected == LITERAL and got == PEANO:
            hint = "   (use p2d.<peano> to get a Literal)"
        raise TypeMismatch(
            f"{where}: expected {show(expected)}, got {show(got)}  (in: {_short(render(node))}){hint}"
        )


# ---------------------------------------------------------------- patterns (LHS)
def check_pattern(p, expected, env, where):
    """Check pattern p against the declared type; give each variable its type."""
    kind = p[0]
    if kind == "Var":
        env[p[1]] = expected
        return

    def cant():
        raise TypeMismatch(
            f"{where}: pattern '{_short(render(p))}' can't match type {show(expected)}"
        )

    if kind == "Con":
        try:
            unify(const_type(p[1]), expected)
        except TypeMismatch:
            cant()
        return
    # what is left is an Op: Nx, Dsq or Mktp
    name, kids = p[1], p[2]
    if name == "Nx":
        if expected != PEANO:
            cant()
        check_pattern(kids[0], PEANO, env, where)
    elif name == "Dsq":
        if expected[0] != "Seq":
            cant()
        check_pattern(kids[0], expected[1], env, where)
        check_pattern(kids[1], expected, env, where)
    else:  # Mktp
        if expected[0] != "Tuple":
            cant()
        check_pattern(kids[0], expected[1], env, where)
        check_pattern(kids[1], expected[2], env, where)


# ---------------------------------------------------------------- expressions (RHS)
def infer(node, env, funcs):
    """Return the type of an expression. Raises TypeMismatch on a mistake."""
    kind = node[0]
    if kind == "Var":
        return env[node[1]]
    if kind == "Con":
        return const_type(node[1])
    if kind == "Num":
        return PEANO
    if kind == "Op":
        name, kids = node[1], node[2]
        if name == "Nx":
            got = infer(kids[0], env, funcs)
            need(PEANO, got, "inside 'Nx'", node)
            return PEANO
        if name == "Mktp":
            return ("Tuple", infer(kids[0], env, funcs), infer(kids[1], env, funcs))
        head = infer(kids[0], env, funcs)         # Dsq
        tail = infer(kids[1], env, funcs)
        return need(("Seq", head), tail, "tail of 'Dsq'", node)
    # Call
    func = funcs[node[1]]
    for i, (arg, want) in enumerate(zip(node[2], func["arg_types"]), 1):
        got = infer(arg, env, funcs)
        need(want, got, f"argument {i} of '{node[1]}'", node)
    return func["ret_type"]


# ---------------------------------------------------------------- whole program
def check_clause(func, clause, funcs):
    env = {}
    for i, (pat, want) in enumerate(zip(clause["patterns"], func["arg_types"]), 1):
        check_pattern(pat, want, env, f"argument {i}")
    for st in clause["suchthat"]:                 # in order: each may use the earlier ones
        env[st["name"]] = infer(st["tree"], env, funcs)
    body = infer(clause["body_tree"], env, funcs)
    need(func["ret_type"], body, "body of this clause", clause["body_tree"])


def typecheck_program(functions):
    for fname, func in functions.items():         # 1. read every header's types
        try:
            func["arg_types"] = [parse_type(t) for t in func["args"]]
            func["ret_type"] = parse_type(func["ret"])
        except ValueError as e:
            raise LangError(f"{at(func, func['line'])}: {e}")
    for fname, func in functions.items():         # 2. check every clause
        for clause in func["clauses"]:
            try:
                check_clause(func, clause, functions)
            except ValueError as e:
                raise LangError(f"{at(func, clause['line'])}: {e}")
    return functions
