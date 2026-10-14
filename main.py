import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "lib"))

from run import load_program, run_call, to_python

funcs = load_program(
    str(ROOT / "texts" / "sort.txt"), strict=True
)  # strict=True for --strict
assert to_python(run_call(funcs, "sort.[#3,#2,#1]")) == [1, 2, 3]
print("Case 1 : Passed!")
assert to_python(run_call(funcs, "sort.[#1]")) == [1]
print("Case 2 : Passed!")
assert to_python(run_call(funcs, "sort.MT")) == []
print("Case 3 : Passed!")
