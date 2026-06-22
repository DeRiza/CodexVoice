from pathlib import Path

from codexvoice.app import _config_path_from_args, _hotkey_from_args


def test_config_path_from_args_uses_explicit_path() -> None:
    assert _config_path_from_args(["--config", "custom.yaml"]) == Path("custom.yaml")


def test_config_path_from_args_returns_none_without_explicit_path() -> None:
    assert _config_path_from_args([]) is None


def test_hotkey_from_args_reads_next_value() -> None:
    assert _hotkey_from_args(["--set-hotkey", "option+space"]) == "option+space"


def test_hotkey_from_args_returns_none_when_absent() -> None:
    assert _hotkey_from_args([]) is None

