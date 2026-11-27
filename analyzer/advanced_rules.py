"""Additional AST-based security and maintainability rules.

These rules are deliberately heuristic. They report suspicious syntax and
include context rather than claiming to prove exploitability.
"""

import ast
import re

from analyzer.base import Issue, Rule


def _import_aliases(tree: ast.AST, module: str) -> dict[str, str]:
    """Map local names to original imported names for one import module."""
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == module or item.name.startswith(module + "."):
                    bound = item.asname or item.name.split(".")[0]
                    aliases[bound] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module == module:
            for item in node.names:
                if item.name != "*":
                    aliases[item.asname or item.name] = f"{module}.{item.name}"
    return aliases


def _call_path(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_path(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _keyword_bool(call: ast.Call, name: str) -> bool | None:
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            if isinstance(keyword.value.value, bool):
                return keyword.value.value
    return None


def _is_dynamic_command(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(part, ast.FormattedValue) for part in node.values)
    if isinstance(node, ast.BinOp):
        return isinstance(node.op, (ast.Add, ast.Mod)) and any(
            isinstance(part, (ast.Name, ast.Call, ast.JoinedStr, ast.BinOp))
            for part in (node.left, node.right)
        )
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "format":
            return True
        if isinstance(node.func, ast.Name) and node.func.id == "input":
            return True
    if isinstance(node, ast.Name):
        name = node.id.lower()
        return any(token in name for token in ("user", "request", "input", "command", "cmd"))
    return False


class UnsafeSubprocessRule(Rule):
    rule_id = "SEC003"
    severity = "critical"
    description = "Potentially unsafe subprocess command construction"
    PROCESS_FUNCTIONS = {"run", "Popen", "call", "check_call", "check_output"}

    def check(self, filepath, source, tree):
        aliases = _import_aliases(tree, "subprocess")
        imported_callables = {
            local for local, original in aliases.items()
            if original.startswith("subprocess.") and original.rsplit(".", 1)[-1] in self.PROCESS_FUNCTIONS
        }
        subprocess_modules = {local for local, original in aliases.items() if original == "subprocess"}
        issues = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_path = _call_path(node.func) or ""
            function_name = call_path.rsplit(".", 1)[-1]
            is_subprocess_call = (
                (function_name in self.PROCESS_FUNCTIONS and "." in call_path
                 and call_path.split(".", 1)[0] in subprocess_modules)
                or ("." not in call_path and call_path in imported_callables)
            )
            os_aliases = _import_aliases(tree, "os")
            original_os_path = os_aliases.get(call_path, call_path)
            if "." in call_path:
                root, suffix = call_path.split(".", 1)
                if os_aliases.get(root) == "os":
                    original_os_path = f"os.{suffix}"
            is_os_system = original_os_path == "os.system"
            if not (is_subprocess_call or is_os_system):
                continue

            shell_enabled = _keyword_bool(node, "shell") is True
            command = node.args[0] if node.args else next(
                (item.value for item in node.keywords if item.arg in {"args", "command"}), None
            )
            dynamic_command = command is not None and _is_dynamic_command(command)
            if not shell_enabled and not dynamic_command:
                continue
            if _keyword_bool(node, "shell") is False:
                continue

            if shell_enabled:
                context = "shell=True enables shell interpretation, so interpolated or untrusted command text can execute shell metacharacters."
            else:
                context = "The command appears to be built from dynamic or user-controlled data; validate it and prefer a fixed executable with an argument list."
            issues.append(Issue(
                self.rule_id, self.severity, filepath, node.lineno,
                f"Potentially unsafe process invocation: {context}",
            ))
        return issues


class WeakHashRule(Rule):
    rule_id = "SEC004"
    severity = "warning"
    description = "Use of a weak MD5 or SHA-1 hashing algorithm"

    def check(self, filepath, source, tree):
        hashlib_aliases = _import_aliases(tree, "hashlib")
        crypto_aliases = _import_aliases(tree, "Crypto.Hash")
        weak_names = {"md5", "sha1"}
        issues = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function_path = _call_path(node.func) or ""
            original_path = hashlib_aliases.get(function_path, function_path)
            if "." in function_path:
                root, suffix = function_path.split(".", 1)
                if hashlib_aliases.get(root) == "hashlib":
                    original_path = f"hashlib.{suffix}"
                elif root in crypto_aliases:
                    original_path = f"{crypto_aliases[root]}.{suffix}"
            leaf = original_path.rsplit(".", 1)[-1].lower()
            weak = False
            if leaf in weak_names:
                weak = original_path.startswith("hashlib.")
            if leaf == "new" and original_path.startswith("hashlib."):
                weak = any(isinstance(arg, ast.Constant) and str(arg.value).lower() in weak_names for arg in node.args[:1])
            if original_path.endswith(("Crypto.Hash.MD5.new", "Crypto.Hash.SHA1.new")):
                weak = True
            if weak:
                algorithm = "MD5" if leaf == "md5" or ".MD5.new" in original_path or any(
                    isinstance(arg, ast.Constant) and str(arg.value).lower() == "md5" for arg in node.args[:1]
                ) else "SHA-1"
                issues.append(Issue(
                    self.rule_id, self.severity, filepath, node.lineno,
                    f"Use of {algorithm} detected. It may be acceptable for legacy compatibility or non-security checks, but should not protect against adversarial collisions.",
                ))
        return issues


SQL_PATTERN = re.compile(r"\b(?:select|insert|update|delete|replace|merge|drop|alter|create|truncate)\b", re.IGNORECASE)


def _constant_text(node: ast.AST) -> str:
    """Collect static string fragments from an expression without evaluating it."""
    return " ".join(item.value for item in ast.walk(node) if isinstance(item, ast.Constant) and isinstance(item.value, str))


def _is_dynamic_sql(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(part, ast.FormattedValue) for part in node.values)
    if isinstance(node, ast.BinOp):
        return isinstance(node.op, (ast.Add, ast.Mod)) and any(
            not isinstance(part, ast.Constant) for part in (node.left, node.right)
        )
    if isinstance(node, ast.Call):
        return isinstance(node.func, ast.Attribute) and node.func.attr == "format"
    return False


class PotentialSQLInjectionRule(Rule):
    rule_id = "SEC005"
    severity = "critical"
    description = "Potential SQL injection from dynamically constructed SQL text"
    EXECUTION_METHODS = {"execute", "executemany"}

    def check(self, filepath, source, tree):
        issues = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in self.EXECUTION_METHODS or not node.args:
                continue
            query = node.args[0]
            if not SQL_PATTERN.search(_constant_text(query)) or not _is_dynamic_sql(query):
                continue
            issues.append(Issue(
                self.rule_id, self.severity, filepath, node.lineno,
                "Potential SQL injection: SQL text appears to combine a query with dynamic values. Static analysis cannot prove exploitability; use bound query parameters.",
            ))
        return issues


class UnusedImportRule(Rule):
    rule_id = "MAINT002"
    severity = "info"
    description = "Imported name does not appear to be used in this module"

    def check(self, filepath, source, tree):
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    if item.name == "__future__":
                        continue
                    bound_name = item.asname or item.name.split(".")[0]
                    imported.append((bound_name, item.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if node.module == "__future__":
                    continue
                for item in node.names:
                    if item.name != "*":
                        imported.append((item.asname or item.name, item.name, node.lineno))

        if not imported:
            return []
        loads = {
            node.id for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        exports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
                if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                    exports.update(item.value for item in node.value.elts if isinstance(item, ast.Constant) and isinstance(item.value, str))
        return [
            Issue(
                self.rule_id, self.severity, filepath, line,
                f"Imported name '{bound}' from '{original}' is not referenced in this module. Dynamic reflection, re-exports, and import side effects can make this finding a false positive.",
            )
            for bound, original, line in imported
            if bound not in loads and bound not in exports
        ]


CONTROL_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)


class ExcessiveNestingRule(Rule):
    rule_id = "SMELL002"
    severity = "warning"
    description = "Function control flow exceeds the configured nesting depth"

    def __init__(self, max_depth=4):
        self.max_depth = max_depth

    def check(self, filepath, source, tree):
        issues = []
        functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for function in functions:
            crossing_line = self._first_crossing(function.body, 0)
            if crossing_line is not None:
                issues.append(Issue(
                    self.rule_id, self.severity, filepath, crossing_line,
                    f"Function '{function.name}' exceeds {self.max_depth} nested control-flow blocks; excessive nesting reduces readability.",
                ))
        return sorted(issues, key=lambda issue: issue.line)

    def _first_crossing(self, statements, depth):
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            if not isinstance(statement, CONTROL_NODES):
                found = self._first_crossing(list(ast.iter_child_nodes(statement)), depth)
                if found is not None:
                    return found
                continue
            next_depth = depth + 1
            if next_depth > self.max_depth:
                return statement.lineno

            if isinstance(statement, ast.If):
                found = self._first_crossing(statement.body, next_depth)
                if found is not None:
                    return found
                if statement.orelse:
                    if (len(statement.orelse) == 1 and isinstance(statement.orelse[0], ast.If)
                            and statement.orelse[0].col_offset == statement.col_offset):
                        found = self._first_crossing(statement.orelse, depth)
                    else:
                        found = self._first_crossing(statement.orelse, next_depth)
                    if found is not None:
                        return found
            elif isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
                for block in (statement.body, statement.orelse):
                    found = self._first_crossing(block, next_depth)
                    if found is not None:
                        return found
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                found = self._first_crossing(statement.body, next_depth)
                if found is not None:
                    return found
            elif isinstance(statement, ast.Try):
                blocks = [statement.body, statement.orelse, statement.finalbody]
                blocks.extend(handler.body for handler in statement.handlers)
                for block in blocks:
                    found = self._first_crossing(block, next_depth)
                    if found is not None:
                        return found
        return None


class _ComplexityVisitor(ast.NodeVisitor):
    """Count approximate independent decision paths, excluding nested scopes."""

    def __init__(self):
        self.complexity = 1

    def visit_FunctionDef(self, node):
        return  # Nested function complexity is measured separately.

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        return

    def visit_If(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self.complexity += 1
        self.generic_visit(node)

    visit_AsyncFor = visit_For

    def visit_While(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_IfExp(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        self.complexity += max(0, len(node.values) - 1)
        self.generic_visit(node)


class HighCyclomaticComplexityRule(Rule):
    rule_id = "SMELL003"
    severity = "warning"
    description = "Function approximate cyclomatic complexity exceeds the configured threshold"

    def __init__(self, threshold=10):
        self.threshold = threshold

    def check(self, filepath, source, tree):
        issues = []
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            visitor = _ComplexityVisitor()
            for statement in function.body:
                visitor.visit(statement)
            if visitor.complexity > self.threshold:
                issues.append(Issue(
                    self.rule_id, self.severity, filepath, function.lineno,
                    f"Function '{function.name}' has approximate cyclomatic complexity {visitor.complexity} (threshold {self.threshold}).",
                ))
        return issues
