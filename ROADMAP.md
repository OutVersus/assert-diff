# Roadmap

This is a small first release. The goal is useful maintenance work, not a large feature list.

## First: measure usefulness

- Collect consenting maintainers' examples of noisy and useful findings.
- Build a public before/after corpus with expected findings and explanations.
- Evaluate it on real Python pull requests with human review labels; publish methodology and raw counts.
- Improve suppression and baseline handling only after observing concrete false positives.

## Next: reduce review friction

- Match moved/renamed tests when there is strong structural evidence.
- Flag assertions moved behind new conditional exits.
- Compare literal parameter identities, not just counts.
- Add a stable machine-readable rule reference and SARIF output.
- Document integrations with coding agents that ask for review before changing existing expectations.

## Later, if maintainers ask for it

- JavaScript/TypeScript test support using an appropriate parser.
- PyPI distribution after packaging, name ownership, and release processes are settled.
- Optional human-reviewed justification records for intentional test changes.

No adoption, roadmap delivery date, benchmark accuracy, or funding-program eligibility is promised. The project earns those claims through use and evidence.
