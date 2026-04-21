import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

Effort = Literal["low", "medium", "high", "xhigh", "max"]
_VALID_EFFORTS: tuple[Effort, ...] = ("low", "medium", "high", "xhigh", "max")


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
    directory: Path


@dataclass(frozen=True)
class ClaudeConfig:
    model: str
    effort: Effort


@dataclass(frozen=True)
class ProvidersConfig:
    claude: ClaudeConfig | None = None

    def get(self, name: str) -> ClaudeConfig | None:
        if name == "claude":
            return self.claude
        return None

    def configured_names(self) -> tuple[str, ...]:
        names: list[str] = []
        if self.claude is not None:
            names.append("claude")
        return tuple(names)


@dataclass(frozen=True)
class EngineConfig:
    cwd: Path
    data_dir: Path
    providers: ProvidersConfig
    default_provider: str
    timezone: str
    vault: VaultConfig
    discord: DiscordConfig
    http: HttpConfig
    log_level: str

    @property
    def database_path(self) -> Path:
        return self.data_dir / "agent-engine.db"


_DEFAULTS: dict[str, Any] = {
    "providers": {
        "claude": {
            "model": "opus[1m]",
            "effort": "max",
        },
    },
    "default_provider": "claude",
    "timezone": "UTC",
    "vault": {},
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


def _build_claude_config(raw: dict[str, Any]) -> ClaudeConfig:
    model = raw.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError(
            "providers.claude.model must be a non-empty string (e.g. 'opus'); null is not permitted"
        )

    effort = raw.get("effort")
    if effort not in _VALID_EFFORTS:
        raise ValueError(
            f"providers.claude.effort must be one of {_VALID_EFFORTS}, got {effort!r}"
        )

    return ClaudeConfig(model=model, effort=effort)


def _build_providers_config(raw: dict[str, Any]) -> ProvidersConfig:
    if not isinstance(raw, dict):
        raise ValueError("providers must be a mapping")
    claude_raw = raw.get("claude")
    claude = _build_claude_config(claude_raw) if claude_raw is not None else None
    return ProvidersConfig(claude=claude)


def load_config(cwd: Path | str, data_dir: Path | str | None = None) -> EngineConfig:
    cwd_path = Path(cwd).resolve()
    if not cwd_path.is_dir():
        raise FileNotFoundError(f"cwd does not exist: {cwd_path}")

    home = Path.home()
    data_dir_path = Path(data_dir).resolve() if data_dir else home / ".agent-engine"

    config_path = data_dir_path / "config.yaml"

    merged = _merge(_DEFAULTS, _load_yaml(config_path))
    merged = _merge(merged, _env_overrides())

    providers = _build_providers_config(merged["providers"])

    default_provider = merged["default_provider"]
    if not isinstance(default_provider, str) or not default_provider:
        raise ValueError("default_provider must be a non-empty string")
    if providers.get(default_provider) is None:
        configured = providers.configured_names()
        raise ValueError(
            f"default_provider {default_provider!r} has no configuration; "
            f"configured providers: {configured}"
        )

    timezone = merged["timezone"]
    if not isinstance(timezone, str) or not timezone:
        raise ValueError("timezone must be a non-empty string")

    vault_directory_raw = merged["vault"].get("directory")
    vault_directory = Path(vault_directory_raw).resolve() if vault_directory_raw else data_dir_path

    vault = VaultConfig(directory=vault_directory)

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
        providers=providers,
        default_provider=default_provider,
        timezone=timezone,
        vault=vault,
        discord=discord,
        http=http,
        log_level=str(merged["log_level"]),
    )
