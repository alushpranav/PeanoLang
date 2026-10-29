"""utils.py - parsing helpers for the Peano language.

Every tree node starts with its kind:

    ['Var', 'x']                 variable
    ['Con', 'Zero']              constant: core built-in or named Literal from literal_dict.yaml
    ['Op',  'Nx', [child]]       built-in with children (Nx, Dsq, Mktp)

Expressions (RHS) also have:

    ['Call', 'name', [args]]     function call
    ['Num', 12]                  number = Peano constant

Syntax rules enforced here:
    - Name.(...)  is the only way to give a name its children. 'Name(' is an error.
    - Brackets only group.
    - A pair is written Mktp.a.b. There is no (a,b) style and there are no commas.
    - Literal values are named built-ins from literal_dict.yaml; raw and quoted symbols are rejected.
    - Capital first letter = built-in, lowercase (or _) first letter = variable / function.
"""

import json
import re
from pathlib import Path

BUILTIN_FILE = Path(__file__).with_name("literal_dict.yaml")
CORE_BUILTINS = {"Nil": 0, "MT": 0, "Yes": 0, "No": 0,
                 "Nx": 1, "Dsq": 2, "Mktp": 2}


def _load_literal_dict(path=BUILTIN_FILE):
    """Read a simple YAML mapping of Literal names to quoted one-character strings."""
    values = {}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", "//", "--")):
            continue
        name, sep, encoded = line.partition(":")
        name, encoded = name.strip(), encoded.strip()
        if not sep or not re.fullmatch(r"[A-Z][A-Za-z0-9_]*", name):
            raise ValueError(f"{path.name}:{line_no}: expected BuiltinName: \"symbol\"")
        if name in CORE_BUILTINS:
            raise ValueError(f"{path.name}:{line_no}: '{name}' is reserved")
        try:
            value = json.loads(encoded)
        except ValueError as e:
            raise ValueError(f"{path.name}:{line_no}: invalid JSON symbol: {e}")
        if not isinstance(value, str) or len(value) != 1:
            raise ValueError(f"{path.name}:{line_no}: each value must be exactly one character")
        if name in values:
            raise ValueError(f"{path.name}:{line_no}: duplicate name '{name}'")
        values[name] = value
    if not values:
        raise ValueError(f"{path.name}: no Literal constants defined")
    return values


LITERAL_DICT = _load_literal_dict()
BUILTINS = {**CORE_BUILTINS, **{name: 0 for name in LITERAL_DICT}}


class LangError(Exception):
    """An error in the user's program (with line info)."""


def protect(s):
    """Reject direct quoted Literals; use names from literal_dict.yaml instead."""
    if "'" in s or '"' in s:
        raise ValueError("Direct quoted Literals are disabled; use a name from literal_dict.yaml")
    return s


def unprotect(s):
    """Compatibility helper for parser error formatting."""
    return s


def compact(s):
    """Remove whitespace, rejecting direct quoted Literal syntax."""
    return "".join(protect(s).split())


def where(func, line):
    """'line 5 in 'add'' - plus the refer file when the function came from refer/."""
    text = f"line {line} in '{func['name']}'"
    return text + f" ({func['file']})" if func.get("file") else text


def split_top(s, sep="."):
    """Split s at sep, but only outside brackets."""
    parts, cur, depth = [], "", 0
    for c in s.strip():
        if c == "(":
            depth += 1
            cur += c
        elif c == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("Unmatched closing parenthesis")
            cur += c
        elif c == sep and depth == 0:
            if cur:
                parts.append(cur)
            cur = ""
        else:
            cur += c
    if depth != 0:
        raise ValueError("Unmatched opening parenthesis")
    if cur:
        parts.append(cur)
    return parts


def extract_args(s):
    """Split a clause LHS like '.(Nx.x).y' into ['(Nx.x)', 'y']."""
    return split_top(s, ".")


def check_syntax(s):
    """'(' must be at the start or right after '.' or '('.
    ')' must be followed by '.', ')' or the end.
    There are no commas: a pair is written Mktp.a.b, not (a,b)."""
    s = s.strip()
    for i, c in enumerate(s):
        if c == "(" and i > 0 and s[i - 1] not in ".(":
            raise ValueError(f"Bad '(' after a name in: {s}   (write Name.(...) not Name(...))")
        if c == ")" and i < len(s) - 1 and s[i + 1] not in ".)":
            raise ValueError(f"Bad text after ')' in: {s}")
    if "," in s:
        raise ValueError(f"Commas are not used. Write a pair as Mktp.a.b, not (a,b)   (in: {s})")


def _is_var(head):
    return head[0].islower() or head[0] == "_"


def _encloses(s):
    """True if one bracket pair wraps the whole string."""
    if not (s.startswith("(") and s.endswith(")")):
        return False
    depth = 0
    for i, c in enumerate(s):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if depth == 0 and i < len(s) - 1:
            return False
    return True


def _unwrap(s):
    """Strip brackets that wrap the whole text, e.g. ((Nx.x)) -> Nx.x"""
    s = s.strip()
    while _encloses(s):
        s = s[1:-1].strip()
    return s


def collect_vars(node):
    """All variable names in a pattern tree."""
    kind = node[0]
    if kind == "Var":
        return [node[1]]
    if kind == "Op":
        return [v for c in node[2] for v in collect_vars(c)]
    return []


# ---------------------------------------------------------------- patterns (LHS)
def _break(s):
    s = _unwrap(s)
    parts = split_top(s, ".")
    if not parts:
        raise ValueError("Empty pattern")
    head, children = parts[0], parts[1:]
    if head.startswith("("):
        raise ValueError(f"A bracket group can't take arguments in: {s}")

    if _is_var(head):
        if children:
            raise ValueError(f"Function call not allowed on LHS: {s}")
        return ["Var", head]

    if head[0].isdigit():
        raise ValueError("Bare digit Literals are disabled; use a name from literal_dict.yaml")

    if head not in BUILTINS:
        raise ValueError(f"Unknown built-in '{head}' in: {s}")
    if len(children) != BUILTINS[head]:
        raise ValueError(f"{head} needs {BUILTINS[head]} child(ren), got {len(children)} in: {s}")
    if not children:
        return ["Con", head]
    return ["Op", head, [_break(ch) for ch in children]]


def break_pattern(s):
    s = compact(s)
    check_syntax(s)
    return _break(s)


# ---------------------------------------------------------------- expressions (RHS)
def _expr(s, funcs, bound):
    s = _unwrap(s)
    parts = split_top(s, ".")
    if not parts:
        raise ValueError("Empty expression")
    head, rest = parts[0], parts[1:]
    if head.startswith("("):
        raise ValueError(f"A bracket group can't take arguments in: {s}")

    # literals and numbers
    if head.isdigit():
        if rest:
            raise ValueError(f"A number can't take arguments in: {s}")
        return ["Num", int(head)]
    # function call or variable
    if _is_var(head):
        if head in funcs:
            want = funcs[head]["args_count"]
            if len(rest) != want:
                raise ValueError(f"'{head}' takes {want} argument(s), got {len(rest)} in: {s}")
            return ["Call", head, [_expr(r, funcs, bound) for r in rest]]
        if head in bound:
            if rest:
                raise ValueError(f"Variable '{head}' can't take arguments in: {s}")
            return ["Var", head]
        raise ValueError(f"Unknown name '{head}' in: {s}")

    # built-in
    if head not in BUILTINS:
        raise ValueError(f"Unknown built-in '{head}' in: {s}")
    if len(rest) != BUILTINS[head]:
        raise ValueError(f"{head} needs {BUILTINS[head]} child(ren), got {len(rest)} in: {s}")
    if not rest:
        return ["Con", head]
    return ["Op", head, [_expr(r, funcs, bound) for r in rest]]


def parse_expr(s, funcs, bound):
    """funcs: dict name -> function info (needs 'args_count'); bound: set of variable names."""
    s = compact(s)
    check_syntax(s)
    return _expr(s, funcs, bound)
