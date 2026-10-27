# Changelog

## 2.5.3 — 2026-10-27

- Fix search pagination so later pages no longer repeat page one. Search queries now preserve reserved characters and Unicode.
- Correct IDs, embed links, keywords, thumbnails and duration types returned by listing parsers.
- Choose a download quality from the requested codec, and handle absolute download URLs correctly.
- Accept more JSON-LD shapes and optional metadata without crashing.
- Recognize German and French profile statistics, localized video paths and missing channels that return HTTP 200.
- Close CLI sessions reliably and report unsuccessful downloads as errors.
- Use the published `eaf-base-api>=4.2.5` dependency.

