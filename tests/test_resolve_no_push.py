"""Tests for resolve_no_push() — the --no-push preference resolver.

Covers the precedence order: CLI flag → CENTELLA_NO_PUSH env var →
no_push in centella.toml → False (push by default per DESIGN §6).

Also covers boolean parsing (1/0, true/false, yes/no, on/off) and the
die() path for typos in env or TOML.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def repo_root(tmp_path, monkeypatch):
    """An empty repo-root directory with CENTELLA_NO_PUSH unset."""
    monkeypatch.delenv("CENTELLA_NO_PUSH", raising=False)
    return tmp_path


def test_default_is_push_enabled(centella, repo_root):
    """No CLI flag, no env, no file → False (push by default)."""
    assert centella.resolve_no_push(repo_root, cli_value=False) is False


def test_cli_flag_wins(centella, repo_root, monkeypatch):
    """--no-push CLI flag is the highest precedence."""
    monkeypatch.setenv("CENTELLA_NO_PUSH", "0")
    (repo_root / "centella.toml").write_text("no_push = false\n")
    assert centella.resolve_no_push(repo_root, cli_value=True) is True


def test_env_set_true(centella, repo_root, monkeypatch):
    monkeypatch.setenv("CENTELLA_NO_PUSH", "1")
    assert centella.resolve_no_push(repo_root, cli_value=False) is True


def test_env_set_false_falls_through_to_default(centella, repo_root, monkeypatch):
    """An env value of 'false' is an explicit "use the default" — but
    since the default is False, the result is False either way. Pin
    behavior so callers know an env-false isn't 'unset'."""
    monkeypatch.setenv("CENTELLA_NO_PUSH", "false")
    assert centella.resolve_no_push(repo_root, cli_value=False) is False


def test_file_set_true_no_env(centella, repo_root):
    (repo_root / "centella.toml").write_text("no_push = true\n")
    assert centella.resolve_no_push(repo_root, cli_value=False) is True


def test_env_wins_over_file(centella, repo_root, monkeypatch):
    """Env is a session knob and outranks the committed centella.toml
    default — same precedence pattern as source-of-truth."""
    (repo_root / "centella.toml").write_text("no_push = true\n")
    monkeypatch.setenv("CENTELLA_NO_PUSH", "false")
    assert centella.resolve_no_push(repo_root, cli_value=False) is False


@pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "on", "ON"])
def test_env_truthy_spellings(centella, repo_root, monkeypatch, value):
    monkeypatch.setenv("CENTELLA_NO_PUSH", value)
    assert centella.resolve_no_push(repo_root, cli_value=False) is True


@pytest.mark.parametrize("value", ["0", "false", "False", "FALSE", "no", "off", "OFF"])
def test_env_falsy_spellings(centella, repo_root, monkeypatch, value):
    monkeypatch.setenv("CENTELLA_NO_PUSH", value)
    assert centella.resolve_no_push(repo_root, cli_value=False) is False


def test_env_garbage_dies(centella, repo_root, monkeypatch):
    """Unrecognized boolean spelling in env → die so a typo doesn't get
    silently treated as False (push by default would be a worse surprise)."""
    monkeypatch.setenv("CENTELLA_NO_PUSH", "maybe")
    with pytest.raises(SystemExit):
        centella.resolve_no_push(repo_root, cli_value=False)


def test_file_garbage_dies(centella, repo_root):
    (repo_root / "centella.toml").write_text("no_push = sometimes\n")
    with pytest.raises(SystemExit):
        centella.resolve_no_push(repo_root, cli_value=False)


def test_env_empty_string_falls_through(centella, repo_root, monkeypatch):
    """CENTELLA_NO_PUSH="" should be treated as unset, not as a value."""
    monkeypatch.setenv("CENTELLA_NO_PUSH", "")
    assert centella.resolve_no_push(repo_root, cli_value=False) is False


def test_cli_false_with_env_true(centella, repo_root, monkeypatch):
    """CLI cli_value=False means '--no-push not passed' (action=store_true
    default). The env/TOML can still set no_push=True. CLI doesn't
    override env in this case because cli_value=False isn't an explicit
    'I want push on' signal — it's just 'I didn't pass --no-push'."""
    monkeypatch.setenv("CENTELLA_NO_PUSH", "1")
    assert centella.resolve_no_push(repo_root, cli_value=False) is True
