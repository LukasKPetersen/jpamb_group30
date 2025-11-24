#!/usr/bin/env python3

import logging
import tree_sitter
import tree_sitter_java
import jpamb
import sys
from pathlib import Path
import query as query
import wager as wager

## SETUP

methodid = jpamb.getmethodid(
    "syntaxer",
    "1.0",
    "The Dirty Thirties",
    ["syntactic", "python"],
    for_science=True,
)

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
parser = tree_sitter.Parser(JAVA_LANGUAGE)

log = logging
log.basicConfig(level=logging.DEBUG)

srcfile = jpamb.sourcefile(methodid).relative_to(Path.cwd())

with open(srcfile, "rb") as f:
    log.debug("Parse sourcefile: %s", srcfile)
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
log.debug("")
log.debug("------ Input parameters ------")
for t in input_params.text.splitlines():
    log.debug("line: %s", t.decode())
log.debug("")

# query input parameters
input_params = query.input_value_query(input_params)
param_dict = {}
for i, val in enumerate(input_params, start=1):
    log.debug("input parameter %d: %s", i, val)
    param_dict[val] = []

# extract body
body = method_node.child_by_field_name("body")
assert body and body.text
log.debug("")
log.debug("------ Method body ------")
for t in body.text.splitlines():
    log.debug("line: %s", t.decode())
log.debug("---- End method body ----")

# static integers
static_integers = query.static_integer_query(body)
for integer in static_integers:
    log.debug("integer: %s", integer)

log.debug("")

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

sys.exit(0)
