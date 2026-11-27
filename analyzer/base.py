"""Shared rule and finding types used by built-in and extension rules."""

from dataclasses import dataclass


REMEDIATION_BY_RULE = {
    "STYLE001": "Break long statements into readable expressions or wrap them in parentheses.",
    "STYLE002": "Add a concise docstring describing the public function or class.",
    "BUG001": "Catch specific exceptions so unrelated failures are not silently swallowed.",
    "BUG002": "Use None as the default and initialize the mutable value inside the function.",
    "SEC001": "Avoid eval() and exec(); use safe parsing such as ast.literal_eval or explicit operations.",
    "SEC002": "Load credentials from environment variables or a secrets manager, and rotate exposed credentials.",
    "SMELL001": "Group related parameters into a data structure or simplify the function interface.",
    "MAINT001": "Resolve the TODO/FIXME or remove it if the work is no longer needed.",
    "SEC003": "Avoid shell=True. Pass an argument list to subprocess with shell=False and validate untrusted values.",
    "SEC004": "Use SHA-256/SHA-3 for general integrity checks; use a dedicated password-hashing algorithm for passwords.",
    "SEC005": "Use parameterized SQL queries instead of interpolating values into SQL text.",
    "MAINT002": "Remove the unused import, or reference it explicitly if it is a deliberate re-export or side-effect import.",
    "SMELL002": "Reduce nested control flow with guard clauses or extracted helper functions.",
    "SMELL003": "Split the function into smaller, focused functions with simpler decision paths.",
}


@dataclass
class Issue:
    """A single static-analysis finding."""

    rule_id: str
    severity: str
    file: str
    line: int
    message: str
    remediation: str | None = None

    def __post_init__(self):
        if self.remediation is None:
            self.remediation = REMEDIATION_BY_RULE.get(self.rule_id)


class Rule:
    """Base class every analyzer rule implements."""

    rule_id = "BASE000"
    severity = "info"
    description = "Base rule (do not use directly)"

    def check(self, filepath: str, source: str, tree):
        raise NotImplementedError
