"""refer.py - build refer/index.txt from the programs you keep in refer/.

usage (from anywhere):
    python lib/refer.py

Paste your .txt programs into root/refer/, run this once, and every function in
them is listed in refer/index.txt. After that run.py finds those functions by
itself, so a program does not have to write them again. Your own functions in
texts/ always win over the ones in refer/.

index.txt, one line per function:
    add Peano => Peano => Peano ::   -- demo.txt
"""
import sys
from pathlib import Path

from run import INDEX_NAME, REFER_DIR, add_from_refer, analyse, read_program
from typecheck import typecheck_program
from utils import LangError


def signature(func):
    return f"{func['name']} {' => '.join(func['args'] + [func['ret']])} ::"


def main():
    refer_dir = Path(REFER_DIR)
    refer_dir.mkdir(exist_ok=True)
    files = sorted(p for p in refer_dir.glob("*.txt") if p.name != INDEX_NAME)
    if not files:
        print(f"Nothing to index: put your .txt programs in {refer_dir}")
        return 1

    # 1. read every file; one name must not be defined in two files
    problems, owner, listing = [], {}, []
    for path in files:
        try:
            funcs = read_program(path)
        except LangError as e:
            problems.append(f"{path.name}: {e}")
            continue
        for name, func in funcs.items():
            if name in owner:
                problems.append(f"'{name}' is defined in both {owner[name]} and {path.name}")
            else:
                owner[name] = path.name
                listing.append((path.name, signature(func)))

    # 2. check each file (it may use functions of the other files)
    if not problems:
        for path in files:
            funcs = read_program(path)
            for func in funcs.values():
                func["file"] = f"refer/{path.name}"
            try:
                add_from_refer(funcs, index=owner, refer_dir=refer_dir)
                typecheck_program(analyse(funcs))
            except (LangError, ValueError) as e:
                problems.append(f"{path.name}: {e}")

    if problems:
        print("index.txt NOT updated. Fix these first:")
        for p in problems:
            print("  -", p)
        return 1

    lines = ["-- made by refer.py, do not edit. Run  python lib/refer.py  to rebuild.",
             "-- signature                                   -- file"]
    lines += [f"{sig}   -- {file}" for file, sig in listing]
    (refer_dir / INDEX_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Indexed {len(listing)} function(s) from {len(files)} file(s) -> refer/{INDEX_NAME}")
    for file, sig in listing:
        print(f"  {sig}   -- {file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
