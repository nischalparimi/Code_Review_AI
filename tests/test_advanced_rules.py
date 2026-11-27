"""Focused positive, negative, and boundary tests for advanced AST rules."""

import ast

from analyzer.advanced_rules import (
    ExcessiveNestingRule,
    HighCyclomaticComplexityRule,
    PotentialSQLInjectionRule,
    UnusedImportRule,
    UnsafeSubprocessRule,
    WeakHashRule,
)
from analyzer.rules import EvalExecUsageRule, HardcodedSecretRule


def check(rule, source):
    return rule.check("sample.py", source, ast.parse(source))


def test_sec003_flags_shell_true_and_dynamic_command_with_line_and_guidance():
    source = "import subprocess\nsubprocess.run(user_command, shell=True)\nsubprocess.run(user_input)\n"
    issues = check(UnsafeSubprocessRule(), source)
    assert [(i.rule_id, i.severity, i.line) for i in issues] == [
        ("SEC003", "critical", 2), ("SEC003", "critical", 3),
    ]
    assert all("shell=False" in i.remediation for i in issues)


def test_sec003_does_not_flag_shell_false_or_literal_argument_lists():
    source = """import subprocess
subprocess.run(["git", "status"], shell=False)
subprocess.run(["git", "status"])
subprocess.run("git status", shell=False)
"""
    assert check(UnsafeSubprocessRule(), source) == []


def test_sec003_resolves_imported_callable_alias_and_ignores_other_run_methods():
    source = """from subprocess import run as execute
execute(f"tool {user_arg}")
other.run(command)
"""
    issues = check(UnsafeSubprocessRule(), source)
    assert [(i.rule_id, i.line) for i in issues] == [("SEC003", 2)]


def test_sec004_flags_md5_sha1_and_hashlib_new_but_not_strong_or_unrelated_calls():
    source = """import hashlib as hashes
from hashlib import sha1 as legacy_hash
hashes.md5(b"x")
legacy_hash(b"x")
hashes.new("md5")
hashes.sha256(b"x")
unrelated.md5()
"""
    issues = check(WeakHashRule(), source)
    assert [(i.rule_id, i.severity, i.line) for i in issues] == [
        ("SEC004", "warning", 3), ("SEC004", "warning", 4), ("SEC004", "warning", 5),
    ]
    assert "legacy compatibility" in issues[0].message


def test_sec004_detects_pycryptodome_md5_and_sha1_factories():
    source = "from Crypto.Hash import MD5, SHA1\nMD5.new()\nSHA1.new()\n"
    issues = check(WeakHashRule(), source)
    assert [(i.rule_id, i.line, "MD5" in i.message) for i in issues] == [
        ("SEC004", 2, True), ("SEC004", 3, False),
    ]


def test_sec005_flags_dynamic_sql_concatenation_fstring_format_and_percent_format():
    source = '''cursor.execute("SELECT * FROM users WHERE name='" + name + "'")
cursor.execute(f"SELECT * FROM users WHERE id={user_id}")
cursor.execute("SELECT * FROM users WHERE name='{}'".format(name))
cursor.execute("SELECT * FROM users WHERE id=%s" % user_id)
'''
    issues = check(PotentialSQLInjectionRule(), source)
    assert [(i.rule_id, i.severity, i.line) for i in issues] == [
        ("SEC005", "critical", 1), ("SEC005", "critical", 2),
        ("SEC005", "critical", 3), ("SEC005", "critical", 4),
    ]
    assert all("parameter" in i.remediation for i in issues)


def test_sec005_ignores_parameterized_queries_and_non_sql_strings():
    source = '''cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
cursor.execute("UPDATE users SET name=? WHERE id=?", (name, user_id))
logger.info(f"user={user_id}")
cursor.execute("print " + text)
'''
    assert check(PotentialSQLInjectionRule(), source) == []


def test_maint002_handles_used_aliases_annotations_and_multiple_imports():
    source = '''import os, json as serializer
from pathlib import Path
from datetime import datetime as UnusedDate

def load(path: Path) -> str:
    return serializer.dumps(os.fspath(path))
'''
    issues = check(UnusedImportRule(), source)
    assert [(i.rule_id, i.severity, i.line) for i in issues] == [("MAINT002", "info", 3)]
    assert "UnusedDate" in issues[0].message
    assert "reflection" in issues[0].message


def test_maint002_resolves_from_import_alias_and_ignores_future_and_star_imports():
    source = '''from __future__ import annotations
from package import used as alias, unused as spare
from package import *
def f() -> alias:
    return alias
'''
    issues = check(UnusedImportRule(), source)
    assert [(i.line, "spare" in i.message) for i in issues] == [(2, True)]


def test_maint002_reports_each_unused_name_from_one_import_statement():
    issues = check(UnusedImportRule(), "import os, json\n")
    assert [(i.rule_id, i.line) for i in issues] == [("MAINT002", 1), ("MAINT002", 1)]


def test_smell002_threshold_boundary_and_sequential_blocks():
    source = '''def sequential():
    if a:
        pass
    if b:
        pass
def within_limit():
    if a:
        for x in xs:
            pass
def too_deep():
    if a:
        for x in xs:
            while ready:
                pass
'''
    issues = check(ExcessiveNestingRule(max_depth=2), source)
    assert [(i.rule_id, i.severity, i.line) for i in issues] == [("SMELL002", "warning", 13)]
    assert "too_deep" in issues[0].message


def test_smell002_counts_try_with_if_and_scans_nested_functions_separately():
    source = '''def outer():
    def nested():
        if a:
            if b:
                if c:
                    pass
    try:
        with open("x"):
            if a:
                pass
    except OSError:
        pass
'''
    issues = check(ExcessiveNestingRule(max_depth=2), source)
    assert [(i.line, "Function 'nested'" in i.message) for i in issues] == [(5, True), (9, False)]


def test_smell003_complexity_threshold_counts_boolean_paths_and_reports_function_line():
    source = '''def simple(x):
    return x
def at_limit(x):
    if x and x > 1:
        return 1
    return 0
def complex(x):
    if x:
        pass
    if x > 1:
        pass
    if x > 2:
        pass
'''
    issues = check(HighCyclomaticComplexityRule(threshold=3), source)
    assert [(i.rule_id, i.severity, i.line) for i in issues] == [("SMELL003", "warning", 7)]
    assert "complexity 4" in issues[0].message


def test_smell003_handles_async_and_nested_functions_independently():
    source = '''async def outer(items):
    async for item in items:
        if item:
            pass
    def inner(x):
        if x:
            pass
        if x > 1:
            pass
        return 1 if x else 0
'''
    issues = check(HighCyclomaticComplexityRule(threshold=3), source)
    assert [(i.line, "inner" in i.message) for i in issues] == [(5, True)]


def test_smell003_counts_except_handlers():
    source = '''def parse(value):
    try:
        return int(value)
    except ValueError:
        return 0
    except TypeError:
        return 0
    except OverflowError:
        return 0
'''
    issues = check(HighCyclomaticComplexityRule(threshold=3), source)
    assert [(i.rule_id, i.line) for i in issues] == [("SMELL003", 1)]


def test_sec002_handles_secret_names_formats_and_never_prints_secret_values():
    aws_key = "AKIA" + "1234567890ABCDEF"
    source = '''api_key = "ordinary-long-key-value"
client_secret = "very-secret-value"
private_key = "private-value"
accessToken = "token-value"
aws = "{}"
'''.format(aws_key)
    issues = check(HardcodedSecretRule(), source)
    assert [(i.rule_id, i.severity, i.line) for i in issues] == [
        ("SEC002", "critical", 1), ("SEC002", "critical", 2),
        ("SEC002", "critical", 3), ("SEC002", "critical", 4), ("SEC002", "critical", 5),
    ]
    assert all("ordinary-long-key-value" not in i.message for i in issues)


def test_sec002_ignores_empty_placeholders_documentation_and_normal_values():
    source = '''API_KEY = "YOUR_API_KEY"
password = "password"
client_secret = ""
timeout = "60"
description = "password is required"
'''
    assert check(HardcodedSecretRule(), source) == []


def test_sec002_supports_annotated_credential_assignments():
    issues = check(HardcodedSecretRule(), 'clientSecret: str = "real-secret-value"\n')
    assert [(i.rule_id, i.line) for i in issues] == [("SEC002", 1)]


def test_existing_findings_have_remediation_guidance():
    issue = check(EvalExecUsageRule(), "eval(value)\n")[0]
    assert issue.remediation == "Avoid eval() and exec(); use safe parsing such as ast.literal_eval or explicit operations."
