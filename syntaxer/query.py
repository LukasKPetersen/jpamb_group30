import logging
import tree_sitter
import tree_sitter_java
import jpamb
import sys
from pathlib import Path

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
parser = tree_sitter.Parser(JAVA_LANGUAGE)

log = logging
log.basicConfig(level=logging.DEBUG)

def class_query(tree, class_name):

    # treesitter query
    class_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        f"""
            (class_declaration 
                name: ((identifier) @class-name (#eq? @class-name "{class_name}"))) @class
        """,
    )

    for node in tree_sitter.QueryCursor(class_q).captures(tree.root_node)["class"]:
        return node

    log.error(f"FAIL: Could not find a class of name '{class_name}'")
    sys.exit(-1)


def method_query(class_node, method_name, method_params):

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

            # todo check for type.
        else:
            return node
    else:
        log.warning(f"FAIL: could not find a method of name {method_name} in the class")
        sys.exit(-1)

def find_captures(query, node, query_name):
    return any(
        capture_name == query_name
        for capture_name, _ in tree_sitter.QueryCursor(query).captures(node).items()
    )

def find_all_captures(query, node, query_name):
    captures = tree_sitter.QueryCursor(query).captures(node)
    return captures.get(query_name, [])

def input_value_query(node):
    input_q = tree_sitter.Query(JAVA_LANGUAGE, """(formal_parameter) @input""")
    found = find_all_captures(input_q, node, "input")
    if found:
        # Extract input parameter names and types from nodes
        input_params = []
        for param in found:
            name = param.child_by_field_name("name").text.decode('utf-8')
            type_node = param.child_by_field_name("type")
            param_type = type_node.text.decode('utf-8') if type_node else "unknown"
            input_params.append({"name": name, "type": param_type})
        return input_params
    else:
        log.debug("No input values found")
        return []

def static_integer_query(body_node):
    int_q = tree_sitter.Query(JAVA_LANGUAGE, """(decimal_integer_literal) @int""")
    found = find_all_captures(int_q, body_node, "int")
    if found:
        # Extract integer values from nodes
        integer_values = [int(node.text.decode('utf-8')) for node in found]
        return integer_values
    else:
        return []


#### Other queries ####
def assert_query(body_node):
    assert_q = tree_sitter.Query(JAVA_LANGUAGE, """(assert_statement) @assert""")
    found = find_captures(assert_q, body_node, "assert")
    if found:
        log.debug("Assertion found")
    else:
        log.debug("No assertion found")
    return found

def division_query(body_node):
    divide_q = tree_sitter.Query(JAVA_LANGUAGE, """(binary_expression operator: "/") @divide""")
    found = find_captures(divide_q, body_node, "divide")
    if found:
        log.debug("Division found")
    else:
        log.debug("No division found")
    return found

def out_of_bounds_query(body_node):
    oob_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        """
        (method_invocation
            name: (identifier) @method-name
            arguments: (argument_list) @args
            (#match? @method-name "get|set|add|remove")) @oob
        """,
    )
    found = find_captures(oob_q, body_node, "oob")
    if found:
        log.debug("Out of bounds access found")
    else:
        log.debug("No out of bounds access found")
    return found

def null_query(body_node):
    null_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        """
        (null_literal) @null
        """,
    )
    found = find_captures(null_q, body_node, "null")
    if found:
        log.debug("Null literal found")
    else:
        log.debug("No null literal found")
    return found

def array_access_query(body_node):
    array_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        """
        (array_access) @array
        """,
    )
    found = find_captures(array_q, body_node, "array")
    if found:
        log.debug("Array access found")
    else:
        log.debug("No array access found")
    return found

def loop_query(body_node):
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
    if found_for or found_while:
        log.debug("Loop found")
        return True
    else:
        log.debug("No loop found")
        return False