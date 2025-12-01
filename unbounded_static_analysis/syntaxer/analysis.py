#!/usr/bin/env python3
"""Syntactic analysis module for extracting constants and parameters from Java source.

This module uses tree-sitter to parse Java source files and extract:
- Static integer constants
- Method input parameters with their types
"""
import logging
import sys
from pathlib import Path

import tree_sitter
import tree_sitter_java
import jpamb

from . import query
from . import wager

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
parser = tree_sitter.Parser(JAVA_LANGUAGE)

def get_constants(srcfile, methodid):
    """Extract constants and input parameters from Java source.
    
    Args:
        srcfile: Path to the Java source file
        methodid: Method identifier to analyze
    
    Returns:
        tuple: (sorted_integers, input_params)
            - sorted_integers: List of integer constants found in the method
            - input_params: List of dicts with 'name' and 'type' keys for each parameter
    """
    # Parse Java source file
    with open(srcfile, "rb") as f:
        tree = parser.parse(f.read())
    
    # Locate class and method nodes
    simple_classname = str(methodid.classname.name)
    class_node = query.class_query(tree, simple_classname)

    method_name = methodid.extension.name
    method_params = methodid.extension.params
    method_node = query.method_query(class_node, method_name, method_params)

    # Extract input parameters
    params_node = method_node.child_by_field_name("parameters")
    assert params_node and params_node.text, "Method must have parameters node"
    input_params = query.input_value_query(params_node)

    # Extract method body
    body = method_node.child_by_field_name("body")
    assert body and body.text, "Method must have a body"

    # Extract static integer constants from method body
    static_integers = query.static_integer_query(body)

    # Note: Wager-based prediction code is disabled in favor of abstract interpretation
    # The wager module can still be used for heuristic-based analysis if needed
    
    return sorted(static_integers), input_params
