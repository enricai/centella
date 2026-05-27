"""Tests for validate_resume_state().

Covers the structural shape checks applied to a loaded state.json
before a `--resume` proceeds.
"""
from __future__ import annotations

import pytest


def test_minimal_valid_state(centella):
    """A state with just task is valid (waves can be absent for a run
    interrupted before scheduling)."""
    centella.validate_resume_state({"task": "do the thing"})


def test_missing_task_dies(centella, capsys):
    with pytest.raises(SystemExit) as exc:
        centella.validate_resume_state({})
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "no usable 'task'" in err


def test_blank_task_dies(centella, capsys):
    with pytest.raises(SystemExit) as exc:
        centella.validate_resume_state({"task": "   "})
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "no usable 'task'" in err


def test_new_clarify_key_accepted(centella):
    """A state with the new `clarify` key resumes fine."""
    centella.validate_resume_state({"task": "x", "clarify": False})
    centella.validate_resume_state({"task": "x", "clarify": True})


def test_waves_must_be_list_of_lists(centella, capsys):
    with pytest.raises(SystemExit) as exc:
        centella.validate_resume_state({"task": "x", "waves": "not a list"})
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "waves" in err


def test_completed_waves_out_of_range_dies(centella, capsys):
    with pytest.raises(SystemExit) as exc:
        centella.validate_resume_state(
            {"task": "x", "waves": [["a"], ["b"]], "completed_waves": 5})
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "completed_waves" in err


def test_subtask_status_must_be_dict(centella, capsys):
    with pytest.raises(SystemExit) as exc:
        centella.validate_resume_state(
            {"task": "x", "subtask_status": ["a", "b"]})
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "subtask_status" in err
