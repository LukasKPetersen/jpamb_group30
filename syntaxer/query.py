"""Tree-sitter query functions for extracting information from Java source code.

This module provides query functions to locate classes, methods, and various
Java language constructs using tree-sitter.
"""
import logging
import sys
from pathlib import Path

import tree_sitter
import tree_sitter_java
import jpamb

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
parser = tree_sitter.Parser(JAVA_LANGUAGE)

logging.basicConfig(level=logging.DEBUG)

# === Class and Method Queries ===

def class_query(tree, class_name):
    """Find a class node by name in the syntax tree."""
    class_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        f"""
            (class_declaration 
                name: ((identifier) @class-name (#eq? @class-name "{class_name}"))) @class
        """,
    )

    for node in tree_sitter.QueryCursor(class_q).captures(tree.root_node)["class"]:
        return node

    logging.error(f"FAIL: Could not find a class of name '{class_name}'")
    sys.exit(-1)


def method_query(class_node, method_name, method_params):
    """Find a method node by name and parameters within a class node."""
    method_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        f"""
            (method_declaration name: 
                ((identifier) @method-name (#eq? @method-name "{method_name}"))) @method
        """,
    )

    for node in tree_sitter.QueryCursor(method_q).captures(class_node)["method"]:

        # verify that parameters exist
        if not (p := node.child_by_field_name("parameters")):
            continue

        params = [c for c in p.children if c.type == "formal_parameter"]

        # verify parameter length
        if len(params) != len(method_params):
            continue

        for tn, t in zip(method_params, params):
            if (tp := t.child_by_field_name("type")) is None:
                break

            if tp.text is None:
                break

            # TODO: Implement parameter type checking if needed
        else:
            return node
    else:
        logging.warning(f"FAIL: Could not find method '{method_name}' in the class")
        sys.exit(-1)


# === Query Helper Functions ===

def find_captures(query, node, query_name):
    """Check if a query matches any nodes."""
    return any(
        capture_name == query_name
        for capture_name, _ in tree_sitter.QueryCursor(query).captures(node).items()
    )


def find_all_captures(query, node, query_name):
    """Get all nodes matching a query capture name."""
    captures = tree_sitter.QueryCursor(query).captures(node)
    return captures.get(query_name, [])


# === Data Extraction Queries ===

def input_value_query(node):
    """Extract input parameter names and types from a parameters node."""
    input_q = tree_sitter.Query(JAVA_LANGUAGE, """(formal_parameter) @input""")
    found = find_all_captures(input_q, node, "input")
    if not found:
        logging.debug("No input values found")
        return []
    
    # Extract input parameter names and types from nodes
    input_params = []
    for param in found:
        name = param.child_by_field_name("name").text.decode('utf-8')
        type_node = param.child_by_field_name("type")
        param_type = type_node.text.decode('utf-8') if type_node else "unknown"
        input_params.append({"name": name, "type": param_type})
    return input_params


def static_integer_query(body_node):
    """Extract all integer literals from a method body."""
    int_q = tree_sitter.Query(JAVA_LANGUAGE, """(decimal_integer_literal) @int""")
    found = find_all_captures(int_q, body_node, "int")
    if not found:
        return []
    # Extract integer values from nodes
    return [int(node.text.decode('utf-8')) for node in found]


# === Pattern Detection Queries ===
# These queries detect specific Java patterns (assertions, division, loops, etc.)

def assert_query(body_node):
    """Check if the method body contains any assertions."""
    assert_q = tree_sitter.Query(JAVA_LANGUAGE, """(assert_statement) @assert""")
    found = find_captures(assert_q, body_node, "assert")
    logging.debug("Assertion found" if found else "No assertion found")
    return found


def division_query(body_node):
    """Check if the method body contains division operations."""
    divide_q = tree_sitter.Query(JAVA_LANGUAGE, """(binary_expression operator: "/") @divide""")
    found = find_captures(divide_q, body_node, "divide")
    logging.debug("Division found" if found else "No division found")
    return found


def out_of_bounds_query(body_node):
    """Check if the method body contains potential out-of-bounds access."""
    oob_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        """
        (method_invocation
            name: (identifier) @method-name
            arguments: (argument_list) @args
            (#match? @method-name "get|set|add|remove")) @oob
        """
    )
    found = find_captures(oob_q, body_node, "oob")
    logging.debug("Out of bounds access found" if found else "No out of bounds access found")
    return found


def null_query(body_node):
    """Check if the method body contains null literals."""
    null_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        """
        (null_literal) @null
        """,
    )
    found = find_captures(null_q, body_node, "null")
    logging.debug("Null literal found" if found else "No null literal found")
    return found


def array_access_query(body_node):
    """Check if the method body contains array access operations."""
    array_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        """
        (array_access) @array
        """,
    )
    found = find_captures(array_q, body_node, "array")
    logging.debug("Array access found" if found else "No array access found")
    return found


def loop_query(body_node):
    """Check if the method body contains loops (for or while)."""
    for_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        """
        (for_statement) @for
        """,
    )
    while_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        """
        (while_statement) @while
        """,
    )
    found_for = find_captures(for_q, body_node, "for")
    found_while = find_captures(while_q, body_node, "while")
    found = found_for or found_while
    logging.debug("Loop found" if found else "No loop found")
    return found