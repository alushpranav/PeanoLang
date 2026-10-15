"""utils.py - parsing helpers for the Peano language.

Every tree node starts with its kind:

    ['Var', 'x']                 variable
    ['Con', 'Nil']               constant: Nil, MT, Yes, No, or a Literal (one symbol: 5, 'a', '%')
    ['Op',  'Nx', [child]]       built-in with children (Nx, Dsq, Mktp)

Expressions (RHS) also have:

    ['Call', 'name', [args]]     function call
    ['Num', 12]                  number with 2+ digits = Peano constant

Syntax rules enforced here:
    - Name.(...)  is the only way to give a name its children. 'Name(' is an error.
    - Brackets only group.
    - A pair is written Mktp.a.b. There is no (a,b) style and there are no commas.
    - A Literal is one symbol of any kind: a bare digit (5) or a quoted symbol ('a', '%', '.').
    - Capital first letter = built-in, lowercase (or _) first letter = variable / function.
"""

BUILTINS = {"Nil": 0, "MT": 0, "Yes": 0, "No": 0, "Nx": 1, "Dsq": 2, "Mktp": 2}  # name -> child count


class LangError(Exception):
    """An error in the user's program (with line info)."""


# A quoted Literal like 'a' is swapped for a placeholder (LIT + code + END) before the
# text is split on dots, brackets and spaces, so that 'a', '.', '(' or ' ' are safe.
LIT, END = "\x01", "\x02"


def protect(s):
    """Replace every quoted Literal 'c' with a placeholder. Spaces are kept."""
    out, i = [], 0
    while i < len(s):
        if s[i] != "'":
            out.append(s[i])
            i += 1
        elif i + 2 < len(s) and s[i + 2] == "'":
            out.append(f"{LIT}{ord(s[i + 1])}{END}")
            i += 3
        else:
            raise ValueError("A quoted Literal is exactly one symbol between quotes, like 'a'")
    return "".join(out)


def unprotect(s):
    """Placeholders back to 'c', for error messages."""
    out, i = [], 0
    while i < len(s):
        if s[i] == LIT and END in s[i:]:
            j = s.index(END, i)
            out.append("'" + chr(int(s[i + 1:j])) + "'")
            i = j + 1
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def lit_char(token):
    """The symbol inside a placeholder token."""
    if not (token.startswith(LIT) and token.endswith(END) and token[1:-1].isdigit()):
        raise ValueError(f"Bad Literal in: {unprotect(token)}")
    return chr(int(token[1:-1]))


def compact(s):
    """Remove all whitespace (except inside a quoted Literal)."""
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

    if head[0] == LIT:
        if children:
            raise ValueError(f"A Literal can't have children: {s}")
        return ["Con", lit_char(head)]

    if head[0].isdigit():
        if not head.isdigit() or len(head) != 1:
            raise ValueError(f"A bare digit is a Literal (one digit), got '{head}'. Write a symbol as 'a'")
        if children:
            raise ValueError(f"A Literal can't have children: {s}")
        return ["Con", head]

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
def _expr(s, funcs, bound, allow_hash):
    s = _unwrap(s)
    parts = split_top(s, ".")
    if not parts:
        raise ValueError("Empty expression")
    head, rest = parts[0], parts[1:]
    if head.startswith("("):
        raise ValueError(f"A bracket group can't take arguments in: {s}")

    # literals and numbers
    if head.startswith(LIT):
        if rest:
            raise ValueError(f"A Literal can't take arguments in: {s}")
        return ["Con", lit_char(head)]
    if head.isdigit():
        if rest:
            raise ValueError(f"A number can't take arguments in: {s}")
        return ["Con", head] if len(head) == 1 else ["Num", int(head)]
    if allow_hash and head.startswith("#") and head[1:].isdigit():
        if rest:
            raise ValueError(f"A number can't take arguments in: {s}")
        return ["Num", int(head[1:])]

    # in a call typed on the terminal, one bare symbol is a Literal:  toh.#2.a.b.c
    if allow_hash and len(head) == 1 and head not in "()" and head not in funcs and head not in bound:
        if rest:
            raise ValueError(f"A Literal can't take arguments in: {s}")
        return ["Con", head]

    # function call or variable
    if _is_var(head):
        if head in funcs:
            want = funcs[head]["args_count"]
            if len(rest) != want:
                raise ValueError(f"'{head}' takes {want} argument(s), got {len(rest)} in: {s}")
            return ["Call", head, [_expr(r, funcs, bound, allow_hash) for r in rest]]
        if head in bound:
            if rest:
                raise ValueError(f"Variable '{head}' can't take arguments in: {s}")
            return ["Var", head]
        hint = "   (a Literal is one symbol: a, %, 7)" if allow_hash else ""
        raise ValueError(f"Unknown name '{head}' in: {s}{hint}")

    # built-in
    if head not in BUILTINS:
        raise ValueError(f"Unknown built-in '{head}' in: {s}")
    if len(rest) != BUILTINS[head]:
        raise ValueError(f"{head} needs {BUILTINS[head]} child(ren), got {len(rest)} in: {s}")
    if not rest:
        return ["Con", head]
    return ["Op", head, [_expr(r, funcs, bound, allow_hash) for r in rest]]


def parse_expr(s, funcs, bound, allow_hash=False):
    """funcs: dict name -> function info (needs 'args_count'); bound: set of variable names."""
    s = compact(s)
    check_syntax(s)
    return _expr(s, funcs, bound, allow_hash)
