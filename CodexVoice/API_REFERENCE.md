# CodexVoice API Reference

> 版本: v0.3.0 MVP foundation  
> 日期: 2026-06-23  
> 状态: 与当前 `src/codexvoice` 源码同步

---

## 说明

本文件记录当前公开接口。后续修改 public class/function/method 时必须同步更新。

当前已实现 core、audio、injection、transcriber 适配层、macOS 菜单栏 UI 和原生声波浮窗；多 App 矩阵、长句、异常路径和打包仍待验收。

---

## `src/codexvoice/types.py`

### 枚举

| 名称 | 值 | 说明 |
|------|----|------|
| `SessionState` | `IDLE`, `RECORDING`, `PROCESSING`, `INJECTING`, `ERROR` | 语音 session 状态 |
| `StopReason` | `MANUAL`, `NO_SPEECH`, `SILENCE`, `MAX_DURATION` | 停止原因 |
| `PermissionState` | `GRANTED`, `DENIED`, `UNKNOWN`, `UNSUPPORTED` | 权限状态 |

### 数据结构和异常

| 名称 | 签名/字段 | 说明 |
|------|-----------|------|
| `CodexVoiceError` | `Exception` | 可恢复错误基类 |
| `TranscriberUnavailable` | `CodexVoiceError` | 本地转录引擎不可用 |
| `AudioDeviceError` | `CodexVoiceError` | 麦克风不可用 |
| `AudioBuffer` | `(pcm: bytes, sample_rate: int, channels: int, duration_sec: float)` | 内存 PCM 音频 |
| `AudioBuffer.is_empty` | `property -> bool` | 是否为空音频 |
| `Transcript` | `(text: str, language: str | None, duration_sec: float, model: str)` | 转录结果 |
| `InjectionResult` | `(ok: bool, method: str, error: str | None = None)` | 注入结果 |
| `PermissionStatus` | `(name: str, state: PermissionState, message: str, can_request: bool = False)` | 权限检查结果 |

---

## `src/codexvoice/config.py`

### 配置 dataclass

| 名称 | 主要字段 | 说明 |
|------|----------|------|
| `RecordingConfig` | `sample_rate=16000`, `channels=1`, `frame_ms=20`, `pre_speech_timeout_sec=8.0`, `post_speech_silence_sec=1.2`, `max_duration_sec=60.0`, `speech_threshold=0.015` | 录音和停止规则 |
| `TranscriptionConfig` | `engine="auto"`, `language="zh"`, `model="small"` | 本地转录 |
| `InjectionConfig` | `method="clipboard"`, `restore_clipboard=True`, `paste_delay_ms=80` | 文本注入 |
| `UIConfig` | `show_overlay=True` | UI 开关 |
| `LoggingConfig` | `level="INFO"` | 日志级别 |
| `AppConfig` | `hotkey`, `recording`, `transcription`, `injection`, `ui`, `logging` | 总配置 |

### 函数

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `default_user_config_path()` | `() -> Path` | - | `Path` | 用户配置路径 `~/Library/Application Support/CodexVoice/config.yaml` |
| `default_config()` | `() -> AppConfig` | - | `AppConfig` | 返回默认配置 |
| `load_config()` | `(path: Path | str | None = None) -> AppConfig` | `path`: JSON/TOML/YAML 配置路径 | `AppConfig` | 加载、合并、校验配置 |
| `save_config()` | `(config: AppConfig, path: Path | str) -> None` | `config`: 配置；`path`: 保存路径 | - | 保存 JSON 或 YAML 配置 |
| `validate_config()` | `(config: AppConfig) -> None` | `config`: 配置 | - | 校验范围；失败抛 `ValueError` |

---

## `src/codexvoice/app.py`

### Protocol seams

| 名称 | 方法/签名 | 输入格式 | 输出格式 | 说明 |
|------|-----------|----------|----------|------|
| `RecorderProtocol` | `start() -> None`, `stop() -> AudioBuffer`, `cancel() -> None`, `is_recording() -> bool` | 录音控制调用 | `AudioBuffer`、录音状态 | 录音 adapter seam；当前实现为 `AudioRecorder` |
| `TranscriberProtocol` | `transcribe(audio: AudioBuffer, prompt: str | None = None) -> Transcript` | 内存 PCM `AudioBuffer`、可选 prompt | `Transcript` | 转录 adapter seam；当前实现为 faster-whisper/fake |
| `InjectorProtocol` | `inject(text: str) -> InjectionResult` | 非空文本 `str` | `InjectionResult` | 文本注入 adapter seam；当前实现为剪贴板注入 |
| `OverlayProtocol` | `show(state)`, `hide()`, `set_state(state)`, `set_level(level)` | `SessionState`、`level: 0.0-1.0` | UI 副作用，无返回值 | UI overlay seam；实现内部负责 AppKit 主线程调度 |

### `VoiceSessionController`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `__init__()` | `(config: AppConfig, recorder, transcriber, injector, overlay=None, logger=None) -> None` | 依赖注入对象 | - | 创建 session 控制器 |
| `toggle()` | `() -> None` | - | - | IDLE/ERROR 时开始录音，RECORDING 时停止处理；可恢复 session 异常会记录日志并进入 ERROR，不向 AppKit 热键回调传播；ERROR 约 3 秒后自动回到 IDLE |
| `start_recording()` | `() -> None` | - | - | 开始录音；状态冲突抛 `BusyError`；麦克风启动失败时记录日志并进入 ERROR，约 3 秒后自动恢复 IDLE |
| `stop_and_process()` | `(reason: StopReason = StopReason.MANUAL) -> None` | `reason`: 停止原因 | - | 停止录音、转录、注入；处理失败时记录日志并进入 ERROR，约 3 秒后自动恢复 IDLE |
| `cancel()` | `() -> None` | - | - | 取消当前 session |
| `state()` | `() -> SessionState` | - | `SessionState` | 当前状态 |

### 其他

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `main()` | `(argv: Sequence[str] | None = None) -> int` | `--check`, `--config PATH`, `--set-hotkey HOTKEY` | exit code | CLI/App 入口 |
| `BusyError` | `RuntimeError` | - | - | session 状态冲突 |
| `NullOverlay` | `show/hide/set_state/set_level` | - | - | 无 UI overlay 实现 |

---

## `src/codexvoice/logging_setup.py`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `default_log_dir()` | `() -> Path` | - | `Path` | 默认日志目录 |
| `setup_logging()` | `(config: LoggingConfig, log_dir: Path | None = None) -> logging.Logger` | `config`: 日志配置；`log_dir`: 可选目录 | `Logger` | 配置文件和控制台日志 |

---

## `src/codexvoice/runtime_lock.py`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `default_lock_path()` | `() -> Path` | - | `Path` | 默认单实例锁路径 |
| `SingleInstanceLock.__init__()` | `(path: Path | None = None) -> None` | `path`: 可选锁文件路径 | - | 初始化文件锁 |
| `SingleInstanceLock.acquire()` | `() -> bool` | - | `bool` | 非阻塞获取锁 |
| `SingleInstanceLock.release()` | `() -> None` | - | - | 释放锁 |
| `SingleInstanceLock.__enter__()` | `() -> SingleInstanceLock` | - | `SingleInstanceLock` | 上下文管理 |
| `SingleInstanceLock.__exit__()` | `(exc_type, exc, tb) -> None` | 异常上下文 | - | 上下文退出释放锁 |

---

## `src/codexvoice/audio/vad.py`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `rms_level()` | `(pcm_frame: bytes) -> float` | `pcm_frame`: 16-bit PCM | `0.0-1.0` | 计算音量 |
| `WEBRTC_ENERGY_GATE` | `0.003` | - | `float` | WebRTC VAD 前置 RMS gate，低于该值直接判定为静音 |
| `is_speech_frame()` | `(pcm_frame: bytes, sample_rate: int, energy_threshold: float = 0.015) -> bool` | PCM、采样率、能量阈值 | `bool` | 优先用 0.003 RMS gate 过滤低音量假阳性，再调用 WebRTC VAD；缺失 WebRTC 时用能量阈值 |

### `StopRuleTracker`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `__init__()` | `(config: RecordingConfig) -> None` | `config`: 录音配置 | - | 初始化停止规则 |
| `reset()` | `(now: float) -> None` | `now`: 单调时钟秒 | - | 重置状态 |
| `update()` | `(is_speech: bool, now: float) -> StopReason | None` | 当前帧是否人声、当前时间 | 停止原因或 `None` | 判断是否触发停止 |

---

## `src/codexvoice/audio/recorder.py`

### `AudioRecorder`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `__init__()` | `(config: RecordingConfig, on_level=None, on_auto_stop=None) -> None` | `on_level(float)`, `on_auto_stop(StopReason)` | - | 初始化录音器 |
| `start()` | `() -> None` | - | - | 打开 `sounddevice.RawInputStream`；缺依赖抛 `RuntimeError`；无可用麦克风抛 `AudioDeviceError`；每次启动会重新枚举输入设备，优先默认输入，默认输入不可用或打开失败时尝试其他可用输入；启动失败后清理半初始化 stream，并 best-effort 重新初始化 sounddevice/PortAudio 设备状态；session controller 会替换 recorder，下一次重试使用新 recorder |
| `stop()` | `() -> AudioBuffer` | - | `AudioBuffer` | 停止并返回内存 PCM |
| `cancel()` | `() -> None` | - | - | 停止并丢弃音频 |
| `is_recording()` | `() -> bool` | - | `bool` | 是否录音中 |
| `current_level()` | `() -> float` | - | `float` | 当前音量 |

---

## `src/codexvoice/injection/clipboard.py`

### Protocols

| 名称 | 方法 | 说明 |
|------|------|------|
| `ClipboardBackend` | `available()`, `read()`, `write(text)` | 剪贴板后端 |
| `PasteRunner` | `available()`, `paste(delay_sec)` | 粘贴动作 |

### Classes

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `MacClipboardBackend.available()` | `() -> bool` | - | `bool` | `pbcopy/pbpaste` 是否可用 |
| `MacClipboardBackend.read()` | `() -> str` | - | `str` | 读取剪贴板 |
| `MacClipboardBackend.write()` | `(text: str) -> None` | `text`: 文本 | - | 写入剪贴板 |
| `AppleScriptPasteRunner.available()` | `() -> bool` | - | `bool` | `osascript` 是否可用 |
| `AppleScriptPasteRunner.paste()` | `(delay_sec: float) -> None` | 延迟秒数 | - | 发送 Cmd+V |
| `ClipboardInjector.__init__()` | `(config: InjectionConfig, clipboard=None, paste_runner=None, logger=None) -> None` | 可注入 fake backend | - | 创建注入器 |
| `ClipboardInjector.can_inject()` | `() -> bool` | - | `bool` | 当前环境是否可注入 |
| `ClipboardInjector.inject()` | `(text: str) -> InjectionResult` | `text`: 文本 | `InjectionResult` | 写剪贴板、粘贴、恢复 |

---

## `src/codexvoice/transcriber/`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `create_transcriber()` | `(config: TranscriptionConfig) -> LocalTranscriber` | 转录配置 | 转录器 | `fake` 或 `faster-whisper` |
| `normalize_transcript()` | `(text: str, language: str | None = "zh") -> str` | 原始文本、语言 | `str` | 简繁统一、中文标点归一化、保留英文空格、清理中文内部空格、长中文句末补句号 |

### `corrections.py`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `PhraseCorrection` | `(wrong: str, correct: str, note: str = "")` | 错误短语、修正短语、说明 | - | 带说明的短语纠错规则 |
| `DEFAULT_PHRASE_CORRECTIONS` | `tuple[PhraseCorrection, ...]` | - | - | 内置高置信长上下文短语纠错表 |
| `apply_default_phrase_corrections()` | `(text: str) -> tuple[str, int]` | 文本 | 修正后文本、替换次数 | 应用默认短语纠错 |
| `apply_phrase_corrections()` | `(text: str, rules: Mapping[str, str] | Iterable[PhraseCorrection]) -> tuple[str, int]` | 文本、规则 | 修正后文本、替换次数 | 应用自定义短语纠错；跳过单字规则并按长短语优先 |

### `LocalTranscriber`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `transcribe()` | `(audio: AudioBuffer, prompt: str | None = None) -> Transcript` | 内存 PCM、可选 prompt | `Transcript` | 本地转录协议 |
| `warmup()` | `() -> None` | - | - | 模型预热协议 |

### `FasterWhisperTranscriber`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `__init__()` | `(config: TranscriptionConfig) -> None` | 配置 | - | 延迟加载模型 |
| `warmup()` | `() -> None` | - | - | 加载模型 |
| `transcribe()` | `(audio: AudioBuffer, prompt: str | None = None) -> Transcript` | 内存 PCM | `Transcript` | 使用 faster-whisper 转录，不写临时文件 |

### `FakeTranscriber`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `__init__()` | `(config: TranscriptionConfig, text: str = "测试文本") -> None` | 配置、固定文本 | - | 测试转录器 |
| `warmup()` | `() -> None` | - | - | no-op |
| `transcribe()` | `(audio: AudioBuffer, prompt: str | None = None) -> Transcript` | 音频、prompt | `Transcript` | 返回固定文本 |

---

## `src/codexvoice/hotkey.py`

### `HotkeyManager`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `__init__()` | `(hotkey: str, on_toggle: Callable[[], None]) -> None` | 热键、toggle 回调 | - | 初始化 |
| `register()` | `() -> None` | - | - | 注册 AppKit key-down 或 flags-changed monitor；缺 PyObjC 抛 `RuntimeError` |
| `unregister()` | `() -> None` | - | - | 移除 monitor |
| `set_hotkey()` | `(hotkey: str) -> None` | 新热键 | - | 更新热键 |

---

## `src/codexvoice/permissions.py`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `check_microphone_permission()` | `() -> PermissionStatus` | - | `PermissionStatus` | 检查麦克风权限 |
| `check_accessibility_permission()` | `() -> PermissionStatus` | - | `PermissionStatus` | 检查辅助功能权限 |
| `open_privacy_settings()` | `(pane: str) -> None` | `microphone` 或 `accessibility` | - | 打开系统设置 |

---

## `src/codexvoice/ui/`

### `OverlayController`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `__init__()` | `(enabled: bool = True) -> None` | 是否启用 | - | 初始化可降级的原生 overlay 控制器 |
| `show()` | `(state: SessionState) -> None` | 状态 | - | 显示浮窗并进入指定状态；内部负责 AppKit 主线程调度 |
| `hide()` | `() -> None` | - | - | 隐藏浮窗并停止动画 |
| `set_state()` | `(state: SessionState) -> None` | 状态 | - | 更新 idle/recording/processing/injecting/error 状态 |
| `set_level()` | `(level: float) -> None` | 0.0-1.0 | - | 保存音量值；可从音频线程调用，不直接操作 AppKit |

线程约束：`show()`、`hide()`、`set_state()` 和 `set_level()` 可以由 session/音频回调路径调用；`OverlayController` 内部负责把 AppKit 操作调度回主线程，调用方不得直接操作 AppKit view/window。

### `StatusItemApp`

| 函数/方法 | 签名 | 参数 | 返回值 | 说明 |
|-----------|------|------|--------|------|
| `__init__()` | `(on_quit: Callable[[], None]) -> None` | 退出回调 | - | 初始化菜单栏 App |
| `run()` | `() -> None` | - | - | 启动 AppKit run loop；缺 PyObjC 抛 `RuntimeError` |
| `set_state()` | `(state: SessionState) -> None` | 状态 | - | 更新菜单栏标题 |
| `show_error()` | `(message: str) -> None` | 错误消息 | - | 标记错误状态 |

---

## 测试状态

- `tests/test_app.py`
- `tests/test_cli.py`
- `tests/test_config.py`
- `tests/test_corrections.py`
- `tests/test_hotkey.py`
- `tests/test_injection.py`
- `tests/test_normalize.py`
- `tests/test_overlay.py`
- `tests/test_recorder.py`
- `tests/test_runtime_lock.py`
- `tests/test_vad_rules.py`

当前验证：`70 passed`。
