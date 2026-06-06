"""
Advanced code security analysis for strategy execution.
Uses AST parsing to detect dangerous patterns that regex cannot catch.
"""

import ast
import re
import logging
from typing import List, Set, Optional

logger = logging.getLogger(__name__)

# Forbidden imports (module names)
FORBIDDEN_MODULES = {
    'os', 'sys', 'subprocess', 'requests', 'urllib', 'urllib2', 'http',
    'ftplib', 'smtplib', 'socket', 'socketserver', 'threading', 'multiprocessing',
    'concurrent.futures', 'pickle', 'shelve', 'dbm', 'sqlite3', 'anydbm',
    'redis', 'pymongo', 'elasticsearch', 'boto3', 'botocore',
    'ctypes', 'mmap', 'fcntl', 'msvcrt', 'winreg', 'asyncio.subprocess',
}

# Dangerous builtins and functions
DANGEROUS_BUILTINS = {'eval', 'exec', 'compile', '__import__', 'open', 'input',
                      'getattr', 'setattr', 'delattr', 'globals', 'locals', 'vars', 'dir'}

# Dangerous dunder methods / attributes
DANGEROUS_DUNDERS = re.compile(r'__(\w+)__')
FORBIDDEN_DUNDERS = {'subclasses__', 'bases__', 'class__', 'mro__'}


class SecurityAnalyzer(ast.NodeVisitor):
    """AST visitor that detects dangerous code patterns."""

    def __init__(self):
        self.violations: List[str] = []
        self.imported_modules: Set[str] = set()
        self.defined_names: Set[str] = set()

    def _check_module_name(self, name: str) -> bool:
        """Check if a module or its parent is forbidden."""
        parts = name.split('.')
        for i in range(len(parts)):
            partial = '.'.join(parts[:i+1])
            if partial in FORBIDDEN_MODULES:
                return True
        return False

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imported_modules.add(alias.name)
            if self._check_module_name(alias.name):
                self.violations.append(f"Forbidden import: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ''
        self.imported_modules.add(module)
        if self._check_module_name(module):
            self.violations.append(f"Forbidden import from: {module}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Detect eval(), exec(), compile(), __import__(), open(), etc.
        if isinstance(node.func, ast.Name):
            if node.func.id in DANGEROUS_BUILTINS:
                self.violations.append(f"Forbidden builtin call: {node.func.id}()")
            if node.func.id == '__import__':
                self.violations.append("Forbidden __import__ call")
        # Detect getattr(obj, '__subclasses__') etc.
        if isinstance(node.func, ast.Name) and node.func.id == 'getattr':
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                attr = node.args[1].value
                if attr.startswith('__') and attr.endswith('__'):
                    self.violations.append(f"Forbidden getattr with dunder: {attr}")
        # Detect .__subclasses__() etc.
        if isinstance(node.func, ast.Attribute):
            if node.func.attr.startswith('__') and node.func.attr.endswith('__'):
                if node.func.attr in FORBIDDEN_DUNDERS or DANGEROUS_DUNDERS.match(node.func.attr):
                    self.violations.append(f"Forbidden dunder access: {node.func.attr}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # Detect obj.__class__, obj.__bases__, etc.
        if node.attr.startswith('__') and node.attr.endswith('__'):
            if node.attr in FORBIDDEN_DUNDERS or DANGEROUS_DUNDERS.match(node.attr):
                self.violations.append(f"Forbidden dunder attribute access: {node.attr}")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        # Detect direct reference to dangerous builtins
        if node.id in DANGEROUS_BUILTINS:
            # Only flag if it's being used (not just defined)
            # This is tricky; we rely on Call detection mostly
            pass
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr):
        # Detect string-based dynamic execution attempts
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            text = node.value.value
            # Detect string literals that look like hidden import attempts
            if any(kw in text.lower() for kw in ['__import__', 'eval(', 'exec(', 'compile(', 'open(']):
                if len(text) < 500:  # Only short strings
                    self.violations.append(f"Suspicious string literal containing dangerous code")
        self.generic_visit(node)


def analyze_code(code: str) -> List[str]:
    """
    Analyze Python code for security violations using AST parsing.
    
    Returns a list of violation descriptions. Empty list means code is clean.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"Syntax error in code: {e}"]
    except Exception as e:
        return [f"Failed to parse code: {e}"]

    analyzer = SecurityAnalyzer()
    analyzer.visit(tree)
    return analyzer.violations


def is_code_safe(code: str) -> tuple[bool, Optional[str]]:
    """
    Quick check if code passes all security validations.
    
    Returns (is_safe, error_message).
    """
    violations = analyze_code(code)
    if violations:
        return False, "; ".join(violations[:5])  # Limit to first 5
    return True, None


# Regex-based dangerous patterns (additional layer)
REGEX_DANGEROUS_PATTERNS = [
    r'\bimport\s+(os|sys|subprocess|requests|urllib|socket|threading|multiprocessing|pickle|shelve|dbm|sqlite3|redis|pymongo|elasticsearch|boto3|botocore|ctypes|mmap)\b',
    r'\bfrom\s+(os|sys|subprocess|requests|urllib|socket|threading|multiprocessing|pickle|shelve|dbm|sqlite3|redis|pymongo|elasticsearch|boto3|botocore|ctypes|mmap)\b',
    r'\beval\s*\(',
    r'\bexec\s*\(',
    r'\bcompile\s*\(',
    r'\b__import__\s*\(',
    r'\bopen\s*\(',
    r'\bglobals\s*\(',
    r'\blocals\s*\(',
    r'\bvars\s*\(',
    r'\bdir\s*\(',
    r'\bgetattr\s*\(.*__\w+__',
    r'\.\s*__subclasses__\s*\(',
    r'\.\s*__bases__\s*',
    r'\.\s*__class__\s*',
    r'\.\s*__mro__\s*',
]


def regex_scan_code(code: str) -> List[str]:
    """Secondary regex-based scan for dangerous patterns."""
    violations = []
    for pattern in REGEX_DANGEROUS_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            violations.append(f"Regex match: {pattern}")
    return violations
