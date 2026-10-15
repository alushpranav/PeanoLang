# Peano Language

A small teaching language where everything is Peano numbers, pattern matching and recursion.

## Folders

```
root/
  lib/     run.py, typecheck.py, utils.py, refer.py   (don't touch)
  texts/   your programs (.txt)
  refer/   ready-made functions you can reuse
```

## Run

```bash
python lib/run.py texts/mycode.txt "maxoftwo.#120.#130"
```

`"name.arg1.arg2"` calls the function `name`. Calls are type-checked before they run.

| Argument | Means |
|---|---|
| `#120` | Peano number |
| `7`, `a`, `%` | Literal (any one symbol) |
| `[#1,#4,#2]` / `[1,2,3]` / `[]` | list of Peano / list of digits / empty list |
| `(Mktp.#3.#4)` | pair |
| `Yes`, `No` | Boolean |

Output: numbers as `9`, lists as `[1, 2]`, literals as `'7'`, pairs as `(3, 1)`, Boolean as `Yes`/`No`.

### Options

| Option | What it does |
|---|---|
| `--strict` | enforces layout (2-space indents, `::` after signatures). Good for lab practice |
| `--raw` | prints raw `Nx(...)` / `Dsq(...)` instead of numbers |
| `--dump` | prints the parsed program |
| `--norefer` | doesn't look in `refer/` |

## Writing a program

```
maxoftwo Peano => Peano => Peano ::
  .Nil.x := x
  .x.Nil := x
  .(Nx.x).(Nx.y) := Nx.(zz)
    suchthat
      zz := maxoftwo.x.y
```

- Signature: `name Type => Type => ReturnType ::`
- Clauses `.pattern.pattern := result`, first match wins
- `suchthat` names sub-results, in order
- Calls and built-ins take children with a dot: `f.a.b`, `Nx.x`, `Dsq.x.xs`, `Mktp.a.b`. Brackets only group
- Built-ins start with a capital (`Nx`, `Dsq`, `Mktp`, `MT`, `Nil`, `Yes`, `No`), your functions with a lowercase letter
- Types: `Peano`, `Boolean`, `Literal`, `Seq.<type>`, `Tuple.<type>.<type>` (a `Seq` or `Tuple` always needs its types)
- A Literal is any one symbol. In a terminal call just write it (`toh.#3.a.b.c`). Inside a program write it in quotes (`'a'`, `'%'`), a bare digit (`7`) needs none. Use `d2p` / `p2d` to convert to / from Peano

## refer/ - reuse functions

1. Put `.txt` programs with ready-made functions in `refer/`
2. Run `python lib/refer.py`. It lists every function in `refer/index.txt`
3. Now your programs can use those functions without writing them. Your own functions win if the name is the same

Run `refer.py` again whenever you change a file in `refer/`.

## Use from Python (for tests)

Keep your test file in `root/` (next to `lib/` and `texts/`). It works from any folder.

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "lib"))

from run import load_program, run_call, to_python

funcs = load_program(str(ROOT / "texts" / "sort.txt"), strict=True)  # strict=True for --strict
assert to_python(run_call(funcs, "sort.[#3,#2,#1]")) == [1, 2, 3]
assert to_python(run_call(funcs, "sort.MT")) == []
print("Passed!")
```

`to_python` gives plain Python (int, list, tuple, bool, str). `fmt` gives the same text as the terminal. Errors raise `LangError`.
