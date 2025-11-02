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
    log.debug(f"Searching for class: {class_name}")

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
    log.debug(f"Searching for method {method_name}")

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
            log.debug(f"Could not find parameteres of {method_name}")
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
            log.debug(f"Parameter text: {tp.text}")
            log.debug(f"Expected type: {tn}")
        else:
            return node
    else:
        log.warning(f"FAIL: could not find a method of name {method_name} in the class")
        sys.exit(-1)


def assert_query(body_node):
    assert_q = tree_sitter.Query(JAVA_LANGUAGE, """(assert_statement) @assert""")

    return any(
        capture_name == "assert"
        for capture_name, _ in tree_sitter.QueryCursor(assert_q).captures(body_node).items()
    )

def divide_query(body_node):
    divide_q = tree_sitter.Query(JAVA_LANGUAGE, """(binary_expression operator: "/") @divide""")

    return any(
        capture_name == "divide"
        for capture_name, _ in tree_sitter.QueryCursor(divide_q).captures(body_node).items()
    )