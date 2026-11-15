# 3.0.0

Release 3.0.0

Update pagination handling, validation, and documentation.

Changes since v2.5.4:

```text
README.md                     |  16 +++++-
 eporner_api/api.py            | 128 ++++++++++++++++++++++++++++--------------
 eporner_api/modules/consts.py |   5 +-
 pyproject.toml                |   4 +-
 4 files changed, 106 insertions(+), 47 deletions(-)
```

# Changelog

## 2.5.4 - 2026-11-14

- Retain scene actor names and URLs together for metadata export without extra profile requests.

## 2.5.3 — 2026-10-27

- Fix search pagination so later pages no longer repeat page one. Search queries now preserve reserved characters and Unicode.
- Correct IDs, embed links, keywords, thumbnails and duration types returned by listing parsers.
- Choose a download quality from the requested codec, and handle absolute download URLs correctly.
- Accept more JSON-LD shapes and optional metadata without crashing.
- Recognize German and French profile statistics, localized video paths and missing channels that return HTTP 200.
- Close CLI sessions reliably and report unsuccessful downloads as errors.
- Use the published `eaf-base-api>=4.2.5` dependency.

