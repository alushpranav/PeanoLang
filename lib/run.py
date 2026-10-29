"""run.py - interpreter for the Peano language.

usage:
    python run.py program.txt                         load and type-check the program
    python run.py program.txt "maxoftwo.4.9"           run a call
    python run.py "add.4.9"                           run a function from refer/
    python run.py program.txt "append.[1,2].[3]"       lists use [ ]
options:
    --dump     print the parsed program
    --raw      print the result as raw Nx(...) / Dsq(...)
    --norefer  do not look in refer/ for functions the file does not define
    --recursion-limit N  set the recursion limit (default: 10000)
"""
import re
import sys
import threading
from pathlib import Path
from pprint import pprint

from typecheck import infer, typecheck_program
from utils import compact as _compact
from utils import (LangError, break_pattern, collect_vars, parse_expr,
                   split_top, protect, unprotect, where, LITERAL_DICT)

DEFAULT_RECURSION_LIMIT = 10_000
sys.setrecursionlimit(DEFAULT_RECURSION_LIMIT)


def set_recursion_limit(limit=DEFAULT_RECURSION_LIMIT):
    """Set Python's recursion limit for interpreting recursive Peano programs."""
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("recursion limit must be a positive integer")
    sys.setrecursionlimit(limit)

LITERAL_NAMES = {}
for _name, _symbol in LITERAL_DICT.items():
    LITERAL_NAMES.setdefault(_symbol, _name)


# ================================================================ loading
def read_program(path):
    functions = {}
    func = clause = None
    in_such = False

    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    for n, raw in enumerate(lines, 1):
        text = raw.strip()
        if not text or text.startswith(("//", "--", "#")):
            continue  # blank or comment line
        indent = len(raw) - len(raw.lstrip())

        def fail(msg):
            raise LangError(f"line {n}: {msg}")

        def compact(s):  # same as utils.compact, but errors name the line
            try:
                return _compact(s)
            except ValueError as e:
                fail(str(e))

        if "\t" in raw[:indent]:
            fail("tabs are not allowed for indentation")
        if indent % 2:
            fail(f"indentation must use 2-space steps, got {indent} spaces")

        if indent == 0:  # function header
            if not text.endswith("::"):
                fail("function signature must end with '::'")
            header_text = text[:-2].rstrip()
            name, _, rest = header_text.partition(" ")
            if not rest.strip():
                fail("header must look like:  name Type => Type => ReturnType ::")
            if not (name[0].islower() or name[0] == "_"):
                fail(f"function name '{name}' must start with a lowercase letter")
            if name in functions:
                fail(f"function '{name}' is defined twice")
            parts = rest.split("=>")
            ret = parts.pop().split("::")[0].strip()
            args = [a.strip() for a in parts]
            if not args or not all(args) or not ret:
                fail("header must look like:  name Type => Type => ReturnType")
            func = {
                "name": name,
                "ret": ret,
                "args": args,
                "args_count": len(args),
                "clauses": [],
                "line": n,
            }
            functions[name] = func
            clause, in_such = None, False

        elif text.startswith("."):  # clause
            if indent != 2:
                fail(f"clause must be indented exactly 2 spaces, got {indent}")
            if func is None:
                fail("clause before any function header")
            lhs, sep, body = text.partition(":=")
            if not sep:
                fail("clause needs ':='")
            clause = {
                "lhs": compact(lhs),
                "body": compact(body),
                "suchthat": [],
                "line": n,
            }
            func["clauses"].append(clause)
            in_such = False

        elif text.startswith("suchthat"):
            if indent != 4:
                fail(f"'suchthat' must be indented exactly 4 spaces, got {indent}")
            if clause is None:
                fail("'suchthat' must be inside a clause")
            if clause["suchthat"] or in_such:
                fail("a clause can have only one 'suchthat' block")
            in_such = True

        elif in_such and ":=" in text:  # suchthat entry:  name := expr
            if indent != 6:
                fail(
                    f"suchthat definitions must be indented exactly 6 spaces, got {indent}"
                )
            name, _, expr = text.partition(":=")
            name = compact(name)
            if not name or not (name[0].islower() or name[0] == "_"):
                fail(f"bad suchthat name '{name}'")
            clause["suchthat"].append({"name": name, "raw": compact(expr), "line": n})

        else:
            fail("can't understand this line")

    return functions


def _add_names(seen, new, functions):
    for v in new:
        if v in seen:
            raise ValueError(f"Variable '{v}' is used twice in one clause")
        if v in functions:
            raise ValueError(f"Variable '{v}' has the same name as a function")
        seen.append(v)


def analyse(functions):
    """Pass 2: parse patterns and expressions into trees, and check them."""
    for fname, func in functions.items():
        if not func["clauses"]:
            raise LangError(f"{where(func, func['line'])}: function has no clauses")
        for clause in func["clauses"]:
            try:
                args = split_top(clause["lhs"], ".")
                if len(args) != func["args_count"]:
                    raise ValueError(
                        f"'{fname}' takes {func['args_count']} argument(s), clause has {len(args)}"
                    )
                patterns = [break_pattern(a) for a in args]
                seen = []
                _add_names(
                    seen, [v for p in patterns for v in collect_vars(p)], functions
                )

                for st in clause["suchthat"]:  # in order: each may use the earlier ones
                    st["tree"] = parse_expr(st["raw"], functions, set(seen))
                    _add_names(seen, [st["name"]], functions)

                clause["args"] = args
                clause["patterns"] = patterns
                clause["body_tree"] = parse_expr(clause["body"], functions, set(seen))
            except ValueError as e:
                raise LangError(f"{where(func, clause['line'])}: {unprotect(str(e))}")
    return functions


# ================================================================ refer/ folder
# root/refer/ holds ready-made functions. refer.py lists every function in
# refer/index.txt, one line each:   add Peano => Peano => Peano ::   -- demo.txt
# A function you use but did not write is loaded from the file named there.
REFER_DIR = Path(__file__).resolve().parent.parent / "refer"
INDEX_NAME = "index.txt"


def read_index(refer_dir=REFER_DIR):
    """index.txt -> {function name: file name}. No index means an empty one."""
    index = {}
    path = Path(refer_dir) / INDEX_NAME
    if not path.exists():
        return index
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("//", "--")):
            continue
        signature, _, file = line.partition("::")
        name = signature.split()[0] if signature.split() else ""
        file = file.strip().lstrip("-").strip()
        if name and file:
            index[name] = file
    return index


def _names(text):
    """Every lowercase name written in text (functions and variables alike)."""
    return set(re.findall(r"\b[a-z_]\w*", text))


def called_names(func):
    """Names a function uses on a right-hand side that are not its own variables."""
    used = set()
    for clause in func["clauses"]:
        own = _names(clause["lhs"]) | {st["name"] for st in clause["suchthat"]}
        texts = [clause["body"]] + [st["raw"] for st in clause["suchthat"]]
        used |= set().union(*map(_names, texts)) - own
    return used


def add_from_refer(functions, call_text=None, index=None, refer_dir=REFER_DIR):
    """Add every function the program (or the call) uses but does not define,
    and that refer/ has. Your own functions always win. Works through
    functions that those functions use, too."""
    index = read_index(refer_dir) if index is None else index
    todo = {(name, None) for name in _names(protect(call_text or ""))}
    for func in list(functions.values()):
        todo.update((name, None) for name in called_names(func))
    cache = {}
    while todo:
        name, scope_file = todo.pop()
        if name in functions:
            continue
        file = index.get(name)
        if file is None:
            # Underscore helpers are private to their refer file. They are
            # reachable only through a function loaded from that same file.
            if not name.startswith("_") or scope_file is None:
                continue
            file = scope_file
        if file not in cache:
            path = Path(refer_dir) / file
            if not path.exists():
                raise LangError(f"refer/{INDEX_NAME} lists '{name}' in refer/{file}, "
                                f"but that file is gone. Run refer.py again")
            try:
                cache[file] = read_program(path)
            except LangError as e:
                raise LangError(f"in refer/{file}: {e}")
        func = cache[file].get(name)
        if func is None:
            raise LangError(f"refer/{INDEX_NAME} lists '{name}' in refer/{file}, "
                            f"but it is not there any more. Run refer.py again")
        func["file"] = f"refer/{file}"
        functions[name] = func
        todo.update((dep, file) for dep in called_names(func))
    return functions


def load_program(path, call=None, use_refer=True):
    """Read, check and type-check a program. A function it uses but does not
    define is taken from refer/ (call = the call text, so a function you only
    call, and never use in the file, is found too)."""
    functions = read_program(path)
    if use_refer:
        add_from_refer(functions, call)
    return typecheck_program(analyse(functions))  # always on: type errors stop the load


# ================================================================ values
# ('Nil',)  ('Nx', v)  ('MT',)  ('Dsq', head, tail)  ('Yes',)  ('No',)
# ('Lit', '5')  ('Mktp', a, b)
NIL = ("Nil",)


def peano(n):
    v = NIL
    for _ in range(n):
        v = ("Nx", v)
    return v


def fmt(v):
    """Readable output: Peano as a number and Literals by their dictionary names."""
    tag = v[0]
    if tag in ("Nil", "Nx"):
        n = 0
        while v[0] == "Nx":
            n += 1
            v = v[1]
        return str(n)
    if tag in ("Yes", "No"):
        return tag
    if tag == "Lit":
        return LITERAL_NAMES.get(v[1], repr(v[1]))
    if tag in ("MT", "Dsq"):
        items = []
        while v[0] == "Dsq":
            items.append(fmt(v[1]))
            v = v[2]
        return "[" + ", ".join(items) + "]"
    if tag == "Mktp":
        return "(" + fmt(v[1]) + ", " + fmt(v[2]) + ")"
    return repr(v)


def raw_fmt(v):
    tag = v[0]
    if tag == "Lit":
        return LITERAL_NAMES.get(v[1], repr(v[1]))
    if len(v) == 1:
        return tag
    return tag + "(" + ", ".join(raw_fmt(x) for x in v[1:]) + ")"


# ================================================================ running
def match(p, v, env):
    """Match pattern p against value v. Variables are stored in env."""
    kind = p[0]
    if kind == "Var":
        env[p[1]] = v
        return True
    if kind == "Con":
        name = p[1]
        expected = ("Lit", LITERAL_DICT[name]) if name in LITERAL_DICT else (name,)
        return v == expected
    if kind == "Op":
        if v[0] != p[1]:
            return False
        return all(match(cp, cv, env) for cp, cv in zip(p[2], v[1:]))
    return False


def evaluate(node, functions, env):
    kind = node[0]
    if kind == "Var":
        return env[node[1]]
    if kind == "Con":
        name = node[1]
        return ("Lit", LITERAL_DICT[name]) if name in LITERAL_DICT else (name,)
    if kind == "Num":
        return peano(node[1])
    if kind == "Op":
        return (node[1],) + tuple(evaluate(c, functions, env) for c in node[2])
    if kind == "Call":
        return call(functions, node[1], [evaluate(a, functions, env) for a in node[2]])
    raise LangError(f"internal error: unknown node {node}")


def call(functions, name, args):
    """Try the clauses top to bottom. The first match wins."""
    for clause in functions[name]["clauses"]:
        env = {}
        if all(match(p, a, env) for p, a in zip(clause["patterns"], args)):
            for st in clause["suchthat"]:
                env[st["name"]] = evaluate(st["tree"], functions, env)
            return evaluate(clause["body_tree"], functions, env)
    raise LangError(
        f"No clause of '{name}' matches: " + ", ".join(fmt(a) for a in args)
    )


def _split_list_items(text):
    """Split list contents on commas outside parentheses and nested lists."""
    if not text.strip():
        return []

    items = []
    start = 0
    paren_depth = 0
    bracket_depth = 0

    for i, char in enumerate(text):
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
            if paren_depth < 0:
                raise ValueError("Unmatched closing parenthesis in list")
        elif char == "[" and paren_depth == 0:
            bracket_depth += 1
        elif char == "]" and paren_depth == 0:
            bracket_depth -= 1
            if bracket_depth < 0:
                raise ValueError("Unexpected ']' in list")
        elif char == "," and paren_depth == 0 and bracket_depth == 0:
            item = text[start:i].strip()
            if not item:
                raise ValueError("Empty list element")
            items.append(item)
            start = i + 1

    if paren_depth != 0 or bracket_depth != 0:
        raise ValueError("Unbalanced brackets or parentheses in list")

    last = text[start:].strip()
    if not last:
        raise ValueError("Empty list element")
    items.append(last)
    return items


def convert_lists(expression):
    """Convert [a,b,c] list syntax into nested Dsq constructors ending in MT."""
    result = []
    i = 0

    while i < len(expression):
        char = expression[i]
        if char == "]":
            raise ValueError("Unexpected ']' in expression")
        if char != "[":
            result.append(char)
            i += 1
            continue

        # Find this list's matching closing bracket, respecting nested lists
        # and parentheses that may contain list syntax.
        start = i + 1
        j = start
        bracket_depth = 1
        paren_depth = 0

        while j < len(expression) and bracket_depth:
            current = expression[j]
            if current == "(":
                paren_depth += 1
            elif current == ")":
                paren_depth -= 1
                if paren_depth < 0:
                    raise ValueError("Unmatched closing parenthesis in expression")
            elif paren_depth == 0 and current == "[":
                bracket_depth += 1
            elif paren_depth == 0 and current == "]":
                bracket_depth -= 1
            j += 1

        if bracket_depth:
            raise ValueError("Unclosed '[' in expression")
        if paren_depth:
            raise ValueError("Unclosed '(' in expression")

        items = _split_list_items(expression[start : j - 1])
        if not items:
            converted = "MT"
        else:
            converted_items = [convert_lists(item) for item in items]
            tail = "MT"
            for item in reversed(converted_items):
                tail = f"(Dsq.({item}).({tail}))"
            converted = tail

        result.append(converted)
        i = j

    return "".join(result)


# ================================================================ use from a Python file
def run_call(functions, text):
    """Run a call written exactly like on the terminal, e.g. "maxoftwo.4.9"
    or "append.[1,2].[3]". Type-checks it, then returns the raw value."""
    tree = parse_expr(convert_lists(protect(text)), functions, set())
    try:
        infer(tree, {}, functions)  # type-check the call too
    except ValueError as e:
        raise LangError(f"in the call: {e}")
    return evaluate(tree, functions, {})


def to_python(v):
    """Raw value -> plain Python: Peano -> int, Seq -> list, Tuple -> (a, b),
    Boolean -> True/False, Literal -> '7' (a one-character string)."""
    tag = v[0]
    if tag in ("Nil", "Nx"):
        n = 0
        while v[0] == "Nx":
            n += 1
            v = v[1]
        return n
    if tag == "Yes":
        return True
    if tag == "No":
        return False
    if tag == "Lit":
        return v[1]
    if tag in ("MT", "Dsq"):
        items = []
        while v[0] == "Dsq":
            items.append(to_python(v[1]))
            v = v[2]
        return items
    if tag == "Mktp":
        return (to_python(v[1]), to_python(v[2]))
    raise LangError(f"internal error: unknown value {v}")


# ================================================================ command line
def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    options, positional = [], []
    recursion_limit = DEFAULT_RECURSION_LIMIT
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--recursion-limit":
            i += 1
            if i >= len(argv):
                print("Error: --recursion-limit needs a positive integer")
                return 1
            try:
                recursion_limit = int(argv[i])
            except ValueError:
                print("Error: --recursion-limit needs a positive integer")
                return 1
        elif arg.startswith("--recursion-limit="):
            try:
                recursion_limit = int(arg.split("=", 1)[1])
            except ValueError:
                print("Error: --recursion-limit needs a positive integer")
                return 1
        elif arg.startswith("--"):
            options.append(arg)
        else:
            positional.append(arg)
        i += 1
    try:
        set_recursion_limit(recursion_limit)
    except ValueError as e:
        print("Error:", e)
        return 1

    path = Path(positional[0]) if positional and Path(positional[0]).is_file() else None
    call_text = " ".join(positional[1:] if path else positional)

    if path is None:
        if not call_text:
            print("Error: provide a program file or a refer function call")
            return 1
        if "--norefer" in options:
            print("Error: a refer function call cannot be used with --norefer")
            return 1
        entry = call_text.split(".", 1)[0]
        if entry not in read_index():
            print(f"Error: no input file found, and '{entry}' is not in refer/index.txt")
            return 1

    try:
        if path is None:
            functions = {}
            add_from_refer(functions, call_text)
            typecheck_program(analyse(functions))
        else:
            functions = load_program(path, call=call_text,
                                     use_refer="--norefer" not in options)
        if "--dump" in options:
            pprint(functions, sort_dicts=False)
        if call_text:
            value = run_call(functions, call_text)
            print(raw_fmt(value) if "--raw" in options else fmt(value))
        elif "--dump" not in options:
            own = [n for n, f in functions.items() if not f.get("file")]
            ref = [n for n, f in functions.items() if f.get("file")]
            extra = f"  + from refer: {', '.join(ref)}" if ref else ""
            print(f"Loaded {len(own)} function(s): " + ", ".join(own) + extra)
    except (LangError, ValueError) as e:
        print("Error:", unprotect(str(e)))
        return 1
    except RecursionError:
        print("Error: recursion too deep")
        return 1
    return 0


if __name__ == "__main__":
    for size_mb in (512, 256, 64):  # big stack so deep recursion doesn't crash
        try:
            threading.stack_size(size_mb * 1024 * 1024)
            break
        except (ValueError, RuntimeError):
            continue
    result = []
    worker = threading.Thread(target=lambda: result.append(main(sys.argv)))
    worker.start()
    worker.join()
    sys.exit(result[0] if result else 1)
