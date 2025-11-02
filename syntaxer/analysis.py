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

## Create wager
wager = wager.Wager()

## Class query
simple_classname = str(methodid.classname.name)
class_node = query.class_query(tree, simple_classname)
log.debug("Found class '%s' in range: %s", simple_classname, class_node.range)

## Method query
method_name = methodid.extension.name
method_params = methodid.extension.params
method_node = query.method_query(class_node, method_name, method_params)
log.debug("Found method '%s' in range: %s", method_name, method_node.range)

# extract body
body = method_node.child_by_field_name("body")
assert body and body.text
log.debug("------ Method body ------")
for t in body.text.splitlines():
    log.debug("line: %s", t.decode())
log.debug("---- End method body ----")

## Assert query
if query.assert_query(body):
    log.debug("Found assertion")
    wager.assertion_error = 0.8
else:
    log.debug("No assertion")
    wager.assertion_error = 0.2

## Division query
if query.divide_query(body):
    log.debug("Found division")
    wager.divide_by_zero = 0.8
else:
    log.debug("No division")
    wager.divide_by_zero = 0.2

## Print wager
wager.print_wager()

sys.exit(0)
