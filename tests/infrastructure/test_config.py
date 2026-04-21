
import pytest

from agent_engine.infrastructure.system.config.config import load_config


def test_load_config_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    project = tmp_path / "proj"
    project.mkdir()

    config = load_config(project)
    assert config.cwd == project.resolve()
    assert config.default_provider == "claude"
    assert config.providers.claude is not None
    assert config.providers.claude.model == "opus"
    assert config.providers.claude.effort == "max"
    assert config.http.port == 8938
    assert config.discord.token is None


def test_data_dir_config_overrides(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text(
        "providers:\n  claude:\n    model: sonnet\n    effort: high\nhttp:\n  port: 9999\n"
    )

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))

    config = load_config(project, data_dir=data_dir)
    assert config.providers.claude is not None
    assert config.providers.claude.model == "sonnet"
    assert config.providers.claude.effort == "high"
    assert config.http.port == 9999
    assert config.data_dir == data_dir.resolve()


def test_default_data_dir_uses_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".agent-engine").mkdir(parents=True)
    (home / ".agent-engine" / "config.yaml").write_text(
        "providers:\n  claude:\n    model: sonnet\n    effort: low\n"
    )
    monkeypatch.setenv("HOME", str(home))

    project = tmp_path / "proj"
    project.mkdir()

    config = load_config(project)
    assert config.providers.claude is not None
    assert config.providers.claude.model == "sonnet"


def test_null_model_raises(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".agent-engine").mkdir(parents=True)
    (home / ".agent-engine" / "config.yaml").write_text(
        "providers:\n  claude:\n    model: null\n    effort: max\n"
    )
    monkeypatch.setenv("HOME", str(home))

    project = tmp_path / "proj"
    project.mkdir()

    with pytest.raises(ValueError, match="providers.claude.model"):
        load_config(project)


def test_invalid_effort_raises(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".agent-engine").mkdir(parents=True)
    (home / ".agent-engine" / "config.yaml").write_text(
        "providers:\n  claude:\n    model: opus\n    effort: ludicrous\n"
    )
    monkeypatch.setenv("HOME", str(home))

    project = tmp_path / "proj"
    project.mkdir()

    with pytest.raises(ValueError, match="providers.claude.effort"):
        load_config(project)


def test_default_provider_must_be_configured(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".agent-engine").mkdir(parents=True)
    (home / ".agent-engine" / "config.yaml").write_text(
        "default_provider: chatgpt\n"
    )
    monkeypatch.setenv("HOME", str(home))

    project = tmp_path / "proj"
    project.mkdir()

    with pytest.raises(ValueError, match="default_provider"):
        load_config(project)


def test_env_overrides(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENT_ENGINE_DISCORD_TOKEN", "token-abc")
    monkeypatch.setenv("AGENT_ENGINE_HTTP_PORT", "5000")

    config = load_config(project, data_dir=data_dir)
    assert config.discord.token == "token-abc"
    assert config.http.port == 5000


def test_bad_cwd_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does-not-exist")


def test_database_path_uses_data_dir(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)

    config = load_config(project, data_dir=data_dir)
    assert config.database_path == data_dir.resolve() / "agent-engine.db"


def test_vault_directory_defaults_to_data_dir(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)

    config = load_config(project, data_dir=data_dir)
    assert config.vault.directory == data_dir.resolve()


def test_vault_directory_configurable(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (data_dir / "config.yaml").write_text(
        "vault:\n  directory: " + str(vault_dir) + "\n"
    )
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)

    config = load_config(project, data_dir=data_dir)
    assert config.vault.directory == vault_dir.resolve()
