import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_DATA_DIR = Path.home() / ".agent-engine"


@dataclass(frozen=True)
class DiscordConfig:
    token: str | None
    channel_id: int | None
    character_limit: int
    history_limit: int


@dataclass(frozen=True)
class HttpConfig:
    host: str
    port: int
    enabled: bool


@dataclass(frozen=True)
class VaultConfig:
    embedding_model: str
    directory: Path


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    model: str | None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineConfig:
    cwd: Path
    data_dir: Path
    provider: ProviderConfig
    vault: VaultConfig
    discord: DiscordConfig
    http: HttpConfig
    log_level: str

    @property
    def database_path(self) -> Path:
        return self.data_dir / "agent-engine.db"


_DEFAULTS: dict[str, Any] = {
    "provider": {"name": "claude", "model": None, "options": {}},
    "vault": {"embedding_model": "all-MiniLM-L6-v2"},
    "discord": {"token": None, "channel_id": None, "character_limit": 2000, "history_limit": 50},
    "http": {"host": "127.0.0.1", "port": 8938, "enabled": True},
    "log_level": "INFO",
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text()
    data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Config at {path} must be a mapping at the top level.")
    return data


def _env_overrides() -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    token = os.environ.get("AGENT_ENGINE_DISCORD_TOKEN")
    if token:
        overrides.setdefault("discord", {})["token"] = token
    channel = os.environ.get("AGENT_ENGINE_DISCORD_CHANNEL_ID")
    if channel:
        overrides.setdefault("discord", {})["channel_id"] = int(channel)
    port = os.environ.get("AGENT_ENGINE_HTTP_PORT")
    if port:
        overrides.setdefault("http", {})["port"] = int(port)
    log_level = os.environ.get("AGENT_ENGINE_LOG_LEVEL")
    if log_level:
        overrides["log_level"] = log_level
    return overrides


def load_config(cwd: Path | str, data_dir: Path | str | None = None) -> EngineConfig:
    cwd_path = Path(cwd).resolve()
    if not cwd_path.is_dir():
        raise FileNotFoundError(f"cwd does not exist: {cwd_path}")

    home = Path.home()
    data_dir_path = Path(data_dir).resolve() if data_dir else home / ".agent-engine"

    config_path = data_dir_path / "config.yaml"

    merged = _merge(_DEFAULTS, _load_yaml(config_path))
    merged = _merge(merged, _env_overrides())

    provider_raw = merged["provider"]
    provider = ProviderConfig(
        name=provider_raw["name"],
        model=provider_raw.get("model"),
        options=provider_raw.get("options", {}) or {},
    )

    vault_directory_raw = merged["vault"].get("directory")
    vault_directory = Path(vault_directory_raw).resolve() if vault_directory_raw else data_dir_path

    vault = VaultConfig(
        embedding_model=merged["vault"]["embedding_model"],
        directory=vault_directory,
    )

    discord_raw = merged["discord"]
    discord = DiscordConfig(
        token=discord_raw.get("token"),
        channel_id=(
            int(discord_raw["channel_id"])
            if discord_raw.get("channel_id") is not None
            else None
        ),
        character_limit=int(discord_raw["character_limit"]),
        history_limit=int(discord_raw["history_limit"]),
    )

    http_raw = merged["http"]
    http = HttpConfig(
        host=http_raw["host"],
        port=int(http_raw["port"]),
        enabled=bool(http_raw["enabled"]),
    )

    return EngineConfig(
        cwd=cwd_path,
        data_dir=data_dir_path,
        provider=provider,
        vault=vault,
        discord=discord,
        http=http,
        log_level=str(merged["log_level"]),
    )
