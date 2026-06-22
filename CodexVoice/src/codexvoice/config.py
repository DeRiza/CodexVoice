"""Configuration loading and validation."""

from __future__ import annotations

import json
import tomllib
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, get_args, get_origin, get_type_hints


@dataclass
class RecordingConfig:
    sample_rate: int = 16000
    channels: int = 1
    frame_ms: int = 20
    pre_speech_timeout_sec: float = 8.0
    post_speech_silence_sec: float = 1.2
    max_duration_sec: float = 60.0
    speech_threshold: float = 0.015


@dataclass
class TranscriptionConfig:
    engine: str = "auto"
    language: str | None = "zh"
    model: str = "small"


@dataclass
class InjectionConfig:
    method: str = "clipboard"
    restore_clipboard: bool = True
    paste_delay_ms: int = 80


@dataclass
class UIConfig:
    show_overlay: bool = True


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class AppConfig:
    hotkey: str = "cmd+shift+space"
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    injection: InjectionConfig = field(default_factory=InjectionConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


T = TypeVar("T")


def default_user_config_path() -> Path:
    return Path.home() / "Library" / "Application Support" / "CodexVoice" / "config.yaml"


def default_config() -> AppConfig:
    return AppConfig()


def load_config(path: Path | str | None = None) -> AppConfig:
    config = default_config()
    if path is None:
        validate_config(config)
        return config

    config_path = Path(path).expanduser()
    if not config_path.exists():
        validate_config(config)
        return config

    data = _read_config_file(config_path)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain an object: {config_path}")

    merged = _merge_dataclass(config, data)
    validate_config(merged)
    return merged


def save_config(config: AppConfig, path: Path | str) -> None:
    validate_config(config)
    config_path = Path(path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(config)
    suffix = config_path.suffix.lower()

    if suffix == ".json":
        config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return
    if suffix in {".yaml", ".yml", ""}:
        yaml = _import_yaml()
        config_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return
    raise ValueError(f"Unsupported config format for saving: {config_path.suffix}")


def validate_config(config: AppConfig) -> None:
    if not config.hotkey.strip():
        raise ValueError("hotkey must not be empty")

    recording = config.recording
    if recording.sample_rate <= 0:
        raise ValueError("recording.sample_rate must be positive")
    if recording.channels != 1:
        raise ValueError("recording.channels must be 1 for MVP")
    if recording.frame_ms not in {10, 20, 30}:
        raise ValueError("recording.frame_ms must be 10, 20, or 30")
    if recording.pre_speech_timeout_sec <= 0:
        raise ValueError("recording.pre_speech_timeout_sec must be positive")
    if not 0.8 <= recording.post_speech_silence_sec <= 3.0:
        raise ValueError("recording.post_speech_silence_sec must be between 0.8 and 3.0")
    if recording.max_duration_sec <= recording.pre_speech_timeout_sec:
        raise ValueError("recording.max_duration_sec must be greater than pre_speech_timeout_sec")
    if not 0.0 <= recording.speech_threshold <= 1.0:
        raise ValueError("recording.speech_threshold must be between 0 and 1")

    if config.transcription.engine not in {"auto", "mlx", "faster-whisper", "fake"}:
        raise ValueError("transcription.engine must be auto, mlx, faster-whisper, or fake")
    if not config.transcription.model.strip():
        raise ValueError("transcription.model must not be empty")

    if config.injection.method != "clipboard":
        raise ValueError("injection.method must be clipboard for MVP")
    if config.injection.paste_delay_ms < 0:
        raise ValueError("injection.paste_delay_ms must be non-negative")

    if config.logging.level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("logging.level is invalid")


def _read_config_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix == ".toml":
        with path.open("rb") as file:
            return tomllib.load(file)
    if suffix in {".yaml", ".yml"}:
        yaml = _import_yaml()
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        return {} if loaded is None else loaded
    raise ValueError(f"Unsupported config format: {path.suffix}")


def _import_yaml() -> Any:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency is declared.
        raise RuntimeError("YAML config requires PyYAML. Install codexvoice with its base dependencies.") from exc
    return yaml


def _merge_dataclass(instance: T, updates: dict[str, Any]) -> T:
    if not is_dataclass(instance):
        raise TypeError("instance must be a dataclass")

    values = asdict(instance)
    type_hints = get_type_hints(type(instance))
    field_defs = {field.name: field for field in fields(instance)}
    for key, value in updates.items():
        if key not in field_defs:
            raise ValueError(f"Unknown config key: {key}")

        current = getattr(instance, key)
        if is_dataclass(current):
            if not isinstance(value, dict):
                raise ValueError(f"Config section {key} must be an object")
            values[key] = _merge_dataclass(current, value)
        else:
            values[key] = value

    coerced: dict[str, Any] = {}
    for field in fields(instance):
        value = values[field.name]
        if isinstance(value, dict) and is_dataclass(getattr(instance, field.name)):
            coerced[field.name] = _dict_to_dataclass(type(getattr(instance, field.name)), value)
        else:
            coerced[field.name] = _coerce_value(value, type_hints.get(field.name, field.type), field.name)
    return type(instance)(**coerced)


def _dict_to_dataclass(cls: type[T], data: dict[str, Any]) -> T:
    allowed = {field.name: field for field in fields(cls)}
    type_hints = get_type_hints(cls)
    unknown = set(data) - set(allowed)
    if unknown:
        raise ValueError(f"Unknown config key: {', '.join(sorted(unknown))}")
    return cls(
        **{
            name: _coerce_value(data[name], type_hints.get(name, field.type), name)
            for name, field in allowed.items()
            if name in data
        }
    )


def _coerce_value(value: Any, expected_type: Any, name: str) -> Any:
    origin = get_origin(expected_type)
    args = get_args(expected_type)
    if expected_type is Any:
        return value
    if origin is None:
        if expected_type is float and isinstance(value, int):
            return float(value)
        if expected_type in {int, float, str, bool} and not isinstance(value, expected_type):
            raise ValueError(f"Config key {name} must be {expected_type.__name__}")
        return value
    if type(None) in args:
        non_none = [arg for arg in args if arg is not type(None)]
        if value is None:
            return None
        return _coerce_value(value, non_none[0], name)
    return value
