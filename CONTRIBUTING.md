# Contributing to GWyl Mail

Thank you for your interest in contributing! This project is licensed under GPL‑3.0‑only. By contributing, you agree that your contributions will be licensed under the same terms.

Guidelines (quick)
- Use clear, focused pull requests and commit messages.
- Include tests for new behavior when possible; keep coverage steady.
- Follow the existing code style and structure.
- Avoid adding new runtime dependencies unless strictly necessary.

Developer Certificate of Origin (DCO)
- We use a lightweight DCO process. Please sign your commits with:
  - `git commit -s -m "Your message"`
  - This adds a Signed-off-by trailer asserting you have the right to contribute under GPL‑3.0‑only.

License
- SPDX identifier: `GPL-3.0-only`
- Source files should include a single-line SPDX header at the top where practical.
- See `LICENSE` at the repository root for the full license text.

Issues & Security
- For bugs or feature requests, open an issue with clear steps/repro.
- For security-sensitive reports, please avoid public disclosure; contact the maintainers privately if possible.

CI & Integrity
- The repository uses integrity hooks and a baseline snapshot.
- If the pre-commit hook blocks your change for integrity reasons, run the integrity helper targets in the Makefile (e.g., `make integrity-commit MSG="..."`).

Thank you for helping improve GWyl Mail!
