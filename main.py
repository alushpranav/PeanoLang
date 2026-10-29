import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "lib"))

from run import load_program, run_call, set_recursion_limit, to_python

set_recursion_limit(10000)

funcs = load_program(str(ROOT / "texts" / "sort.txt"))
assert to_python(run_call(funcs, "sort.[3,2,1]")) == [1, 2, 3]
print("Case 1 : Passed!")
assert to_python(run_call(funcs, "sort.[1]")) == [1]
print("Case 2 : Passed!")
assert to_python(run_call(funcs, "sort.MT")) == []
print("Case 3 : Passed!")
