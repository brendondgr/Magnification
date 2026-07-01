"""
Tests for the shared project-root resolver (`utils/backend/paths.py`).

The regression this guards against: a `__file__`-relative root computation resolves
to a *worktree's* own directory (which has no shared, gitignored `data/`/`config/`),
instead of the single root shared by the main checkout and every worktree.
"""

import subprocess

import pytest

from utils.backend import paths


@pytest.fixture(autouse=True)
def _clear_cache():
    paths.get_project_root.cache_clear()
    yield
    paths.get_project_root.cache_clear()


def test_resolves_to_a_directory_containing_pyproject():
    root = paths.get_project_root()
    assert root.is_dir()
    assert (root / "pyproject.toml").is_file()


def test_resolves_to_the_main_git_dir_not_a_worktree_gitfile():
    # Whether this test itself runs from the main checkout or from a worktree,
    # get_project_root() must land on the checkout whose `.git` is a real
    # directory (the main checkout) rather than a worktree's `.git` gitlink file.
    root = paths.get_project_root()
    assert (root / ".git").is_dir()


def test_falls_back_when_git_is_unavailable(monkeypatch):
    def _raise(*args, **kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", _raise)
    assert paths.get_project_root() == paths._FALLBACK_ROOT


def test_falls_back_when_git_command_fails(monkeypatch):
    def _fail(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=128, cmd=args)

    monkeypatch.setattr(subprocess, "run", _fail)
    assert paths.get_project_root() == paths._FALLBACK_ROOT


def test_result_is_cached(monkeypatch):
    calls = {"n": 0}
    real_run = subprocess.run

    def _counting_run(*args, **kwargs):
        calls["n"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _counting_run)
    paths.get_project_root()
    paths.get_project_root()
    assert calls["n"] == 1


def test_all_gitignored_data_paths_share_the_same_root():
    # Every module that resolves a gitignored data/config file must agree on the
    # same root, so the database and the job/LLM/runtime configs can never drift
    # apart again the way they did before this fix.
    from utils.backend.database.config import DATABASE_PATH
    from utils.backend.scrapers.job_filter import JOBS_CONFIG_PATH as job_filter_path
    from utils.backend.scrapers.task_generator import JOBS_CONFIG_PATH as task_gen_path
    from utils.backend.routes.config_routes import CONFIG_PATH as jobs_route_path
    from utils.backend.llm.config import CONFIG_PATH as llm_endpoint_path
    from utils.backend.recommend.runtime_config import CONFIG_PATH as runtime_path

    root = str(paths.get_project_root())
    for path in (
        str(DATABASE_PATH),
        job_filter_path,
        task_gen_path,
        jobs_route_path,
        llm_endpoint_path,
        runtime_path,
    ):
        assert str(path).startswith(root), f"{path} does not resolve under {root}"
