import logging
import sys
from typing import List, Any
import tree_sitter
import tree_sitter_java
import itertools
from pathlib import Path

from jpamb.model import Input
from jpamb import jvm

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
parser = tree_sitter.Parser(JAVA_LANGUAGE)

log = logging
log.basicConfig(level=logging.DEBUG)

# TODO: Remove me
def get_java_type_name(t: jvm.Type) -> str:
    match t:
        case jvm.Int(): return "int"
        case jvm.Boolean(): return "boolean"
        case jvm.Char(): return "char"
        case jvm.Float(): return "float"

        case jvm.Array(jvm.Int()): return "int[]"
        case jvm.Array(jvm.Char()): return "char[]"
        case _: return "unknown"


def find_method_node(class_node, method_name, param_types: jvm.ParameterType):
    q = tree_sitter.Query(
        JAVA_LANGUAGE,
        f"""
            (method_declaration name: 
                ((identifier) @method-name (#eq? @method-name "{method_name}"))) @method
        """,
    )
    
    candidates = tree_sitter.QueryCursor(q).captures(class_node).get("method", [])
    
    for node in candidates:
        params_node = node.child_by_field_name("parameters")
        if not params_node:
            if len(param_types) == 0:
                return node
            continue
            
        formal_params = [c for c in params_node.children if c.type == "formal_parameter"]
        
        if len(formal_params) != len(param_types):
            continue
            
        match = True
        for i, fp in enumerate(formal_params):
            type_node = fp.child_by_field_name("type")
            if not type_node:
                match = False
                break
            
            source_type = type_node.text.decode('utf-8')
            expected_type = get_java_type_name(param_types[i])
            
            if source_type != expected_type:
                if expected_type == "String" and source_type.endswith("String"):
                    continue
                match = False
                break
        
        if match:
            return node
            
    return None


def find_class_node(tree, class_name_str):
    q = tree_sitter.Query(
        JAVA_LANGUAGE,
        f"""
            (class_declaration 
                name: ((identifier) @class-name (#eq? @class-name "{class_name_str}"))) @class
        """,
    )
    captures = tree_sitter.QueryCursor(q).captures(tree.root_node)
    nodes = captures.get("class", [])
    if nodes:
        return nodes[0]
    return None

def extract_literals(node, params_types) -> dict[jvm.Type, List[Any]]:
    my_pretty_map = {}

    for pt in set(params_types):
        literals = []

        match pt:
            case jvm.Int() | jvm.Array(jvm.Int()):
                # TODO: what if it finds an int array literal?
                q = tree_sitter.Query(JAVA_LANGUAGE, "(decimal_integer_literal) @int")
                for n in tree_sitter.QueryCursor(q).captures(node).get("int", []):
                    try:
                        integer = int(n.text.decode('utf-8'))
                        literals.append(integer)
                        literals.append(integer + 1)
                        literals.append(integer - 1)
                    except ValueError:
                        pass
            case jvm.Boolean() | jvm.Array(jvm.Boolean()):
                # TODO: what if it finds a boolean array literal?
                q = tree_sitter.Query(JAVA_LANGUAGE, "(true) @true (false) @false")
                for n in tree_sitter.QueryCursor(q).captures(node).get("true", []):
                    literals.append(True)
                for n in tree_sitter.QueryCursor(q).captures(node).get("false", []):
                    literals.append(False)
                # Remove duplicates
                literals = list(set(literals))
            case jvm.Char() | jvm.Array(jvm.Char()):
                # TODO: what if it finds a char array literal?
                q = tree_sitter.Query(JAVA_LANGUAGE, '(character_literal) @char')
                for n in tree_sitter.QueryCursor(q).captures(node).get("char", []):
                    text = n.text.decode('utf-8')
                    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
                        char_value: str = text[1:-1]
                        if len(char_value) == 1:
                            literals.append(char_value)
            case _:
                log.error(f"Static variable extraction not implemented for type {pt}")
                raise NotImplementedError(f"Static variable extraction not implemented for type {pt}")
    
        my_pretty_map[pt] = literals
    
    return my_pretty_map

def generate_every_input_combination(literal_dict: dict[jvm.Type, List[Any]], param_types: jvm.ParameterType) -> List[Input]:
    # Literal combinations for each parameter type
    if len(param_types) == 0:
        return []  # No parameters, return empty combination
    
    lit_combi: List[List[jvm.Value]] = []
    for type in param_types:
        match type:
            case jvm.Int():
                ret = []
                for val in literal_dict.get(jvm.Int(), []):
                    ret.append(jvm.Value.int(val))
                lit_combi.append(ret)
            case jvm.Char():
                ret = []
                for val in literal_dict.get(jvm.Char(), []):
                    ret.append(jvm.Value.char(val))
                lit_combi.append(ret)
            case jvm.Boolean():
                ret = []
                for val in literal_dict.get(jvm.Boolean(), []):
                    ret.append(jvm.Value.boolean(val))
                lit_combi.append(ret)
            case jvm.Array(jvm.Char()):
                ret = []
                char_literals = literal_dict.get(jvm.Char(), [])

                for array_size in range(1, len(char_literals) + 1):
                    for v in itertools.product(char_literals, repeat=array_size):
                        arr = jvm.Value.array(jvm.Char(), list(v))
                        ret.append(arr)
                lit_combi.append(ret)
            case jvm.Array(jvm.Int()):
                ret = []
                int_literals = literal_dict.get(jvm.Int(), [])
                for array_size in range(1, len(int_literals) + 1):
                    for v in itertools.product(int_literals, repeat=array_size):
                        arr = jvm.Value.array(jvm.Int(), list(v))
                        ret.append(arr)
                lit_combi.append(ret)
            case _:
                raise NotImplementedError(f"Combination generation not implemented for type {param_types[0]}")


    input_combinations = []
    for combo in list(itertools.product(*lit_combi)):
        inp = Input(values=combo)
        input_combinations.append(inp)

    return input_combinations


def get_static_variables_combinations(method_signature: jvm.AbsMethodID) -> List[Input]:
    parts = method_signature.classname.parts
    rel_path = Path("src/main/java").joinpath(*parts).with_suffix(".java")
    file_path = Path.cwd() / rel_path
    
    if not file_path.exists():
        log.error(f"File not found: {file_path}")
        return []
        
    with open(file_path, "rb") as f:
        content = f.read()
        
    tree = parser.parse(content)
    
    class_name = method_signature.classname.name
    class_node = find_class_node(tree, class_name)
    if not class_node:
        log.error(f"Class {class_name} not found in {file_path}")
        return []

    method_name = method_signature.extension.name
    param_types = method_signature.extension.params

    method_node = find_method_node(class_node, method_name, param_types)
    if not method_node:
        log.error(f"Method {method_name} not found in class {class_name}")
        return []
    
    literal_dict = extract_literals(method_node, param_types)

    return generate_every_input_combination(literal_dict, param_types)