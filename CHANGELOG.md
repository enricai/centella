# Changelog

All notable changes to Centella will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Per-worker model selection. Default `sonnet`; override with `--model`
  (sets all five workers) or `--model-<worker>` (per-worker; values:
  `sonnet` / `opus` / `haiku`). Env equivalents `CENTELLA_MODEL` and
  `CENTELLA_MODEL_<WORKER>`; TOML keys `model` and `model_<worker>` in
  `centella.toml`. Resolution order, highest first: per-worker CLI →
  global CLI → per-worker env → global env → per-worker TOML → global
  TOML → default. Invalid values rejected at startup. Models are
  re-resolved on `--resume` (not persisted in state).
- `--source-of-truth` CLI flag for one-off overrides of the
  `CENTELLA_SOURCE_OF_TRUTH` env var and `centella.toml`.

### Changed

- Source-of-truth resolution precedence flipped: env var now beats
  `centella.toml` (and the new `--source-of-truth` flag beats both).
  CLI/env are session-scoped knobs; `centella.toml` is the committed
  repo default.

### Deprecated

### Removed

### Fixed

### Security

## [0.2.0] - 2026-05-24

### Added

- Initial public release. Deterministic Python orchestrator for Claude Code;
  six-phase classify → clarify → plan → schedule → execute → finalize
  pipeline; per-wave parallel implementers in isolated git worktrees;
  evidence-gated implement/validate loop; JSON-schema-validated worker
  outputs; resumable state; pytest suite covering deterministic
  enforcement functions.

[Unreleased]: https://github.com/enricai/centella/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/enricai/centella/releases/tag/v0.2.0
