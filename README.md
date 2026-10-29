# Peano Language

A small teaching language where everything is Peano numbers, pattern matching and recursion.

## Folders

```
root/
  lib/     run.py, typecheck.py, utils.py, refer.py, literal_dict.yaml
  texts/   your programs (.txt)
  refer/   ready-made functions you can reuse
```

## Run

```bash
python lib/run.py texts/mycode.txt "maxoftwo.120.130"
```

`"name.arg1.arg2"` calls the function `name`. Calls are type-checked before they run.
You can also call a public function directly from `refer/` without a program file:

```bash
python lib/run.py "add.4.5"
```

Without a file, the first function name in the call must be listed in `refer/index.txt`.

| Argument | Means |
|---|---|
| `120` | Peano number |
| `Zero`, `SmlA`, `Pcnt` | Named Literal constants defined in `lib/literal_dict.yaml` |
| `[1,4,2]` / `[Zero,One,Two]` / `[]` | list of Peano / list of digit Literals / empty list |
| `(Mktp.3.4)` | pair |
| `Yes`, `No` | Boolean |

Output: numbers as `9`, lists as `[1, 2]` or `[Zero, One]`, Literals as their dictionary names, pairs as `(3, 1)`, Boolean as `Yes`/`No`.

### Options

| Option | What it does |
|---|---|
| `--raw` | prints raw `Nx(...)` / `Dsq(...)` instead of numbers |
| `--dump` | prints the parsed program |
| `--norefer` | doesn't look in `refer/` |
| `--recursion-limit N` | raises the recursion limit from the default `10000` (for deeply recursive programs) |

For example: `python lib/run.py texts/mycode.txt "sort.[5,4,3,2,1]" --recursion-limit 50000`.

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
- Built-ins start with a capital (`Nx`, `Dsq`, `Mktp`, `MT`, `Nil`, `Yes`, `No`, and names from `literal_dict.yaml`), your functions with a lowercase letter
- Types: `Peano`, `Boolean`, `Literal`, `Seq.<type>`, `Tuple.<type>.<type>` (a `Seq` or `Tuple` always needs its types)
- Literals must use their names from [`lib/literal_dict.yaml`](lib/literal_dict.yaml), both in programs and terminal calls. For example, use `SmlA` for `a` and `Zero` for `0`; direct quoted or bare symbol syntax is rejected.
- Peano numbers are written as ordinary numbers, without a `#` prefix, both in terminal calls and program expressions (for example, `sort.[1,2,3]`). A number like `1` is Peano; the named Literal `One` is the dictionary value for the symbol `1`.
- To look up a Literal, find its name and one-character value in `lib/literal_dict.yaml`. To add or change one, edit that file. Each entry has the form `Name: "symbol"`, such as `SmlA: "a"`. The interpreter reloads the dictionary each time it starts.
- Use `d2p` / `p2d` to convert between digit Literals and Peano numbers.

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

funcs = load_program(str(ROOT / "texts" / "sort.txt"))
assert to_python(run_call(funcs, "sort.[3,2,1]")) == [1, 2, 3]
assert to_python(run_call(funcs, "sort.MT")) == []
print("Passed!")
```

`to_python` gives plain Python (int, list, tuple, bool, str). `fmt` gives the same text as the terminal. Errors raise `LangError`.
