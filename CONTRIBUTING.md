# Contributing to BirdFrame

Thanks for helping improve BirdFrame. The project is intentionally hobby-sized:
small, reviewable changes and clear documentation are preferred over large
framework additions.

## Before opening a pull request

* Do not commit provider tokens, TV pairing data, model files, generated art,
  local databases, or files from `data/`.
* Check the license and attribution manifest for every artwork pack. Packs are
  optional user-provided content and are not covered by the BirdFrame license.
* Run the backend tests, frontend build, and `git diff --check`.
* Include a short note describing how the change was tested. UI changes should
  include a screenshot when practical.

## Development setup

See [docs/development.md](docs/development.md). Keep external services behind
adapters so tests can use fixtures and fake TV endpoints.

## Pull requests

Please explain the user-facing behavior, configuration or migration impact,
and any security/privacy implications. Keep unrelated formatting changes out of
the same pull request.
