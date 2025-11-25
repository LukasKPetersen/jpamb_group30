#!/usr/bin/env python3

import logging
import tree_sitter
import tree_sitter_java
import jpamb
import sys
from pathlib import Path
from . import query
from . import wager

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
parser = tree_sitter.Parser(JAVA_LANGUAGE)

def get_constants(srcfile, methodid):
    
    with open(srcfile, "rb") as f:
        tree = parser.parse(f.read())
    
    ## Class query
    simple_classname = str(methodid.classname.name)
    class_node = query.class_query(tree, simple_classname)

    ## Method query
    method_name = methodid.extension.name
    method_params = methodid.extension.params
    method_node = query.method_query(class_node, method_name, method_params)

    #### Find interesting input values ####
    # extract input parameters
    input_params = method_node.child_by_field_name("parameters")
    assert input_params and input_params.text

    # query input parameters
    input_params = query.input_value_query(input_params)
    param_dict = {}
    for i, param in enumerate(input_params, start=1):
        param_dict[param["name"]] = []

    # extract body
    body = method_node.child_by_field_name("body")
    assert body and body.text

    # static integers
    static_integers = query.static_integer_query(body)

    printwager = False
    if printwager:
        ## Create wager
        wager = wager.Wager()

        ## Assert query
        wager.assertion_error = 0.8 if query.assert_query(body) else 0.1

        ## Division query
        wager.divide_by_zero = 0.7 if query.division_query(body) else 0.01

        ## Null query
        wager.null_pointer = 0.8 if query.null_query(body) else 0.1

        ## Array query
        array_access = query.array_access_query(body)
        if array_access:
            wager.out_of_bounds = 0.8
            wager.divide_by_zero = 0.6 # why does this work? 
        else:
            wager.out_of_bounds = 0.1

        ## Loop query
        wager.inf = 0.7 if query.loop_query(body) else 0.1

        ## Print wager
        wager.print_wager()
    
    return sorted(static_integers), input_params

# sys.exit(0)
