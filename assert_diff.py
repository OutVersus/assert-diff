#!/usr/bin/env python3
"""Review how Python test expectations change, without running the tests."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import asdict, dataclass, field
import fnmatch
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tokenize

__version__ = "0.1.0"
MAX_FILE_BYTES = 2 * 1024 * 1024
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}
RULES = {
    "AD001": "Test removed or renamed",
    "AD002": "Assertion count decreased",
    "AD003": "Existing assertion changed",
    "AD004": "Skip or expected-failure control added or changed",
    "AD005": "Literal parameter cases decreased",
    "AD006": "Trivially passing assertion introduced",
}


@dataclass
class Finding:
    rule: str
    file: str
    test: str
    line: int
    message: str
    before: str = ""
    after: str = ""
    side: str = "after"


@dataclass
class Test:
    name: str
    line: int
    assertions: list[tuple[str, str, int]] = field(default_factory=list)
    controls: list[tuple[str, str, int]] = field(default_factory=list)
    params: dict[str, int] = field(default_factory=dict)
    trivial: list[tuple[str, str, int]] = field(default_factory=list)


def fingerprint(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def display(node: ast.AST) -> str:
    value = ast.unparse(node)
    return value if len(value) <= 240 else value[:237] + "..."


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        return prefix + "." + node.attr if prefix else node.attr
    return ""


def body_nodes(node: ast.AST):
    """Do not attribute nested helper functions/classes to the enclosing test."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield child
        yield from body_nodes(child)


def is_trivial(node: ast.AST) -> bool:
    # Deliberately conservative: no evaluation, calls, or operator overloading.
    if isinstance(node, ast.Constant):
        return bool(node.value)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left, right = node.left, node.comparators[0]
        if isinstance(left, ast.Constant) and isinstance(right, ast.Constant):
            if isinstance(node.ops[0], ast.Eq):
                return left.value == right.value
    return False


def parse_tests(source: str, filename: str = "<source>") -> dict[str, Test]:
    tree = ast.parse(source, filename=filename)
    aliases = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = node.module + "." + item.name

    def canonical(node):
        name = dotted(node)
        first, separator, rest = name.partition(".")
        return aliases.get(first, first) + (separator + rest if separator else "")

    def control(node):
        callee = node.func if isinstance(node, ast.Call) else node
        name = canonical(callee)
        known = {"pytest.mark.skip", "pytest.mark.skipif", "pytest.mark.xfail", "pytest.skip", "pytest.xfail", "unittest.skip", "unittest.skipIf", "unittest.skipUnless", "unittest.expectedFailure", "self.skipTest"}
        return name in known

    module_controls = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
                module_controls.extend(n for n in ast.walk(node.value) if isinstance(n, (ast.Call, ast.Attribute)) and control(n))
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and control(node.value):
            module_controls.append(node.value)

    result = {}

    def visit(statements, prefix="", inherited=()):
        for node in statements:
            if isinstance(node, ast.ClassDef):
                visit(node.body, prefix + node.name + ".", (*inherited, *node.decorator_list))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                item = Test(prefix + node.name, node.lineno)
                controls = []
                for decorator in (*module_controls, *inherited, *node.decorator_list):
                    if control(decorator):
                        controls.append(decorator)
                    if isinstance(decorator, ast.Call) and canonical(decorator.func) == "pytest.mark.parametrize":
                        names = decorator.args[0] if decorator.args else next((k.value for k in decorator.keywords if k.arg == "argnames"), None)
                        values = decorator.args[1] if len(decorator.args) > 1 else next((k.value for k in decorator.keywords if k.arg == "argvalues"), None)
                        if names is not None and isinstance(values, (ast.List, ast.Tuple)):
                            item.params[fingerprint(names)] = len(values.elts)
                for child in body_nodes(node):
                    check = None
                    if isinstance(child, ast.Assert):
                        check = child.test  # Assertion-message edits do not alter expectations.
                        if is_trivial(child.test):
                            item.trivial.append((fingerprint(child.test), display(child), child.lineno))
                    elif isinstance(child, ast.Call):
                        name = canonical(child.func)
                        if (name.startswith("self.assert") or name in {"pytest.raises", "pytest.warns"}):
                            check = child
                        if control(child):
                            controls.append(child)
                    if check is not None:
                        item.assertions.append((fingerprint(check), display(child), child.lineno))
                # A control can occur both as a module Call and as its Attribute.
                seen = set()
                for mark in controls:
                    key = (mark.lineno, canonical(mark.func if isinstance(mark, ast.Call) else mark))
                    if key not in seen:
                        seen.add(key)
                        item.controls.append((fingerprint(mark), display(mark), mark.lineno))
                result[item.name] = item

    visit(tree.body)
    return result


def compare_sources(before: str, after: str, filename="test_example.py") -> list[Finding]:
    old, new = parse_tests(before, filename), parse_tests(after, filename)
    findings = []
    for name, previous in old.items():
        current = new.get(name)
        if current is None:
            findings.append(Finding("AD001", filename, name, previous.line, "Test no longer exists under this name; verify deletion, rename, or relocation.", side="before"))
            continue
        old_counts = Counter(a[0] for a in previous.assertions)
        new_counts = Counter(a[0] for a in current.assertions)
        removed, added = old_counts - new_counts, new_counts - old_counts
        if len(current.assertions) < len(previous.assertions):
            findings.append(Finding("AD002", filename, name, current.line, f"Recognized assertions decreased from {len(previous.assertions)} to {len(current.assertions)}.", "\n".join(a[1] for a in previous.assertions), "\n".join(a[1] for a in current.assertions)))
        elif removed:
            findings.append(Finding("AD003", filename, name, current.line, "An existing expectation changed or was replaced; review its intent.", "\n".join(a[1] for a in previous.assertions if a[0] in removed), "\n".join(a[1] for a in current.assertions if a[0] in added)))
        for parameter, count in previous.params.items():
            # Removing a parameterization also merits review, even if the decorator was dynamic before.
            remaining = current.params.get(parameter)
            if remaining is None or remaining < count:
                description = str(remaining) if remaining is not None else "unknown (decorator removed, renamed, or changed to a dynamic source)"
                findings.append(Finding("AD005", filename, name, current.line, f"Literal parameter cases were {count}; now {description}."))
    for name, current in new.items():
        previous = old.get(name, Test(name, current.line))
        for attribute, rule in [("controls", "AD004"), ("trivial", "AD006")]:
            prior = Counter(x[0] for x in getattr(previous, attribute))
            for signature, code, line in getattr(current, attribute):
                if prior[signature]:
                    prior[signature] -= 1
                else:
                    message = "New or changed skip/xfail control; check that the test still exercises the intended behavior." if rule == "AD004" else "This constant assertion always passes."
                    findings.append(Finding(rule, filename, name, line, message, after=code))
    return findings


def wanted(path: str, includes: list[str]) -> bool:
    parts = Path(path).parts
    if any(p in SKIP_DIRS for p in parts) or not path.endswith(".py"):
        return False
    if includes:
        return any(fnmatch.fnmatchcase(path, pattern) for pattern in includes)
    name = Path(path).name
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def decode_source(data: bytes) -> str:
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Python source exceeds the 2 MiB per-file limit")
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(encoding)


def directory_sources(root: Path, includes: list[str]) -> dict[str, str]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")
    sources = {}
    for folder, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if d not in SKIP_DIRS and not (Path(folder) / d).is_symlink())
        for name in sorted(files):
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            if wanted(relative, includes):
                if path.is_symlink():
                    raise ValueError(f"Refusing symbolic-link test source: {relative}")
                if path.stat().st_size > MAX_FILE_BYTES:
                    raise ValueError(f"Python source exceeds the 2 MiB limit: {relative}")
                sources[relative] = decode_source(path.read_bytes())
    return sources


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def git_sources(repo: Path, revision: str, includes: list[str]) -> tuple[str, dict[str, str]]:
    # Resolve user-supplied refs to object IDs before putting them in later commands.
    commit = git(repo, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode().strip()
    sources = {}
    for entry in git(repo, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if wanted(path, includes):
            if mode not in {"100644", "100755"} or kind != "blob":
                raise ValueError(f"Refusing non-regular test source: {path}")
            if int(git(repo, "cat-file", "-s", oid)) > MAX_FILE_BYTES:
                raise ValueError(f"Python source exceeds the 2 MiB limit: {path}")
            sources[path] = decode_source(git(repo, "cat-file", "blob", oid))
    return commit, sources


def report(before: dict[str, str], after: dict[str, str], baseline: str, candidate: str) -> dict:
    findings, errors = [], []
    old_count, new_count = 0, 0
    for path in sorted(before.keys() | after.keys()):
        old, new = before.get(path, ""), after.get(path, "")
        try:
            old_count += len(parse_tests(old, path))
            new_count += len(parse_tests(new, path))
            findings.extend(compare_sources(old, new, path))
        except (SyntaxError, ValueError, RecursionError) as error:
            errors.append({"file": path, "message": str(error)})
    return {"schema_version": 1, "tool_version": __version__, "baseline": baseline, "candidate": candidate, "summary": {"files_compared": len(before.keys() | after.keys()), "tests_before": old_count, "tests_after": new_count, "findings": len(findings), "errors": len(errors)}, "findings": [asdict(f) for f in findings], "errors": errors}


def safe(value: str) -> str:
    # Human-readable output must not emit terminal escape sequences from source.
    return "".join(c if c == "\n" or (ord(c) >= 32 and ord(c) != 127) else repr(c)[1:-1] for c in value)


def markdown(value: str) -> str:
    import html
    return html.escape(safe(value)).replace("|", "&#124;").replace("`", "&#96;").replace("\n", "<br>")


def annotation(value: str, prop=False) -> str:
    value = safe(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return value.replace(",", "%2C").replace(":", "%3A") if prop else value


def render(data: dict, format: str) -> str:
    if format == "json":
        return json.dumps(data, indent=2, ensure_ascii=True)
    s = data["summary"]
    summary = f"{s['files_compared']} files compared; {s['tests_before']} -> {s['tests_after']} tests; {s['findings']} review findings; {s['errors']} parse errors."
    lines = ["# Assert Diff", "", summary, "", "These are review signals, not proof of a regression or misconduct.", ""] if format == "markdown" else [summary]
    for f in data["findings"]:
        location = f"{f['file']}:{f['line']} ({f['side']})"
        message = f"{f['rule']} {f['test']}: {f['message']}"
        if format == "markdown":
            lines.extend([f"## {f['rule']}: {markdown(f['test'])}", "", f"**Location:** {markdown(location)}", "", markdown(f['message']), ""])
        elif format == "github":
            # Deleted/renamed tests have old-side lines; avoid misleading head annotations.
            props = f"file={annotation(f['file'], True)},line={f['line']}" if f["side"] == "after" else "title=Removed test"
            lines.append(f"::warning {props}::{annotation(message + ' [' + location + ']')}")
        else:
            lines.append(safe(f"{location}: {message}"))
        if format in {"text", "markdown"}:
            for side in ("before", "after"):
                if f[side]:
                    if format == "markdown":
                        lines.extend(["", f"**{side.title()} ({markdown(f['test'])}, {f['rule']}):** <code>{markdown(f[side])}</code>", ""])
                    else:
                        lines.append(safe(f"  {side}: {f[side]}"))
    for error in data["errors"]:
        if format == "github":
            lines.append(f"::error file={annotation(error['file'], True)}::{annotation(error['message'])}")
        elif format == "markdown":
            lines.append(f"Parse error in {markdown(error['file'])}: {markdown(error['message'])}")
        else:
            lines.append(safe(f"ERROR {error['file']}: {error['message']}"))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser("compare", help="Compare two directories of Python tests")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    revision = sub.add_parser("git", help="Read committed tests from two Git revisions")
    revision.add_argument("--repo", type=Path, default=Path("."))
    revision.add_argument("--base", required=True)
    revision.add_argument("--head", default="HEAD")
    for command in (compare, revision):
        command.add_argument("--format", choices=["text", "json", "markdown", "github"], default="text")
        command.add_argument("--include", action="append", default=[], metavar="GLOB", help="Override default test filename discovery; matches root-relative paths")
        command.add_argument("--fail-on", choices=["none", "findings"], default="none", help="Default is advisory; parse/input errors always return 2")
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            before, after = directory_sources(args.before, args.include), directory_sources(args.after, args.include)
            base, head = "before", "after"
        else:
            base, before = git_sources(args.repo, args.base, args.include)
            head, after = git_sources(args.repo, args.head, args.include)
        data = report(before, after, base, head)
        print(render(data, args.format))
        if data["errors"]:
            return 2
        return 1 if data["findings"] and args.fail_on == "findings" else 0
    except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError) as error:
        if args.format == "json":
            print(json.dumps({"schema_version": 1, "error": str(error)}))
        else:
            print(safe(f"assert-diff: {error}"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
