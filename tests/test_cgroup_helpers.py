"""Tests for the cgroup v2 containment helpers in pila.py.

These helpers live in `orchestrator/pila.py` (search for
`_cgroup_probe`, `_cgroup_create`, `_cgroup_enroll`, `_cgroup_destroy`).
They are best-effort: pila MUST keep running when /sys/fs/cgroup is
read-only or missing. The tests below pin three contracts:

  1. Probe failure makes all subsequent helpers no-op cleanly.
  2. Successful probe + create writes memory.max and pids.max files.
  3. _cgroup_destroy is idempotent (swallow ENOENT and missing files).

We do NOT exercise real /sys/fs/cgroup on the test host because pytest
typically runs on the developer's Mac (no cgroupfs) or in CI with
varying cgroup setups. Instead we point `_CGROUP_ROOT` at a tmp_path
and exercise the file-write surfaces directly.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def reset_probe_memo(pila):
    """Reset the module-level probe memo before every test. Without
    this, the first test that sets `_CGROUP_PROBE_RESULT` would force
    the same value into every subsequent test."""
    pila._CGROUP_PROBE_RESULT = None
    yield
    pila._CGROUP_PROBE_RESULT = None


# ---- probe ----------------------------------------------------------------

def test_probe_success_when_root_writable(pila, tmp_path, monkeypatch):
    """A writable directory acting as the cgroup root: probe creates
    `pila-probe`, writes memory.max, removes the dir, returns True."""
    monkeypatch.setattr(pila, "_CGROUP_ROOT", tmp_path)
    assert pila._cgroup_probe() is True
    # Probe must have cleaned up the probe directory.
    assert not (tmp_path / "pila-probe").exists()


def test_probe_failure_when_root_readonly(pila, tmp_path, monkeypatch):
    """When the root directory exists but mkdir fails, probe returns
    False and degrades gracefully."""
    monkeypatch.setattr(pila, "_CGROUP_ROOT", tmp_path / "missing-path")
    assert pila._cgroup_probe() is False


def test_probe_memoizes(pila, tmp_path, monkeypatch):
    """Once probe runs, the result is cached; the second call is a
    pure read of `_CGROUP_PROBE_RESULT`. Verify by making the second
    call use a path that would otherwise fail — if memoization works,
    we still get the original result."""
    monkeypatch.setattr(pila, "_CGROUP_ROOT", tmp_path)
    first = pila._cgroup_probe()
    # Swap the root to a non-writable location; memoized result should
    # still be returned.
    monkeypatch.setattr(pila, "_CGROUP_ROOT",
                        Path("/sys/fs/cgroup-does-not-exist"))
    second = pila._cgroup_probe()
    assert first == second


# ---- create ---------------------------------------------------------------

def test_create_writes_caps(pila, tmp_path, monkeypatch):
    """A successful create makes the directory and writes memory.max
    and pids.max with the given values."""
    monkeypatch.setattr(pila, "_CGROUP_ROOT", tmp_path)
    pila._cgroup_probe()  # prime the memo
    path = pila._cgroup_create("test-sid", 256 * 1024**2, 64)
    assert path is not None
    assert (path / "memory.max").read_text() == str(256 * 1024**2)
    assert (path / "pids.max").read_text() == "64"


def test_create_returns_none_when_probe_failed(pila, monkeypatch):
    """If the probe says no, create is a no-op returning None — the
    worker spawns uncapped."""
    monkeypatch.setattr(pila, "_CGROUP_ROOT",
                        Path("/sys/fs/cgroup-does-not-exist"))
    pila._cgroup_probe()
    assert pila._cgroup_create("sid", 1 << 30, 64) is None


def test_create_idempotent(pila, tmp_path, monkeypatch):
    """Re-creating with the same sid (e.g., handoff continuation)
    reuses the dir and rewrites the caps with the new values."""
    monkeypatch.setattr(pila, "_CGROUP_ROOT", tmp_path)
    pila._cgroup_probe()
    p1 = pila._cgroup_create("sid-a", 1 << 28, 64)
    p2 = pila._cgroup_create("sid-a", 1 << 30, 128)
    assert p1 == p2
    assert (p2 / "memory.max").read_text() == str(1 << 30)
    assert (p2 / "pids.max").read_text() == "128"


# ---- enroll ---------------------------------------------------------------

def test_enroll_writes_pid(pila, tmp_path, monkeypatch):
    monkeypatch.setattr(pila, "_CGROUP_ROOT", tmp_path)
    pila._cgroup_probe()
    path = pila._cgroup_create("sid-b", 1 << 30, 64)
    assert pila._cgroup_enroll(path, 12345) is True
    assert (path / "cgroup.procs").read_text() == "12345"


def test_enroll_returns_false_on_failure(pila, tmp_path):
    """Enroll into a path that doesn't exist returns False (logs but
    does not raise)."""
    bogus = tmp_path / "nope"
    assert pila._cgroup_enroll(bogus, 1) is False


# ---- destroy --------------------------------------------------------------

def test_destroy_attempts_cgroup_kill_then_rmdir(pila, tmp_path,
                                                  monkeypatch):
    """The destroy contract on a real cgroupfs: write '1' to
    cgroup.kill (atomic kill of the cgroup, kernel ≥5.14), then
    rmdir. On a regular filesystem (like this test), cgroup.kill is
    just a stray file we write; rmdir then fails (dir non-empty) but
    OSError is swallowed. The test verifies cgroup.kill IS written
    and that no exception propagates."""
    monkeypatch.setattr(pila, "_CGROUP_ROOT", tmp_path)
    pila._cgroup_probe()
    path = pila._cgroup_create("sid-c", 1 << 30, 64)
    pila._cgroup_destroy(path)
    # cgroup.kill was attempted (file exists on regular fs).
    assert (path / "cgroup.kill").read_text() == "1"
    # No exception propagated. Whether the dir survives depends on the
    # filesystem; on real cgroupfs the kernel reaps it atomically, on
    # regular fs the files prevent rmdir but the OSError is swallowed.


def test_destroy_handles_none(pila):
    """None path (cgroup containment was off for this worker) is a
    no-op, no exception."""
    pila._cgroup_destroy(None)


def test_destroy_handles_missing_path(pila, tmp_path):
    """Destroy on a path that doesn't exist swallows the ENOENT and
    returns cleanly."""
    pila._cgroup_destroy(tmp_path / "never-existed")
