from pathlib import Path

import pytest

from agent_engine.infrastructure.system.config.config import load_config


def test_load_config_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    project = tmp_path / "proj"
    project.mkdir()

    config = load_config(project)
    assert config.cwd == project.resolve()
    assert config.provider.name == "claude"
    assert config.http.port == 8938
    assert config.discord.token is None


def test_project_config_overrides_global(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".agent-engine").mkdir()
    (home / ".agent-engine" / "config.yaml").write_text(
        "provider:\n  name: claude\n  model: opus\n"
    )

    project = tmp_path / "proj"
    project.mkdir()
    (project / ".agent-engine").mkdir()
    (project / ".agent-engine" / "config.yaml").write_text(
        "provider:\n  model: sonnet\nhttp:\n  port: 9999\n"
    )

    monkeypatch.setenv("HOME", str(home))

    config = load_config(project)
    assert config.provider.model == "sonnet"
    assert config.http.port == 9999


def test_env_overrides(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENT_ENGINE_DISCORD_TOKEN", "token-abc")
    monkeypatch.setenv("AGENT_ENGINE_HTTP_PORT", "5000")

    config = load_config(project)
    assert config.discord.token == "token-abc"
    assert config.http.port == 5000


def test_bad_cwd_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does-not-exist")


def test_engine_dir_and_database_path(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)

    config = load_config(project)
    assert config.engine_dir == project.resolve() / ".agent-engine"
    assert config.database_path == project.resolve() / ".agent-engine" / "agent-engine.db"
