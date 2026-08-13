#!/usr/bin/env python3
"""Detect __init__.py files that import from modules no longer on disk.

Usage:
    python scripts/audit_stale_imports.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path("app")


def check_file(path: Path) -> list[str]:
    issues = []
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError as e:
        issues.append(f"SYNTAX ERROR: {path}: {e}")
        return issues

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module
            if module and module.startswith("app."):
                parts = module.split(".")
                rel = Path(*parts[1:])
                pkg_init = ROOT / rel / "__init__.py"
                pkg_dir = ROOT / rel
                mod_file = ROOT / f"{rel}.py"
                # Check if the target exists as a file or package
                if not pkg_init.exists() and not mod_file.exists() and not pkg_dir.is_dir():
                    issues.append(
                        f"STALE IMPORT: {path}:{node.lineno} imports from "
                        f"'{module}' — module does not exist"
                    )
    return issues


def main():
    all_issues = []
    for f in sorted(ROOT.rglob("*.py")):
        if f.name == "__init__.py":
            issues = check_file(f)
            all_issues.extend(issues)

    if all_issues:
        print(f"Found {len(all_issues)} stale import(s):\n")
        for issue in all_issues:
            print(f"  {issue}")
        sys.exit(1)
    else:
        print("OK: No stale imports found")


if __name__ == "__main__":
    main()
