import sys

sys.setrecursionlimit(100000)  # everything in this language is recursion

from .lib.run import fmt, load_program, run_call, to_python

funcs = load_program("div.txt", strict=True)

result = run_call(funcs, "division.#120.#18")
print(to_python(result))
print(fmt(result))
