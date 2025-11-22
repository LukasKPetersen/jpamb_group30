# Added a return value change
I have added a "not done" return value in two places to not squash useful outputs when the fuzzer is stopped early.

in `interpreter.py` I have changed the return value when the `stop_event` is set.
I also added it in the array size check to return `"not done"` if the array size exceeds 100,000 in the case `jvm.NewArray(type=jvm.Int(), dim=dim)`