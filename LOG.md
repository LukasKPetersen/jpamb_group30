# Added a return value change
I have added a "not done" return value in two places to not squash useful outputs when the fuzzer is stopped early.

in `interpreter.py` I have changed the return value when the `stop_event` is set.
I also added it in the array size check to return `"not done"` if the array size exceeds 100,000 in the case `jvm.NewArray(type=jvm.Int(), dim=dim)`

# Maria's smart remark
Right now we find static literals add + and - 1 to them. What if it is the biggest or smallest integer? Does a overflow happen? We should create a test for that.

# A problem with running forever ("*")
I have added in the intepreter that it runs in `range(1000000)` (one more zero than before). because of big numbers in `jpamb.cases.Calls.allPrimesArePositive` and when you allow the fuzzer to run longer. We need to figure something out here?

# He forgot assertion errors in `jpamb.cases.Dependent.divisionLoop`
I have added a case for `1024` that triggers an assertion error when dividing by 2 five times.

# Merging of CFG
# - Check in `interpreter.py` `run()` that it is correct
# - `CFG.py` has prints in them