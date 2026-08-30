"""Tests for rebob.paths — the single path-resolution authority."""

import os

import pytest

from rebob import paths


@pytest.fixture(autouse=True)
def _reset_paths_cache():
    paths.reset_cache()
    yield
    paths.reset_cache()


class TestRebobHome:
    def test_rebob_home_env_var_wins(self, tmp_path, monkeypatch):
        target = tmp_path / "explicit-home"
        monkeypatch.setenv("REBOB_HOME", str(target))
        assert paths.rebob_home() == target.resolve()

    def test_rebob_project_root_env_var(self, tmp_path, monkeypatch):
        monkeypatch.delenv("REBOB_HOME", raising=False)
        monkeypatch.setenv("REBOB_PROJECT_ROOT", str(tmp_path))
        assert paths.rebob_home() == (tmp_path / ".rebob").resolve()

    def test_rebob_home_takes_priority_over_project_root(self, tmp_path, monkeypatch):
        home = tmp_path / "home-wins"
        monkeypatch.setenv("REBOB_HOME", str(home))
        monkeypatch.setenv("REBOB_PROJECT_ROOT", str(tmp_path / "other"))
        assert paths.rebob_home() == home.resolve()

    def test_marker_search_finds_existing_rebob_dir(self, tmp_path, monkeypatch):
        monkeypatch.delenv("REBOB_HOME", raising=False)
        monkeypatch.delenv("REBOB_PROJECT_ROOT", raising=False)
        project = tmp_path / "project"
        (project / ".rebob").mkdir(parents=True)
        sub = project / "src" / "nested"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        assert paths.rebob_home() == (project / ".rebob").resolve()

    def test_marker_search_finds_bob_dir_when_no_rebob_dir(self, tmp_path, monkeypatch):
        monkeypatch.delenv("REBOB_HOME", raising=False)
        monkeypatch.delenv("REBOB_PROJECT_ROOT", raising=False)
        project = tmp_path / "project"
        (project / ".bob").mkdir(parents=True)
        monkeypatch.chdir(project)
        assert paths.rebob_home() == (project / ".rebob").resolve()

    def test_marker_search_finds_pyproject_toml(self, tmp_path, monkeypatch):
        monkeypatch.delenv("REBOB_HOME", raising=False)
        monkeypatch.delenv("REBOB_PROJECT_ROOT", raising=False)
        project = tmp_path / "project"
        project.mkdir(parents=True)
        (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        sub = project / "a" / "b" / "c"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        assert paths.rebob_home() == (project / ".rebob").resolve()

    def test_falls_back_to_cwd_when_no_marker_found(self, tmp_path, monkeypatch):
        monkeypatch.delenv("REBOB_HOME", raising=False)
        monkeypatch.delenv("REBOB_PROJECT_ROOT", raising=False)
        isolated = tmp_path / "no-markers-here"
        isolated.mkdir()
        monkeypatch.chdir(isolated)
        assert paths.rebob_home() == (isolated / ".rebob").resolve()

    def test_result_is_cached_across_calls(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REBOB_HOME", str(tmp_path / "first"))
        first = paths.rebob_home()
        # Changing the env var after the first call must NOT change the result
        # until reset_cache() is called — this is the documented caching contract.
        monkeypatch.setenv("REBOB_HOME", str(tmp_path / "second"))
        assert paths.rebob_home() == first

    def test_reset_cache_allows_re_resolution(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REBOB_HOME", str(tmp_path / "first"))
        paths.rebob_home()
        monkeypatch.setenv("REBOB_HOME", str(tmp_path / "second"))
        paths.reset_cache()
        assert paths.rebob_home() == (tmp_path / "second").resolve()

    def test_handles_path_with_spaces(self, tmp_path, monkeypatch):
        target = tmp_path / "IBM BOB" / "My Project"
        target.mkdir(parents=True)
        monkeypatch.setenv("REBOB_HOME", str(target / ".rebob"))
        assert paths.rebob_home() == (target / ".rebob").resolve()


class TestDerivedPaths:
    def test_project_root_is_parent_of_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REBOB_HOME", str(tmp_path / "proj" / ".rebob"))
        assert paths.project_root() == (tmp_path / "proj").resolve()

    def test_all_subdirs_derive_from_home(self, tmp_path, monkeypatch):
        home = tmp_path / ".rebob"
        monkeypatch.setenv("REBOB_HOME", str(home))
        assert paths.db_path() == home.resolve() / "rebob.db"
        assert paths.vectors_path() == home.resolve() / "vectors.npy"
        assert paths.sessions_dir() == home.resolve() / "sessions"
        assert paths.pending_dir() == home.resolve() / "pending"
        assert paths.injected_dir() == home.resolve() / "injected"
        assert paths.captures_dir() == home.resolve() / "captures"
        assert paths.embed_cache_dir() == home.resolve() / "embed_cache"

    def test_env_file_and_bob_dir_are_project_root_relative(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REBOB_HOME", str(tmp_path / "proj" / ".rebob"))
        assert paths.env_file() == (tmp_path / "proj" / ".env").resolve()
        assert paths.bob_dir() == (tmp_path / "proj" / ".bob").resolve()


class TestDescribe:
    def test_describe_returns_all_string_paths(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REBOB_HOME", str(tmp_path / ".rebob"))
        info = paths.describe()
        expected_keys = {
            "project_root", "rebob_home", "db_path", "vectors_path",
            "sessions_dir", "pending_dir", "injected_dir", "captures_dir",
            "embed_cache_dir", "env_file", "bob_dir", "resolved_from",
        }
        assert set(info.keys()) == expected_keys
        for key in expected_keys - {"resolved_from"}:
            assert isinstance(info[key], str)

    def test_describe_reports_rebob_home_source(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REBOB_HOME", str(tmp_path / "x"))
        assert paths.describe()["resolved_from"] == "REBOB_HOME"

    def test_describe_reports_project_root_source(self, tmp_path, monkeypatch):
        monkeypatch.delenv("REBOB_HOME", raising=False)
        monkeypatch.setenv("REBOB_PROJECT_ROOT", str(tmp_path))
        assert paths.describe()["resolved_from"] == "REBOB_PROJECT_ROOT"
