"""
rules.py

Defines the original built-in analysis rules and registers both original
and advanced rules with the engine. Shared Rule/Issue types live in
analyzer.base; additional rules live in analyzer.advanced_rules.

To add a new rule, subclass Rule, implement check(), and register an
instance in ALL_RULES below.
"""

import ast
import re
from analyzer.base import Issue, Rule


class LineTooLongRule(Rule):
    rule_id = "STYLE001"
    severity = "info"
    description = "Line exceeds the maximum recommended length (100 chars)"
    MAX_LEN = 100

    def check(self, filepath, source, tree):
        issues = []
        for i, line in enumerate(source.splitlines(), start=1):
            if len(line) > self.MAX_LEN:
                issues.append(Issue(
                    self.rule_id, self.severity, filepath, i,
                    f"Line is {len(line)} chars (limit {self.MAX_LEN})."
                ))
        return issues


class MissingDocstringRule(Rule):
    rule_id = "STYLE002"
    severity = "info"
    description = "Public function or class is missing a docstring"

    def check(self, filepath, source, tree):
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name.startswith("_"):
                    continue  # skip private/internal members
                if ast.get_docstring(node) is None:
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    issues.append(Issue(
                        self.rule_id, self.severity, filepath, node.lineno,
                        f"{kind.capitalize()} '{node.name}' has no docstring."
                    ))
        return issues


class BareExceptRule(Rule):
    rule_id = "BUG001"
    severity = "warning"
    description = "Bare 'except:' clause silently swallows all exceptions"

    def check(self, filepath, source, tree):
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                issues.append(Issue(
                    self.rule_id, self.severity, filepath, node.lineno,
                    "Bare 'except:' catches all exceptions, including "
                    "KeyboardInterrupt/SystemExit. Catch a specific exception instead."
                ))
        return issues


class MutableDefaultArgRule(Rule):
    rule_id = "BUG002"
    severity = "warning"
    description = "Mutable default argument (list/dict/set) — classic Python pitfall"

    def check(self, filepath, source, tree):
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        issues.append(Issue(
                            self.rule_id, self.severity, filepath, node.lineno,
                            f"Function '{node.name}' uses a mutable default "
                            "argument; it is shared across all calls. Use "
                            "None and initialize inside the function body."
                        ))
        return issues


class EvalExecUsageRule(Rule):
    rule_id = "SEC001"
    severity = "critical"
    description = "Use of eval()/exec() can lead to arbitrary code execution"

    def check(self, filepath, source, tree):
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ("eval", "exec"):
                    issues.append(Issue(
                        self.rule_id, self.severity, filepath, node.lineno,
                        f"Call to '{node.func.id}()' detected. Avoid evaluating "
                        "dynamic strings as code; consider ast.literal_eval or "
                        "a safer alternative."
                    ))
        return issues


class HardcodedSecretRule(Rule):
    rule_id = "SEC002"
    severity = "critical"
    description = "Possible hardcoded password/API key/secret assignment"
    SUSPECT_NAMES = {
        "password", "passwd", "secret", "apikey", "accesstoken", "authtoken",
        "clientsecret", "token", "privatekey", "credential", "credentials",
    }
    PLACEHOLDERS = {
        "password", "passwd", "secret", "token", "apikey", "yourapikey",
        "yourpassword", "yourtoken", "changeme", "changeit", "placeholder",
        "example", "dummy", "test", "todo", "none", "null",
    }
    SECRET_FORMATS = (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
        re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{12,}\b"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    )

    @classmethod
    def _looks_sensitive_name(cls, name):
        expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
        tokens = re.findall(r"[a-z0-9]+", expanded.lower())
        compact = "".join(tokens)
        if any(token in cls.SUSPECT_NAMES for token in tokens):
            return True
        return any(pattern in compact for pattern in ("apikey", "clientsecret", "privatekey")) or (
            "api" in tokens and "key" in tokens
        ) or ("private" in tokens and "key" in tokens)

    @classmethod
    def _is_placeholder(cls, value):
        normalized = re.sub(r"[^a-z0-9]", "", value.strip().lower())
        if not normalized or normalized in cls.PLACEHOLDERS:
            return True
        return (
            normalized.startswith(("your", "replace", "insert", "example", "placeholder"))
            or value.strip().startswith(("<", "${"))
            or value.strip().endswith((">", "}"))
        )

    @classmethod
    def _secret_literal(cls, value):
        if not isinstance(value, str) or cls._is_placeholder(value):
            return False
        return True

    def check(self, filepath, source, tree):
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign):
                targets, value = [node.target], node.value
            else:
                continue

            literal = value.value if isinstance(value, ast.Constant) else None
            secret_format = isinstance(literal, str) and any(
                pattern.search(literal) for pattern in self.SECRET_FORMATS
            )
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                sensitive_name = self._looks_sensitive_name(target.id)
                if secret_format or (sensitive_name and self._secret_literal(literal)):
                    issues.append(Issue(
                        self.rule_id, self.severity, filepath, node.lineno,
                        f"Variable '{target.id}' appears to contain a hardcoded credential. "
                        "The value is intentionally omitted from this finding."
                    ))
        return issues


class TooManyArgumentsRule(Rule):
    rule_id = "SMELL001"
    severity = "info"
    description = "Function has too many parameters (readability/design smell)"
    MAX_ARGS = 5

    def check(self, filepath, source, tree):
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                total_args = len(node.args.args)
                if total_args > self.MAX_ARGS:
                    issues.append(Issue(
                        self.rule_id, self.severity, filepath, node.lineno,
                        f"Function '{node.name}' has {total_args} parameters "
                        f"(limit {self.MAX_ARGS}). Consider grouping related "
                        "parameters into an object or config dict."
                    ))
        return issues


class TodoCommentRule(Rule):
    rule_id = "MAINT001"
    severity = "info"
    description = "TODO/FIXME comment left in code"

    def check(self, filepath, source, tree):
        issues = []
        for i, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") and ("TODO" in stripped or "FIXME" in stripped):
                issues.append(Issue(
                    self.rule_id, self.severity, filepath, i,
                    f"Unresolved marker left in code: {stripped}"
                ))
        return issues


# New rules are kept in a separate module so each analysis area remains independently testable.
from analyzer.advanced_rules import (  # noqa: E402
    ExcessiveNestingRule,
    HighCyclomaticComplexityRule,
    PotentialSQLInjectionRule,
    UnusedImportRule,
    UnsafeSubprocessRule,
    WeakHashRule,
)


# Register every rule the engine should run here.
ALL_RULES = [
    LineTooLongRule(),
    MissingDocstringRule(),
    BareExceptRule(),
    MutableDefaultArgRule(),
    EvalExecUsageRule(),
    HardcodedSecretRule(),
    TooManyArgumentsRule(),
    TodoCommentRule(),
    UnsafeSubprocessRule(),
    WeakHashRule(),
    PotentialSQLInjectionRule(),
    UnusedImportRule(),
    ExcessiveNestingRule(),
    HighCyclomaticComplexityRule(),
]
