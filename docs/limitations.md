# Interpretation and limits

Assert Diff is an early static review aid. Its rules describe syntactic changes, not a verdict on intent, security, correctness, or test quality. Both human and AI-assisted changes can produce the same findings.

## Expected false positives

- Renaming or moving a test is reported as AD001. The tool does not infer equivalence across names or files.
- Combining two assertions into one can trigger AD002 even when behavior is preserved.
- Strengthening an expectation can trigger AD003. The tool cannot generally order assertion strength.
- Platform-specific skips and intentional xfails trigger AD004 when added or modified.
- Moving literal parameter cases into a shared variable triggers AD005 because the case count becomes unknown.
- Changing only a unittest assertion's message can trigger AD003 because the whole call is compared. Python `assert` messages are excluded.

These findings should prompt review, not automatic accusations or rejection. Advisory mode is the default.

## Blind spots

- Python only, with conventional test filenames and `test*` function names. Syntax must be supported by the Python interpreter running the tool.
- This does not run pytest collection. Some statically found methods may not actually be collected, and dynamically generated tests may be missed.
- Functions nested inside a test are not attributed to the outer test. Imported helpers, mocks, fixtures, conftest hooks, plugins, and runner configuration are not analyzed for behavior changes.
- Basic top-level `import` and `from ... import ...` aliases are recognized. Star imports, reassignment, shadowing, local imports, wrappers, and dynamic dispatch are not resolved.
- A conditional around an unchanged assertion may prevent it from executing without changing its AST fingerprint; this is not detected.
- Changing a parameter value without changing the number of cases is not detected. Dynamic generators and Hypothesis settings are not evaluated.
- Counts of syntax nodes are not counts of runtime assertions: a check inside a loop still counts once.
- AD006 intentionally recognizes only truthy constants and equal literal constants. It avoids guessing about overloaded operators, function calls, or object identity.
- Source under symlinked directories and Git submodules is not traversed. Directory discovery does not implement `.gitignore`.
- Directory snapshots are not atomic. Avoid concurrent edits while scanning. Git mode reads immutable commits and records their IDs.

## Trust boundary

The scanner uses Python's AST parser and Git plumbing. It does not evaluate source, import project modules, execute tests, or call models. Git is launched without a shell; refs are resolved to commit IDs before tree/blob reads. It does not use Git diff textconv or external diff commands.

This is not a sandbox or a security certification. Run a trusted copy of Assert Diff and Git. The Python process still inherits your environment; AST parsing can consume resources on adversarial input despite the per-file size limit. No claim is made that it withstands arbitrary hostile repositories.

Reports contain test names, paths, and snippets. Review them before publishing if your repository is private. The tool does not upload reports or retain a service-side copy.

For CI, use a reviewed, pinned tool revision and a read-only token. A contributor who can change the scanner or the CI workflow can change the output, just as with other repository-local checks.

## Evaluation claims

The first release is tested on deliberately constructed examples plus temporary Git repositories. Those tests demonstrate implemented behavior; they do not establish precision or recall on real pull requests. The roadmap calls for publishing independently reviewable real-world examples before making accuracy or time-saving claims.
