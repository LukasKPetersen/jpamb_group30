#!/usr/bin/env python3

import logging
import jpamb
from jpamb import jvm
import sys
from pathlib import Path

# Add the parent and current directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from syntaxer import analysis as syntaxer
from abstract_interpreter import abstract_interpretation

## SETUP
methodid = jpamb.getmethodid(
    "syntaxer",
    "1.0",
    "The Dirty Thirties",
    ["syntactic", "python"],
    for_science=True,
)

log = logging
log.basicConfig(level=logging.DEBUG)

srcfile = jpamb.sourcefile(methodid).relative_to(Path.cwd())

K, input_params = syntaxer.get_constants(srcfile, methodid)
log.debug("Extracted constants: %s", K)
log.debug("Extracted input parameters: %s", input_params)

# Convert string types to JVM types
def string_to_jvm_type(type_str):
    if type_str == 'int':
        return jvm.Int()
    elif type_str == 'boolean':
        return jvm.Int()  # Boolean is represented as int in JVM bytecode
    elif type_str.endswith('[]'):
        # Array type - not fully supported yet
        return jvm.Reference()
    else:
        # Assume reference type
        return jvm.Reference()

input_param_types = [string_to_jvm_type(param['type']) for param in input_params]

suite = jpamb.Suite()

log.debug(f"Input parameter types (JVM): {input_param_types}")

final_states, input_intervals = abstract_interpretation(suite, methodid, input_param_types, K)
log.debug(f"Final abstract states: {final_states}")
log.debug(f"Input intervals for fuzzing: {[str(iv) for iv in input_intervals]}")

# Print results for jpamb test framework
print(f"Possible outcomes: {final_states}")
print(f"Fuzzing intervals: {[str(iv) for iv in input_intervals]}")

sys.exit(0)
