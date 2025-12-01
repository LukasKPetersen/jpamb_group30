#!/usr/bin/env python3
import logging
import sys
from pathlib import Path

from interval_abstraction import Interval
from jpamb import jvm
import jpamb

# Add directories to Python path for imports
# sys.path.insert(0, str(Path(__file__).parent.parent))
# sys.path.insert(0, str(Path(__file__).parent))

import analysis as syntaxer
from abstract_interpreter import abstract_interpretation

# === Type Conversion ===
def string_to_jvm_type(type_str: str) -> jvm.Type:
    if type_str == 'int':
        return jvm.Int()
    elif type_str == 'boolean':
        return jvm.Int()  # Boolean as int
    elif type_str.endswith('[]'):
        return jvm.Reference()  # Array types (not handled by this analysis)
    else:
        return jvm.Reference()  # Object types (not handled by this analysis)


def analyze_method(method_signature: str) -> tuple[set[str], list[Interval]]:
    # Parse method identifier
    methodid = jvm.AbsMethodID.decode(method_signature)
    
    # Get source file and extract constants
    suite = jpamb.Suite()
    srcfile = jpamb.sourcefile(methodid).relative_to(Path.cwd())
    K, input_params = syntaxer.get_constants(srcfile, methodid)
    
    # Convert parameter types
    input_param_types = [string_to_jvm_type(param['type']) for param in input_params]
    
    # Run abstract interpretation
    final_states, input_intervals = abstract_interpretation(suite, methodid, input_param_types, K)
    
    return final_states, input_intervals


# TODO: remove this
# # === Configuration ===
# methodid = jpamb.getmethodid(
#     "syntaxer",
#     "1.0",
#     "The Dirty Thirties",
#     ["syntactic", "python"],
#     for_science=True,
# )

# logging.basicConfig(level=logging.DEBUG)

# # Extract constants and parameters
# srcfile = jpamb.sourcefile(methodid).relative_to(Path.cwd())

# K, input_params = syntaxer.get_constants(srcfile, methodid)
# logging.debug("Extracted constants: %s", K)
# logging.debug("Extracted input parameters: %s", input_params)

# input_param_types = [string_to_jvm_type(param['type']) for param in input_params]

# # Run abstract interpretation
# suite = jpamb.Suite()
# logging.debug(f"Input parameter types (JVM): {input_param_types}")

# print(analyze_method(methodid.encode()))
# print("---------")


# final_states, input_intervals = abstract_interpretation(suite, methodid, input_param_types, K)

# # === Output Results ===
# print(f"Possible outcomes: {final_states}")
# print(f"Fuzzing intervals: {[str(iv) for iv in input_intervals]}")

# sys.exit(0)
