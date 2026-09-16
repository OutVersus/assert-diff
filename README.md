# Assert Diff

**The tests passed. What changed in the tests?**

Assert Diff highlights changes to Python test expectations in human- and AI-assisted pull requests. It compares the syntax trees of two versions and gives reviewers a short list of changes worth inspecting: deleted tests, removed assertions, changed expectations, new skips, smaller parameter sets, and trivially passing checks.

**No API keys. No model calls. No runtime dependencies. No test execution.** Python 3.10+; Git is needed only for Git revision comparison.

[![Tests](https://github.com/OutVersus/assert-diff/actions/workflows/tests.yml/badge.svg)](https://github.com/OutVersus/assert-diff/actions/workflows/tests.yml)

Early release, focused on Python `pytest` and `unittest` syntax. Findings are review signals, **not proof that a change is wrong, malicious, or AI-generated**. A quiet report does not certify correctness.

## Try it in a minute

```sh
git clone https://github.com/OutVersus/assert-diff.git
cd assert-diff
python assert_diff.py compare examples/before examples/after
```

On Windows, use `py -3` if `python` is not on your PATH. No installation is needed for this demo. The example files are synthetic source snippets, not executable tests.

The example flags six findings across four original tests:

```text
1 files compared; 4 -> 3 tests; 6 review findings; 0 parse errors.
AD002 test_guest_cannot_checkout: Recognized assertions decreased from 2 to 1.
AD005 test_invalid_quantities: Literal parameter cases were 3; now 1.
AD001 test_duplicate_payment_is_rejected: Test no longer exists under this name...
AD003 test_tax_total: An existing expectation changed or was replaced...
AD004 test_tax_total: New or changed skip/xfail control...
AD006 test_tax_total: This constant assertion always passes.
```

See the [before](examples/before/test_checkout.py) and [after](examples/after/test_checkout.py) files. Actual output also includes line numbers and before/after expressions.

## Review a real change

Run from your project using the path to your copy of Assert Diff:

```sh
python /path/to/assert-diff/assert_diff.py git --base main --head HEAD
```

This compares the two **committed snapshots**, not uncommitted working-tree edits. For a branch review, pass the merge-base commit as `--base` if that is the comparison you want. Neither refs nor the working tree are changed. Revision names are resolved to commit IDs, which are included in JSON output.

Or compare two directories, including uncommitted content:

```sh
python assert_diff.py compare before/ after/ --format markdown
python assert_diff.py compare before/ after/ --format json > review.json
python assert_diff.py git --repo /path/to/project --base HEAD~1 --head HEAD --format github
```

To install a console command from this checkout:

```sh
python -m pip install .
assert-diff --version
```

The package is not published to PyPI in this release. Install from this repository or use the single Python file.

## What it finds

| Rule | Signal | Why review it? |
| --- | --- | --- |
| AD001 | A named test disappears | It may have been deleted, renamed, or moved. Confirm its protection still exists. |
| AD002 | Fewer recognized assertions | Behavior may no longer be checked. The report shows old and new checks. |
| AD003 | An existing assertion changes | A new expected value may be legitimate, or may simply accept a regression. |
| AD004 | New or changed skip/xfail control | Check whether the test will still run and whether failures remain visible. |
| AD005 | Fewer literal parameter cases | Edge cases may have disappeared. Moving to dynamic data is also flagged for review. |
| AD006 | A trivially passing assertion appears | `assert True` and literal equalities such as `assert 1 == 1` test no behavior. |

Formatting, comments, assertion messages, reordering assertions, and adding assertions without replacing existing ones are quiet. Existing unchanged skips and tautologies are quiet: this is a change-review tool, not a general test linter.

## Default behavior

- Discovers `test_*.py`, `*_test.py`, and `conftest.py` recursively.
- Recognizes `test*` functions and methods, including async tests.
- Checks Python `assert`, `self.assert*`, `pytest.raises`, and `pytest.warns` syntax.
- Handles common top-level import aliases, plus function, class, and module skip markers.
- Ignores virtual environments, Git internals, `node_modules`, and build directories.
- Reads Python encoding declarations; limits each source file to 2 MiB.
- Does not import your source, run tests, install dependencies, or contact a server.

Override file discovery for a custom layout:

```sh
python assert_diff.py compare before after --include 'specs/*.py' --include 'checks/*.py'
```

Patterns use case-sensitive shell-style matching against root-relative forward-slash paths. `*` can match `/`; these are not Git pathspecs. Directory mode does not interpret `.gitignore`, so use focused directories or explicit include patterns. Symlinked directories are skipped and symlinked test files are rejected; Git submodules are not traversed.

Exit codes: **0** completed (advisory findings allowed), **1** findings with `--fail-on findings`, **2** input or parse error. Start in advisory mode and measure noise before making this a required check.

## GitHub Actions

The repository includes a [composite action](action.yml) that produces workflow annotations. Pin it to a reviewed full commit SHA in production. It needs Python 3.10+ and both Git revisions present locally.

```yaml
name: Review test changes
on: [pull_request]
permissions:
  contents: read
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6
        with:
          python-version: '3.13'
      - uses: OutVersus/assert-diff@main # Replace main with a reviewed commit SHA.
        with:
          base: ${{ github.event.pull_request.base.sha }}
          head: ${{ github.event.pull_request.head.sha }}
```

The action reads Git objects and emits annotations. It does not post comments or need a write token. It compares the exact supplied snapshots; use a separately computed merge-base if your review policy calls for that. Do not switch this example to `pull_request_target` and execute untrusted PR code.

## Why this project exists

AI coding tools can modify application code and its tests in the same change. Passing CI is useful evidence, but it does not explain whether the test expectations themselves were weakened. Assert Diff makes those edits easier to notice without sending your code to another model.

This problem also exists in human-written changes. The tool deliberately makes no inference about authorship or intent. GitHub's [guidance on reviewing AI-generated code](https://docs.github.com/en/copilot/tutorials/review-ai-generated-code) includes reviewing the reasoning behind deleted failing tests.

Other tools already address adjacent problems: [ProofRun](https://github.com/yebiguo/ProofRun) binds command results to Git state, while [SWT-Bench](https://github.com/logic-star-ai/SWT-Bench) evaluates generated regression tests. Assert Diff's narrow contribution is an offline, inspectable diff of existing Python test checks. It complements test execution, coverage, mutation testing, and human review.

## Limits and next steps

This is static syntax comparison, not semantic verification. Refactors can produce findings. Moved or renamed tests appear as removals. Helper assertions, fixture behavior, mocks, indirect aliases, dynamic parameter generators, test-runner configuration, and other languages are outside the first release. It does not establish whether a new expected value is correct or whether coverage improved. See [limitations](docs/limitations.md) before relying on it.

The initial evaluation is a [synthetic unit/integration suite](tests/test_assert_diff.py), not a field accuracy benchmark. There is no claimed adoption or measured reduction in maintainer workload yet. The [roadmap](ROADMAP.md) starts with public case studies and false-positive reports.

## Contribute

Run the standard-library test suite:

```sh
python -m unittest discover -s tests -v
```

Useful contributions include minimal before/after examples, false-positive reports, and tests for syntax used by real projects. See [CONTRIBUTING.md](CONTRIBUTING.md). AI-assisted contributions are welcome when a human can explain the change and reproduce its verification.

MIT licensed. Maintained under the [OutVersus GitHub account](https://github.com/OutVersus).
