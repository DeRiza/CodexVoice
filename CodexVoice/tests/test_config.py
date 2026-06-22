from pathlib import Path

import pytest

from codexvoice.config import default_config, default_user_config_path, load_config, save_config, validate_config


def test_default_config_is_valid() -> None:
    config = default_config()

    validate_config(config)

    assert config.hotkey == "cmd+shift+space"
    assert config.recording.sample_rate == 16000
    assert config.injection.method == "clipboard"


def test_load_json_config_merges_with_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        '{"recording": {"post_speech_silence_sec": 2.0}, "transcription": {"model": "medium"}}',
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.recording.post_speech_silence_sec == 2.0
    assert config.recording.sample_rate == 16000
    assert config.transcription.model == "medium"


def test_unknown_config_key_fails(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"unknown": true}', encoding="utf-8")

    with pytest.raises(ValueError, match="Unknown config key"):
        load_config(path)


def test_invalid_config_type_fails(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"recording": {"sample_rate": "16000"}}', encoding="utf-8")

    with pytest.raises(ValueError, match="sample_rate"):
        load_config(path)


def test_invalid_silence_timeout_fails() -> None:
    config = default_config()
    config.recording.post_speech_silence_sec = 30.0

    with pytest.raises(ValueError, match="post_speech_silence_sec"):
        validate_config(config)


def test_save_and_load_yaml_config(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    config = default_config()
    config.transcription.model = "small"

    save_config(config, path)
    loaded = load_config(path)

    assert loaded.transcription.model == "small"


def test_default_user_config_path_points_to_codexvoice_config() -> None:
    path = default_user_config_path()

    assert path.name == "config.yaml"
    assert "CodexVoice" in str(path)
