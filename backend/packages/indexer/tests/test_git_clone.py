"""Private-repo clone: token goes in a per-process header, never argv or the clone's config."""

import base64
import subprocess
from pathlib import Path

import pytest
from ci_core.settings import get_settings
from ci_parsers import GitCloneError, clone_git_repo
from ci_parsers.files import _git_auth_env


def test_auth_env_sends_token_as_header_only():
    env = _git_auth_env("ghp_secret")
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert base64.b64encode(b"x-access-token:ghp_secret").decode() in env["GIT_CONFIG_VALUE_0"]
    assert "GIT_CONFIG_COUNT" not in _git_auth_env(None)


def test_clone_failure_is_clear_and_never_leaks_token(tmp_path: Path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 128, "", "remote: Repository not found.\nfatal: not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(GitCloneError, match="CI_GITHUB_TOKEN"):
        clone_git_repo("https://github.com/o/private", tmp_path / "r")
    with pytest.raises(GitCloneError) as info:
        clone_git_repo("https://github.com/o/private", tmp_path / "r", token="ghp_secret")
    assert "ghp_secret" not in str(info.value)
    assert all("ghp_secret" not in " ".join(c) for c in calls)


def test_settings_reads_github_token(monkeypatch):
    monkeypatch.delenv("CI_GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "t1")
    assert get_settings().github_token == "t1"
    monkeypatch.setenv("CI_GITHUB_TOKEN", "t2")
    assert get_settings().github_token == "t2"
    assert "t2" not in repr(get_settings())
