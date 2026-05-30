"""Tests for validate_plan() — the structural validation of merged plans.

Mirrors the IMPLEMENTATION.md §5 plan-validation table. validate_plan
accumulates every issue and dies once with a multi-bullet message, so
each test checks the substring of the relevant error.
"""
from __future__ import annotations

import pytest


def _good_subtask(sid="feat-001", **overrides):
    """A baseline well-formed subtask, overridable per-test."""
    base = {
        "id": sid,
        "title": "a good subtask",
        "intent": "do the thing",
        "scope_note": "one verifiable change",
        "files_likely_touched": ["src/foo.py"],
        "depends_on": [],
        "requires": [],
        "provides": [],
        "success_criteria_seed": "the thing is done",
        "size": "small",
        "investigation_notes": "",
    }
    base.update(overrides)
    return base


def test_well_formed_plan_passes(pila):
    """A clean plan with one subtask per domain-prefixed id passes silently."""
    plan = {
        "feat-001": _good_subtask("feat-001"),
        "test-001": _good_subtask("test-001"),
    }
    # No SystemExit raised → pass.
    pila.validate_plan(plan)


def test_id_without_domain_prefix_dies(pila, capsys):
    plan = {"random-001": _good_subtask("random-001")}
    with pytest.raises(SystemExit):
        pila.validate_plan(plan)
    err = capsys.readouterr().err
    assert "must start with one of" in err
    assert "random-001" in err


def test_size_large_dies(pila, capsys):
    plan = {"feat-001": _good_subtask("feat-001", size="large")}
    with pytest.raises(SystemExit):
        pila.validate_plan(plan)
    err = capsys.readouterr().err
    assert "size='large'" in err
    assert "split" in err


def test_empty_success_criteria_seed_dies(pila, capsys):
    plan = {"feat-001": _good_subtask("feat-001", success_criteria_seed="")}
    with pytest.raises(SystemExit):
        pila.validate_plan(plan)
    err = capsys.readouterr().err
    assert "success_criteria_seed is empty" in err


def test_whitespace_only_success_criteria_seed_dies(pila, capsys):
    plan = {"feat-001": _good_subtask("feat-001", success_criteria_seed="   \n  ")}
    with pytest.raises(SystemExit):
        pila.validate_plan(plan)
    err = capsys.readouterr().err
    assert "success_criteria_seed is empty" in err


def test_dangling_depends_on_dies(pila, capsys):
    plan = {
        "feat-001": _good_subtask("feat-001", depends_on=["feat-999"]),
    }
    with pytest.raises(SystemExit):
        pila.validate_plan(plan)
    err = capsys.readouterr().err
    assert "depends_on 'feat-999'" in err
    assert "does not exist" in err


def test_unresolvable_requires_dies(pila, capsys):
    plan = {
        "feat-001": _good_subtask(
            "feat-001",
            requires=[{"tag": "nonexistent-cap", "extent": "in_plan"}],
        ),
    }
    with pytest.raises(SystemExit):
        pila.validate_plan(plan)
    err = capsys.readouterr().err
    assert "requires 'nonexistent-cap'" in err
    assert "nothing provides it" in err


def test_resolvable_requires_passes(pila):
    """When provides on one subtask matches requires on another, it passes."""
    plan = {
        "feat-001": _good_subtask("feat-001", provides=["feature-x-live"]),
        "test-001": _good_subtask(
            "test-001",
            requires=[{"tag": "feature-x-live", "extent": "in_plan"}],
        ),
    }
    pila.validate_plan(plan)


def test_multiple_errors_accumulated(pila, capsys):
    """validate_plan reports every error in one die() call, not the first."""
    plan = {
        "random-001": _good_subtask(
            "random-001", size="large", success_criteria_seed=""
        ),
    }
    with pytest.raises(SystemExit):
        pila.validate_plan(plan)
    err = capsys.readouterr().err
    # Three issues from this one subtask: bad prefix, large size, empty seed.
    assert "must start with one of" in err
    assert "size='large'" in err
    assert "success_criteria_seed is empty" in err
    assert "3 issue" in err


@pytest.mark.parametrize("prefix", [
    "bugfix-", "feat-", "refactor-", "perf-",
    "test-", "deps-", "config-", "docs-",
])
def test_all_documented_prefixes_accepted(pila, prefix):
    sid = f"{prefix}001"
    plan = {sid: _good_subtask(sid)}
    pila.validate_plan(plan)


# --- requires.extent invariants (DESIGN §5 `requires.extent`) ----------

def test_requires_bare_string_rejected(pila, capsys):
    """`requires` entries must be objects `{tag, extent, reason?}`. Bare
    strings were the pre-extent shape; reject them defensively even
    though the JSON schema catches them earlier — `validate_plan` runs
    after schedule(), which can in principle pass through mutated data."""
    plan = {"feat-001": _good_subtask("feat-001", requires=["bare-string"])}
    with pytest.raises(SystemExit):
        pila.validate_plan(plan)
    err = capsys.readouterr().err
    assert "requires entry must be an object" in err


def test_requires_external_without_reason_rejected(pila, capsys):
    """`extent: external` is a planner declaration that the prerequisite
    lives outside the build graph; the `reason` field is what makes that
    declaration accountable. Reject an external entry that omits it (or
    leaves it empty / whitespace), mirroring the discipline the
    reconciler applies to its `unresolvable` verdict."""
    plan = {
        "feat-001": _good_subtask(
            "feat-001",
            requires=[{"tag": "external-cap", "extent": "external"}],
        ),
    }
    with pytest.raises(SystemExit):
        pila.validate_plan(plan)
    err = capsys.readouterr().err
    assert "extent=external" in err
    assert "reason" in err


def test_requires_external_with_whitespace_only_reason_rejected(pila, capsys):
    plan = {
        "feat-001": _good_subtask(
            "feat-001",
            requires=[{"tag": "external-cap", "extent": "external",
                       "reason": "   \n  "}],
        ),
    }
    with pytest.raises(SystemExit):
        pila.validate_plan(plan)
    err = capsys.readouterr().err
    assert "extent=external" in err


def test_requires_unknown_extent_rejected(pila, capsys):
    """`extent` is an enum; defensive Python check in addition to the
    JSON schema enum (schema runs at worker output time; this catches
    a downstream mutation that smuggled in a bad value)."""
    plan = {
        "feat-001": _good_subtask(
            "feat-001",
            requires=[{"tag": "x", "extent": "maybe"}],
        ),
    }
    with pytest.raises(SystemExit):
        pila.validate_plan(plan)
    err = capsys.readouterr().err
    assert "unknown extent" in err


def test_requires_external_does_not_need_a_provider(pila):
    """An `extent: external` entry is explicitly out-of-graph — no
    in-plan provider is required (or expected). validate_plan must NOT
    flag it as unresolvable."""
    plan = {
        "feat-001": _good_subtask(
            "feat-001",
            requires=[{
                "tag": "dynamo-table-in-region",
                "extent": "external",
                "reason": "provisioned by the api-services repo's CDK stack",
            }],
        ),
    }
    pila.validate_plan(plan)  # no SystemExit


def test_requires_in_plan_without_provider_still_dies(pila, capsys):
    """The pre-existing missing-provider check still applies to
    `extent: in_plan` entries — extent only changes behavior for
    external, not in_plan."""
    plan = {
        "feat-001": _good_subtask(
            "feat-001",
            requires=[{"tag": "missing-cap", "extent": "in_plan"}],
        ),
    }
    with pytest.raises(SystemExit):
        pila.validate_plan(plan)
    err = capsys.readouterr().err
    assert "requires 'missing-cap'" in err
    assert "nothing provides it" in err
