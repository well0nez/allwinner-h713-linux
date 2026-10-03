#!/usr/bin/env python3
"""Check that the PC tools stay within what Python 3.9 parses and runs.

FLASHING.md promises 3.9+, the maintainer runs 3.12, and nothing ran the tools on 3.9 until A1
found 24 `X | Y` signatures h713-extract could not import there (doku/61 row 100). This is that
run without a 3.9 interpreter: every file is parsed with the 3.9 grammar (match, except*, type
parameters fail there), then searched for what the grammar lets through but 3.9 does not run:
PEP 604 unions in an annotation 3.9 evaluates at import -- a def's arguments and return, a class
or module attribute -- without `from __future__ import annotations`; parenthesised context
managers with several items (3.10); library names of 3.10+ (the LATER tables below).

Usage:  python3 tools/check-py39.py [PATH ...]      -- default: installer/ beside tools/

A directory is walked for *.py and for the suffix-less scripts whose first line names python.
One line per finding, `file:line: what`; exit 1 on a finding, 0 when clean. A check, not a
proof: what 3.9 lacks and the tables do not name (an f-string reusing its own quote, 3.12)
still needs a run on 3.9.
"""

import ast
import os
import re
import sys

GRAMMAR = (3, 9)
SKIP_DIRS = ("__pycache__", ".git", "out", "tmp", "build")
SHEBANG = re.compile(rb"^#!.*python")
PAREN_WITH = re.compile(r"^\s*(async\s+)?with\s*\(")
LATER = {                      # a name -> where the library got it, and when
    "pairwise": "itertools.pairwise (3.10)", "bit_count": "int.bit_count (3.10)",
    "TypeAlias": "typing.TypeAlias (3.10)", "ParamSpec": "typing.ParamSpec (3.10)",
    "Concatenate": "typing.Concatenate (3.10)", "TypeGuard": "typing.TypeGuard (3.10)",
    "tomllib": "tomllib (3.11)", "ExceptionGroup": "ExceptionGroup (3.11)",
    "StrEnum": "enum.StrEnum (3.11)", "file_digest": "hashlib.file_digest (3.11)",
    "batched": "itertools.batched (3.12)",
}
LATER_KEYWORDS = {("zip", "strict"): "3.10", ("dataclass", "slots"): "3.10",   # (callable, keyword)
                  ("dataclass", "kw_only"): "3.10"}


def _is_script(path):
    try:
        with open(path, "rb") as fh:
            return bool(SHEBANG.match(fh.readline()))
    except OSError:
        return False


def python_files(paths):
    """Every file to check: the named files, and under a directory every *.py plus the
    suffix-less scripts whose first line names python. Sorted, so two runs read alike."""
    found = []
    for path in paths:
        if os.path.isfile(path):
            found.append(path)
            continue
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                if name.endswith(".py") or (not os.path.splitext(name)[1] and _is_script(full)):
                    found.append(full)
    return sorted(found)


def _annotations(node, evaluated=True):
    """Every annotation 3.9 evaluates. A def's arguments and return are evaluated when the def
    statement runs, wherever it stands; an attribute's when its module or class body runs; a
    local variable's never."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        a = node.args
        for arg in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg]:
            if arg is not None and arg.annotation is not None:
                yield arg.annotation
        if node.returns is not None:
            yield node.returns
        for child in node.body:
            yield from _annotations(child, False)
        return
    if isinstance(node, ast.AnnAssign):
        if evaluated:
            yield node.annotation
        return
    for child in ast.iter_child_nodes(node):
        yield from _annotations(child, True if isinstance(node, ast.ClassDef) else evaluated)


def _future_annotations(tree):
    return any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and
               any(alias.name == "annotations" for alias in n.names) for n in tree.body)


def check_source(path, source):
    """The findings of one file: [(line, what)], sorted by line."""
    try:
        tree = ast.parse(source, path, feature_version=GRAMMAR)
    except SyntaxError as e:
        return [(e.lineno or 0, "not %d.%d syntax: %s" % (GRAMMAR + (e.msg,)))]
    lines = source.splitlines()
    findings = []
    if not _future_annotations(tree):
        for ann in _annotations(tree):
            if any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) for n in ast.walk(ann)):
                findings.append((ann.lineno, "PEP 604 union in an annotation 3.9 evaluates -- "
                                             "add `from __future__ import annotations` (3.10)"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.With, ast.AsyncWith)) and len(node.items) > 1 \
                and PAREN_WITH.match(lines[node.lineno - 1]):
            findings.append((node.lineno, "parenthesised context managers (3.10)"))
        elif isinstance(node, ast.Attribute) and node.attr in LATER:
            findings.append((node.lineno, LATER[node.attr]))
        elif isinstance(node, ast.Name) and node.id in LATER:
            findings.append((node.lineno, LATER[node.id]))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name.split(".")[0] for alias in node.names]
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module.split(".")[0])
            findings += [(node.lineno, LATER[name]) for name in names if name in LATER]
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "id", getattr(node.func, "attr", None))
            for keyword in node.keywords:
                since = LATER_KEYWORDS.get((name, keyword.arg))
                if since:
                    findings.append((node.lineno, "%s(%s=) (%s)" % (name, keyword.arg, since)))
    return sorted(findings)


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if "-h" in args or "--help" in args:
        print(__doc__)
        return 0
    paths = [a for a in args if not a.startswith("-")]
    if not paths:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        paths = [os.path.join(root, "installer")]
    files = python_files(paths)
    total = 0
    for path in files:
        with open(path, "rb") as fh:
            source = fh.read().decode("utf-8", "replace")
        for line, what in check_source(path, source):
            print("%s:%d: %s" % (path, line, what))
            total += 1
    print("check-py39: %d file(s), %d finding(s)" % (len(files), total))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
