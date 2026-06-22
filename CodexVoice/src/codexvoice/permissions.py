"""macOS permission checks with conservative fallbacks."""

from __future__ import annotations

import platform
import subprocess

from .types import PermissionState, PermissionStatus


def check_microphone_permission() -> PermissionStatus:
    if platform.system() != "Darwin":
        return PermissionStatus(
            name="microphone",
            state=PermissionState.UNSUPPORTED,
            message="Microphone permission checks are only implemented for macOS.",
        )

    try:
        import AVFoundation  # type: ignore
    except ImportError:
        return PermissionStatus(
            name="microphone",
            state=PermissionState.UNKNOWN,
            message="Install pyobjc-framework-AVFoundation to check microphone permission.",
            can_request=True,
        )

    status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(AVFoundation.AVMediaTypeAudio)
    granted = getattr(AVFoundation, "AVAuthorizationStatusAuthorized", 3)
    denied = getattr(AVFoundation, "AVAuthorizationStatusDenied", 2)
    restricted = getattr(AVFoundation, "AVAuthorizationStatusRestricted", 1)
    if status == granted:
        return PermissionStatus("microphone", PermissionState.GRANTED, "Microphone permission granted.")
    if status in {denied, restricted}:
        return PermissionStatus("microphone", PermissionState.DENIED, "Microphone permission denied.", can_request=True)
    return PermissionStatus("microphone", PermissionState.UNKNOWN, "Microphone permission has not been decided.", can_request=True)


def check_accessibility_permission() -> PermissionStatus:
    if platform.system() != "Darwin":
        return PermissionStatus(
            name="accessibility",
            state=PermissionState.UNSUPPORTED,
            message="Accessibility permission checks are only implemented for macOS.",
        )

    try:
        import Quartz  # type: ignore
    except ImportError:
        return PermissionStatus(
            name="accessibility",
            state=PermissionState.UNKNOWN,
            message="Install pyobjc-framework-Quartz to check accessibility permission.",
            can_request=True,
        )

    checker = getattr(Quartz, "AXIsProcessTrusted", None)
    if checker is None:
        return PermissionStatus(
            name="accessibility",
            state=PermissionState.UNKNOWN,
            message="PyObjC Quartz does not expose AXIsProcessTrusted on this install.",
            can_request=True,
        )

    trusted = bool(checker())
    if trusted:
        return PermissionStatus("accessibility", PermissionState.GRANTED, "Accessibility permission granted.")
    return PermissionStatus("accessibility", PermissionState.DENIED, "Accessibility permission denied.", can_request=True)


def open_privacy_settings(pane: str) -> None:
    panes = {
        "microphone": "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
        "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    }
    if pane not in panes:
        raise ValueError("pane must be microphone or accessibility")
    subprocess.Popen(["open", panes[pane]])
