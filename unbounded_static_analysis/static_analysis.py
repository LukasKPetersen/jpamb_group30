#!/usr/bin/env python3
"""Static analysis entry point for jpamb test framework.

This script extracts program constants and input parameters from Java source code,
then performs abstract interpretation using interval analysis to determine possible
outcomes for a given method.
"""
import logging
import sys
from pathlib import Path

import jpamb
from jpamb import jvm

# Add directories to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from syntaxer import analysis as syntaxer
from abstract_interpreter import abstract_interpretation

# === Type Conversion ===
def string_to_jvm_type(type_str: str) -> jvm.Type:
    """Convert Java type string to JVM type.
    
    Args:
        type_str: Java type name (e.g., 'int', 'boolean', 'String[]')
    
    Returns:
        Corresponding jvm.Type instance
    """
    if type_str == 'int':
        return jvm.Int()
    elif type_str == 'boolean':
        return jvm.Int()  # Boolean is represented as int in JVM bytecode
    elif type_str.endswith('[]'):
        return jvm.Reference()  # Array types
    else:
        return jvm.Reference()  # Object types


def analyze_method(method_signature: str):
    """Analyze a Java method and return possible outcomes and input intervals.
    
    Args:
        method_signature: Method signature in the format "package.Class.method:(params)returnType"
                         e.g., "jpamb.cases.Simple.divideByN:(I)I"
    
    Returns:
        tuple: (final_states, input_intervals)
            - final_states: Set of possible outcomes ('ok', 'divide by zero', '*', etc.)
            - input_intervals: List of Interval objects for each input parameter
    
    Example:
        >>> final_states, input_intervals = analyze_method("jpamb.cases.Simple.divideByN:(I)I")
        >>> print(final_states)
        {'ok', 'divide by zero'}
    """
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


# === Configuration ===
methodid = jpamb.getmethodid(
    "syntaxer",
    "1.0",
    "The Dirty Thirties",
    ["syntactic", "python"],
    for_science=True,
)

logging.basicConfig(level=logging.DEBUG)

# === Extract Constants and Parameters ===
srcfile = jpamb.sourcefile(methodid).relative_to(Path.cwd())

K, input_params = syntaxer.get_constants(srcfile, methodid)
logging.debug("Extracted constants: %s", K)
logging.debug("Extracted input parameters: %s", input_params)

input_param_types = [string_to_jvm_type(param['type']) for param in input_params]

# === Run Abstract Interpretation ===
suite = jpamb.Suite()
logging.debug(f"Input parameter types (JVM): {input_param_types}")

final_states, input_intervals = abstract_interpretation(suite, methodid, input_param_types, K)

# === Output Results ===
print(f"Possible outcomes: {final_states}")
print(f"Fuzzing intervals: {[str(iv) for iv in input_intervals]}")

sys.exit(0)
