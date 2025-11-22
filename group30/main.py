#!/usr/bin/env python3
import sys
from fuzzer_random.main import RandomFuzzer
import jpamb


if len(sys.argv) == 2 and sys.argv[1] == "info":
    print("Fuzzer") # Name
    print("0.1") # Version
    print("Group 30") # Student Group Name
    print("fuzzer,python") # Tags
    print("no")  # For science
    exit(0)


argument = None
# Get the method we need to fuzz
if len(sys.argv) == 2:
    method_signature = jpamb.parse_methodid(sys.argv[1])

# Get the method and argument?
# FIXME: should this be possible?
elif len(sys.argv) == 3:
    method_signature = jpamb.parse_methodid(sys.argv[1])
    argument = jpamb.parse_input(sys.argv[2])
else:
    print("Usage: fuzzer.py <methodid> [<input>]", file=sys.stderr)
    sys.exit(1)



fuzzer = RandomFuzzer(method_signature, argument)

fuzzer.run()