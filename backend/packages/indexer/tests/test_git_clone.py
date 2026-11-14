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


def test_check_git_access_classifies_results(monkeypatch):
    from ci_parsers import check_git_access

    def fake(stdout="", stderr="", code=0):
        return lambda args, **kw: subprocess.CompletedProcess(args, code, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", fake("ref: refs/heads/develop\tHEAD\nabc\tHEAD\n"))
    assert check_git_access("https://github.com/o/r") == {"ok": True, "default_branch": "develop", "authenticated": False}
    monkeypatch.setattr(subprocess, "run", fake(stderr="remote: Repository not found.", code=128))
    res = check_git_access("https://github.com/o/r")
    assert res["ok"] is False and res["needs_token"] is True and "CI_GITHUB_TOKEN" in res["reason"]
    res = check_git_access("https://github.com/o/r", token="ghp_x")
    assert res["needs_token"] is False and "ghp_x" not in res["reason"]


def test_github_urls_normalize_to_the_token_scope():
    from ci_parsers import normalize_github_url, parse_github_url

    for raw in ("http://github.com/Org/App", "https://www.github.com/Org/App.git", "https://github.com/Org/App/"):
        assert normalize_github_url(raw) == "https://github.com/Org/App"
    assert parse_github_url("https://github.com/o/my.repo.git") == ("o", "my.repo")
    assert parse_github_url("https://gitlab.com/o/r") is None


def test_rejected_token_falls_back_to_anonymous_for_public_repos(monkeypatch):
    from ci_parsers import check_git_access

    def run(args, **kw):
        authed = "GIT_CONFIG_COUNT" in kw["env"]
        if authed:
            return subprocess.CompletedProcess(args, 128, "", "fatal: Authentication failed")
        return subprocess.CompletedProcess(args, 0, "ref: refs/heads/main\tHEAD\n", "")

    monkeypatch.setattr(subprocess, "run", run)
    res = check_git_access("https://github.com/o/public", token="stale")
    assert res["ok"] is True and "rejected" in res["warning"]


def test_same_repo_name_under_different_owners_gets_separate_clones(tmp_path, monkeypatch):
    import ci_parsers
    from ci_indexer import pipeline

    cloned: list[Path] = []
    monkeypatch.setattr(ci_parsers, "check_git_access", lambda url, token=None: {"ok": True})
    monkeypatch.setattr(ci_parsers, "clone_git_repo", lambda url, dest, token=None: cloned.append(dest) or dest.mkdir(parents=True))
    monkeypatch.setattr(pipeline, "create_project_from_path", lambda dest, git_url=None: (dest, git_url))
    a = pipeline.create_project_from_git("https://github.com/a/api", work_root=tmp_path)
    b = pipeline.create_project_from_git("http://www.github.com/b/api.git", work_root=tmp_path)
    assert cloned == [tmp_path / "a__api", tmp_path / "b__api"]
    assert b[1] == "https://github.com/b/api" and a[0] != b[0]
