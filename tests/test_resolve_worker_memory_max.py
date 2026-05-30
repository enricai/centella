"""Tests for _parse_memory_size, _auto_worker_memory_max, and
resolve_worker_memory_max — the resolver chain for the per-worker
cgroup memory cap.

Covers:
- Memory-size parsing: K/M/G/T suffixes, bare bytes, garbage rejected.
- Auto-derivation from /proc/meminfo (mocked) — splits VM ram across
  max_parallel+1 slots, capped at 4 GiB.
- Resolution order: CLI > env > pila.toml > auto.
- die() paths for invalid env / file values.
"""
from __future__ import annotations

import pytest


# ---- _parse_memory_size ---------------------------------------------------

def test_parse_memory_size_bytes(pila):
    assert pila._parse_memory_size("1024", "ctx") == 1024


def test_parse_memory_size_kib(pila):
    assert pila._parse_memory_size("4K", "ctx") == 4 * 1024


def test_parse_memory_size_mib(pila):
    assert pila._parse_memory_size("512M", "ctx") == 512 * 1024**2


def test_parse_memory_size_gib(pila):
    assert pila._parse_memory_size("4G", "ctx") == 4 * 1024**3


def test_parse_memory_size_tib(pila):
    assert pila._parse_memory_size("1T", "ctx") == 1024**4


def test_parse_memory_size_lowercase_suffix(pila):
    assert pila._parse_memory_size("2g", "ctx") == 2 * 1024**3


def test_parse_memory_size_whitespace_tolerated(pila):
    assert pila._parse_memory_size("  256M  ", "ctx") == 256 * 1024**2


def test_parse_memory_size_empty_dies(pila):
    with pytest.raises(SystemExit):
        pila._parse_memory_size("", "ctx")


def test_parse_memory_size_garbage_dies(pila):
    with pytest.raises(SystemExit):
        pila._parse_memory_size("4XYZ", "ctx")


def test_parse_memory_size_negative_dies(pila):
    with pytest.raises(SystemExit):
        pila._parse_memory_size("-4G", "ctx")


def test_parse_memory_size_zero_dies(pila):
    with pytest.raises(SystemExit):
        pila._parse_memory_size("0", "ctx")


def test_parse_memory_size_fractional_rejected(pila):
    """We reject '1.5G' rather than rounding silently. The user can
    write '1536M' if they need fractional values."""
    with pytest.raises(SystemExit):
        pila._parse_memory_size("1.5G", "ctx")


# ---- _auto_worker_memory_max ---------------------------------------------

def test_auto_splits_meminfo_across_slots(pila, monkeypatch, tmp_path):
    """Synthesize a /proc/meminfo with 16 GiB total. With max_parallel=4
    the per-worker share is 16 / 5 = 3.2 GiB; that's below the 4 GiB
    cap, so we expect ~3.2 GiB."""
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(f"MemTotal:       {16 * 1024 * 1024} kB\n")
    import builtins
    real_open = builtins.open

    def fake_open(path, *a, **kw):
        if str(path) == "/proc/meminfo":
            return real_open(meminfo, *a, **kw)
        return real_open(path, *a, **kw)
    monkeypatch.setattr("builtins.open", fake_open)
    result = pila._auto_worker_memory_max(max_parallel=4)
    expected = (16 * 1024**3) // 5
    assert result == expected


def test_auto_caps_at_4gib(pila, monkeypatch, tmp_path):
    """With a huge VM (64 GiB / 5 slots = 12.8 GiB), the per-worker
    cap clamps to 4 GiB."""
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(f"MemTotal:       {64 * 1024 * 1024} kB\n")
    import builtins
    real_open = builtins.open

    def fake_open(path, *a, **kw):
        if str(path) == "/proc/meminfo":
            return real_open(meminfo, *a, **kw)
        return real_open(path, *a, **kw)
    monkeypatch.setattr("builtins.open", fake_open)
    assert pila._auto_worker_memory_max(max_parallel=4) == 4 * 1024**3


def test_auto_fallback_when_meminfo_missing(pila, monkeypatch):
    """No /proc/meminfo on macOS host (where the test suite usually
    runs). Auto returns the 2 GiB fallback."""
    import builtins
    real_open = builtins.open

    def fake_open(path, *a, **kw):
        if str(path) == "/proc/meminfo":
            raise FileNotFoundError(2, "No such file", "/proc/meminfo")
        return real_open(path, *a, **kw)
    monkeypatch.setattr("builtins.open", fake_open)
    assert pila._auto_worker_memory_max(max_parallel=4) == 2 * 1024**3


# ---- resolve_worker_memory_max --------------------------------------------

@pytest.fixture
def repo_root(tmp_path, monkeypatch):
    monkeypatch.delenv("PILA_WORKER_MEMORY_MAX", raising=False)
    return tmp_path


def test_cli_value_wins(pila, repo_root, monkeypatch):
    (repo_root / "pila.toml").write_text("worker_memory_max = 1G\n")
    monkeypatch.setenv("PILA_WORKER_MEMORY_MAX", "2G")
    assert pila.resolve_worker_memory_max(
        repo_root, max_parallel=4, cli_value="4G") == 4 * 1024**3


def test_env_wins_over_file(pila, repo_root, monkeypatch):
    (repo_root / "pila.toml").write_text("worker_memory_max = 1G\n")
    monkeypatch.setenv("PILA_WORKER_MEMORY_MAX", "2G")
    assert pila.resolve_worker_memory_max(
        repo_root, max_parallel=4) == 2 * 1024**3


def test_file_used_when_cli_and_env_unset(pila, repo_root):
    (repo_root / "pila.toml").write_text("worker_memory_max = 1G\n")
    assert pila.resolve_worker_memory_max(
        repo_root, max_parallel=4) == 1024**3


def test_auto_fallback_when_nothing_set(pila, repo_root):
    """No CLI, no env, no file — auto-derive from /proc/meminfo (or
    its 2 GiB fallback on macOS)."""
    result = pila.resolve_worker_memory_max(repo_root, max_parallel=4)
    assert result > 0


def test_garbage_env_dies(pila, repo_root, monkeypatch):
    monkeypatch.setenv("PILA_WORKER_MEMORY_MAX", "garbage")
    with pytest.raises(SystemExit):
        pila.resolve_worker_memory_max(repo_root, max_parallel=4)


def test_garbage_file_dies(pila, repo_root):
    (repo_root / "pila.toml").write_text("worker_memory_max = garbage\n")
    with pytest.raises(SystemExit):
        pila.resolve_worker_memory_max(repo_root, max_parallel=4)
