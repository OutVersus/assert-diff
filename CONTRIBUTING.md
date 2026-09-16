# Contributing

Start with a small before/after test example and the behavior you expected. Reports about noisy findings are as valuable as requests for new rules.

## Development

Use Python 3.10 or newer and Git. There are no runtime dependencies.

```sh
python -m unittest discover -s tests -v
python assert_diff.py compare examples/before examples/after --format json
```

The files in `examples/` are static inputs with intentionally undefined application functions. Do not try to run them with pytest. Only `tests/` contains the project's executable test suite.

Before opening a pull request:

1. Add a minimal test covering the changed behavior, including a nearby case that should remain quiet.
2. Run the unit and Git integration suite.
3. Explain which rule changes and which false-positive tradeoff it introduces.
4. Update the README and limitations if the supported syntax or interpretation changes.

Keep analysis deterministic and offline. Never execute the project being inspected. New dependencies or language support need an explicit design discussion in the pull request.

## AI-assisted work

AI-assisted contributions are welcome. Review the generated diff yourself, report commands you actually ran, and distinguish tested behavior from assumptions. Do not remove or weaken checks merely to make the suite pass. If a test expectation legitimately changes, explain why.

## Community

Be respectful and specific. Discuss the code and evidence rather than a contributor's identity or the tools they use. Do not submit private source, credentials, or personal information in public issues.
