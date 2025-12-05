#!/usr/bin/env python3
import sys
# from fuzzer_random.main import RandomFuzzer
# from fuzzer_syntactic_analysis.main import SyntacticAnalysisFuzzer
# from fuzzer_central_expansion.main import CentralExpansionFuzzer
# from fuzzer_coverage_guided.main import CoverageGuidedStrategy
# from fuzzer_central_expansion_and_syntactic_analysis.main import CentralExpansionAndSyntaticAnalysisFuzzer
from fuzzer_full.main import FullFuzzer
import jpamb

methodid = jpamb.getmethodid(
    "hybrid_fuzzer",
    "1.0",
    "Group 30",
    ["hybrid_fuzzer", "python", "unbounded static analysis", "syntax tree analysis", "CFG"],
    for_science=True,
)

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



# fuzzer = RandomFuzzer(method_signature, argument)
# fuzzer = SyntacticAnalysisFuzzer(method_signature, argument)
# fuzzer = CentralExpansionFuzzer(method_signature, argument)
# fuzzer = CoverageGuidedStrategy(method_signature, argument)
# fuzzer = CentralExpansionAndSyntaticAnalysisFuzzer(method_signature, argument)
fuzzer = FullFuzzer(method_signature, argument)

fuzzer.run()