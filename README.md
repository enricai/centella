# Centella

Deterministic, headless task orchestrator for Claude Code. Give it one task; it
classifies it into up to eight categories, decomposes each into granular
subtasks, schedules them into dependency-ordered waves, and executes each in an
isolated git worktree under an evidence-gated implement/validate loop.

Runs entirely on the Claude Code CLI and your subscription. **No API key.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![tests](https://github.com/enricai/centella/actions/workflows/test.yml/badge.svg)](https://github.com/enricai/centella/actions/workflows/test.yml)
[![syntax](https://github.com/enricai/centella/actions/workflows/syntax.yml/badge.svg)](https://github.com/enricai/centella/actions/workflows/syntax.yml)
[![shellcheck](https://github.com/enricai/centella/actions/workflows/shellcheck.yml/badge.svg)](https://github.com/enricai/centella/actions/workflows/shellcheck.yml)
[![Version](https://img.shields.io/badge/version-0.2.0-orange.svg)](CHANGELOG.md)

## How it works

The orchestrator is a Python program — not an in-session agent. It shells out
to `claude -p` (headless mode) for each unit of LLM work. Each call is a
separate process, so there is no subagent nesting anywhere. Control flow lives
in real Python: `for` loops, `if` statements, counters. It cannot drift.

```
centella "<task>"
   ├─ Phase 1  Classify into 1..8 categories                    → 1 claude -p
   ├─ Phase 0  Clarify — intent-only questions, default zero
   ├─ Phase 2  Plan — one planner per category (parallel)        → N claude -p
   ├─ Phase 3  Schedule — global dependency graph → topo waves   (pure Python)
   ├─ Phase 4  Create centella/staging branch + worktree
   ├─ Phase 5  Per wave: implement (parallel, isolated worktrees) → claude -p each
   │           integrate into staging; validate staging
   └─ Phase 6  Merge staging → working branch; cleanup
```

For the full rationale — why the orchestrator is a script rather than a plugin
command, all architectural decisions, and the complete enforcement surface —
read [`docs/DESIGN.md`](docs/DESIGN.md).

## Why Centella

- **Runs on the Claude Code subscription, not the metered API.** Centella
  shells out to `claude -p`, the headless mode of the Claude Code CLI you
  already have. No API key, no per-call billing surprise.
- **Control flow is real Python, not a model interpreting instructions.**
  Phases, waves, retries, caps, and the source-of-truth check are written as
  ordinary code that you can read, set a breakpoint in, and reason about
  with a state machine. See [`docs/DESIGN.md`](docs/DESIGN.md) §2 for why
  the orchestrator is a subprocess script rather than an in-session agent.
- **Every worker output is JSON-schema-validated; every cap is a Python
  counter; prompts are advisory and code enforces.** The mechanical safety
  surface lives in `orchestrator/centella.py`, not in a prompt that a model
  might drift away from. See [`docs/DESIGN.md`](docs/DESIGN.md) §12.

If you want an orchestrator you can debug with `print()` and reason about
with a state machine, this is the right shape. If you want emergent agentic
behavior, this isn't it.

## Requirements

- `claude` CLI on `PATH`, logged in interactively
- Python 3.10+
- A git repository with `user.email` and `user.name` configured
- A reasonably clean working tree

## Install and run

```bash
# From the root of the target git repository:
/path/to/centella/centella "Fix the login timeout bug and add a regression test"

# Resume an interrupted or budget-capped run:
/path/to/centella/centella --resume

# Skip the clarification phase entirely:
/path/to/centella/centella "task" --no-clarify

# Pre-supply clarification answers (JSON object):
# Keys are question ids from the classifier, plus "source_of_truth"
# set to "codebase", "research", or "both".
/path/to/centella/centella "task" --answers answers.json

# Override caps:
/path/to/centella/centella "task" --max-workers 60 --max-parallel 6

# Dial how persistent the planner and implementer are at building
# confidence before they exit blocked (default 8 evidence-gate rounds
# inside each worker; see DESIGN §8):
/path/to/centella/centella "task" --confidence-rounds 12
export CENTELLA_CONFIDENCE_ROUNDS=12

# Set the source-of-truth preference globally so centella does not ask,
# or pass --source-of-truth on the command line for a one-off override.
# Alternatively, commit a centella.toml at the repo root with the line
# `source_of_truth = codebase` (or research / both / ask).
# Precedence (highest first): --source-of-truth > env > centella.toml.
export CENTELLA_SOURCE_OF_TRUTH=codebase    # or: research, both, ask
/path/to/centella/centella "task" --source-of-truth codebase

# Choose the model for all workers (default: sonnet). Each worker can
# also be overridden independently — see docs/IMPLEMENTATION.md §2
# "Model selection" for the full env-var / CLI-flag / TOML-key table.
export CENTELLA_MODEL=sonnet                # or: opus, haiku
/path/to/centella/centella "task" --model opus
/path/to/centella/centella "task" --model-implementer opus --model-classifier haiku

# Optional but recommended — lower the auto-compaction threshold
# for worker processes (default is 95%):
export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=70
```

Via the thin plugin skill from inside Claude Code:

```bash
claude --plugin-dir /path/to/centella
# then in the session:
/centella Fix the login timeout bug and add a regression test
```

## Configuration

Complete reference for every CLI flag, environment variable, and
`centella.toml` key the orchestrator reads.

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `task` (positional) | — | The task description. Required unless `--resume` is given. |
| `--resume` | — | Resume an interrupted run from `.centella/state.json`. |
| `--answers FILE` | — | JSON object of pre-supplied clarification answers (keyed by question `id`; may include `source_of_truth`). |
| `--no-clarify` | off | Skip clarification entirely. Intent questions are dropped; source-of-truth is resolved from `--source-of-truth` / env / file, otherwise defaults to `codebase`. |
| `--max-workers N` | 40 | Cap on total `claude -p` invocations across the run. |
| `--max-parallel N` | 4 | Cap on concurrent workers within a wave. |
| `--confidence-rounds N` | 8 | Evidence-gate rounds the planner and implementer may run before exiting blocked (DESIGN §8). Overrides `CENTELLA_CONFIDENCE_ROUNDS` and `centella.toml`. |
| `--skip-smoke` | off | Skip the live `claude -p` preflight smoke test. |
| `--source-of-truth VALUE` | — | `codebase` / `research` / `both` / `ask`. Overrides `CENTELLA_SOURCE_OF_TRUTH` and `centella.toml`. |
| `--model ALIAS` | `sonnet` | `sonnet` / `opus` / `haiku`. Model for every worker this run. |
| `--model-<worker> ALIAS` | inherits `--model` | Per-worker override. `<worker>` is one of `classifier`, `planner`, `implementer`, `integrator`, `validator`. |

### Environment variables and `centella.toml` keys

| Env var | `centella.toml` key | Description |
|---------|---------------------|-------------|
| `CENTELLA_SOURCE_OF_TRUTH` | `source_of_truth` | Sticky source-of-truth preference (`codebase` / `research` / `both` / `ask`). Overridden by `--source-of-truth`. |
| `CENTELLA_MODEL` | `model` | Default model alias for all workers. Overridden by `--model`. |
| `CENTELLA_MODEL_<WORKER>` | `model_<worker>` | Per-worker default (e.g. `CENTELLA_MODEL_IMPLEMENTER=opus`). Overridden by `--model-<worker>`. `<worker>` ∈ `classifier`, `planner`, `implementer`, `integrator`, `validator`. |
| `CENTELLA_CONFIDENCE_ROUNDS` | `confidence_rounds` | Evidence-gate rounds per worker (positive integer, default 8). Overridden by `--confidence-rounds`. |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | — | **Claude Code CLI variable**, not consumed by centella. Set to `70` to backstop worker auto-compaction. |

### Precedence

- **Source-of-truth** (highest first): `--source-of-truth` →
  `CENTELLA_SOURCE_OF_TRUTH` → `centella.toml` → default `ask`.
- **Model** (per worker, highest first): `--model-<worker>` →
  `--model` → `CENTELLA_MODEL_<WORKER>` → `CENTELLA_MODEL` →
  `model_<worker>` in `centella.toml` → `model` in `centella.toml` →
  default `sonnet`.
- **Confidence rounds** (highest first): `--confidence-rounds` →
  `CENTELLA_CONFIDENCE_ROUNDS` → `confidence_rounds` in
  `centella.toml` → default `8`.

See [`docs/IMPLEMENTATION.md`](docs/IMPLEMENTATION.md) §2 for the
rationale behind these orders and the full validation contract.

## Worker types

Centella spawns five kinds of `claude -p` worker. Each is a separate
subprocess; there is no in-session agent nesting.

| Worker | Prompt source | Runs per task | Returns |
|--------|---------------|---------------|---------|
| `classifier` | `prompts/classifier.md` | 1 | category set + intent questions |
| `planner` | `prompts/planner.md` | one per category (parallel) | subtask list with deps |
| `implementer` | `prompts/implementer.md` | one per subtask (per wave, parallel) | commits on a `centella/<subtask-id>` branch |
| `integrator` | `prompts/integrator.md` | on conflict during wave integration | resolved merge commit on `centella/staging` |
| `validator` | constant `VALIDATOR_SYSTEM` in `centella.py` (not a file) | once per wave | pass/fail on staging |

See [`docs/DESIGN.md`](docs/DESIGN.md) §7 for the worker contract and
[`docs/IMPLEMENTATION.md`](docs/IMPLEMENTATION.md) §3 for the invocation
surface (flags, timeouts, schema enforcement).

## Walkthrough

For a worked end-to-end example — from invocation through clarification,
wave execution, staging review, and merge — see
[`docs/USAGE.md`](docs/USAGE.md).

## Development

Tests:

```bash
pip install pytest    # only dev dependency
pytest tests/         # from the repo root
```

The suite covers the deterministic enforcement functions, including a
coupling test that the retry-policy markers match the live check-function
strings. See [`docs/IMPLEMENTATION.md`](docs/IMPLEMENTATION.md) §10 for
the test layout. The worker invocation path is not unit-tested (a stub or
live `claude` binary would be needed; out of scope for the current suite).

## Files

| Path | What it is |
|------|------------|
| `orchestrator/centella.py` | The orchestrator — all phases, waves, caps, retries |
| `prompts/classifier.md` | System prompt: classify task + surface intent questions |
| `prompts/planner.md` | System prompt: decompose one category into a subtask plan |
| `prompts/implementer.md` | System prompt: execute one subtask end to end |
| `prompts/integrator.md` | System prompt: resolve merge conflicts behaviorally |
| `scripts/setup-staging.sh` | Create `centella/staging` branch + worktree |
| `scripts/new-worktree.sh` | Create per-subtask branch + worktree off staging |
| `scripts/integrate.sh` | Merge a subtask branch into staging |
| `scripts/finalize.sh` | Merge staging into the working branch |
| `scripts/cleanup.sh` | Remove worktrees; optionally delete `centella/*` branches |
| `centella` | Executable entry-point wrapper |
| `commands/centella.md` | Thin plugin skill — reachable as `/centella` from Claude Code |
| `docs/DESIGN.md` | Full design document and rationale |
| `docs/IMPLEMENTATION.md` | Current code-surface spec (functions, caps, schemas) |
| `docs/USAGE.md` | End-to-end walkthrough of one Centella run |
| `CONTRIBUTING.md` | Development setup, task-completion checklist, PR conventions |

## Safety

Acting workers use `--dangerously-skip-permissions`. That is a real risk
surface — it is what makes the run unattended. It is bounded by worktree
isolation (each worker operates in its own isolated checkout, not your main
working tree) but not eliminated. **Run on repositories you trust, ideally in
a container, and review the `centella/staging` branch before relying on the
result.**

The run writes only to `.centella/` (auto-excluded from git via
`.git/info/exclude`) and to `centella/*` branches until Phase 6, when it merges
into your working branch. After a run, `centella/*` branches are kept as an
audit trail. Remove them with `scripts/cleanup.sh --branches`.

## Troubleshooting

- **`claude: command not found`** — Centella shells out to the Claude Code
  CLI; install it from https://claude.ai/code and confirm with
  `claude --version`. There is no fallback path.

- **Exits with code 10** — not an error. Centella needs clarification
  answers and you are running non-interactively. Read
  `.centella/pending-questions.json`, write the answers to
  `.centella/answers.json`, then `./centella --resume --answers .centella/answers.json`.
  The plugin skill at `commands/centella.md` handles this relay
  automatically when invoked as `/centella`.

- **Run interrupted (Ctrl-C, reboot, network blip)** — `./centella --resume`
  from the same directory. The resume cursor is `state.completed_waves` in
  `.centella/state.json`; finished waves are not re-run.

- **A subtask reports `blocked`** — the implementer hit something it
  cannot resolve and bailed before integration. Read the blocker reason in
  `.centella/state.json` under `blocked[<subtask-id>]`, address the
  upstream cause, then resume. See [`docs/DESIGN.md`](docs/DESIGN.md) §8
  for the evidence-gated loop.

- **Staging / worktree conflicts on a re-run** — `scripts/cleanup.sh --branches`
  removes worktrees and deletes the `centella/*` branches so a fresh run
  has a clean slate. Then re-invoke as normal.

## FAQ

**Do I need an Anthropic API key?**
No. Centella runs entirely on the Claude Code CLI and your existing
subscription. The orchestrator shells out to `claude -p` workers; no API
key is read or sent.

**Can I run multiple Centella instances in the same repository?**
No. The `.centella/` state directory and the `centella/staging` branch
are single-instance. Run separate tasks sequentially, or use separate
clones for parallel work.

**Does Centella work outside a git repository?**
No. Per-subtask isolation is provided by `git worktree`; the worktree
mechanism is load-bearing, not optional.

**What if my project has no test runner?**
The validator falls back to a worker-driven correctness check. See
[`docs/IMPLEMENTATION.md`](docs/IMPLEMENTATION.md) §4 for `detect_test_runner()`
and what happens when nothing is detected.

**Can I see what each worker did?**
Yes. Every worker commits to its own `centella/<subtask-id>` branch and
those branches survive the run. `git log centella/<subtask-id>` is your
per-worker audit trail; `scripts/cleanup.sh --branches` removes them when
you no longer need them.

**Why not use the Claude Code SDK or the in-session Agent tool?**
Two platform constraints make subprocess workers the right shape. See
[`docs/DESIGN.md`](docs/DESIGN.md) §2.

## Contributing

Contributions welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for
development setup, the task-completion checklist, and PR conventions.
Security issues: see [`SECURITY.md`](SECURITY.md).

## License

MIT — see [`LICENSE`](LICENSE).

## Status

v0.2.0 — see [`CHANGELOG.md`](CHANGELOG.md). The orchestrator's phase flow, wave scheduling, cross-domain dependency
resolution, and git worktree mechanics are all tested. First contact with a live
`claude -p` session is the remaining verification step. Limitations and planned
work are in [`docs/DESIGN.md`](docs/DESIGN.md).
