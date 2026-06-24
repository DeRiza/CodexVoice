# CodexVoice Architecture

> 版本: v3.0-reset  
> 日期: 2026-06-22  
> 状态: MVP core 已实现，真实端到端运行待验收

---

## 1. 当前实现状态

当前已经创建 `src/codexvoice` Python 包，并实现以下 core 模块：

- `config.py`：dataclass 配置加载、保存、校验。
- `types.py`：共享数据结构、状态枚举、异常。
- `app.py`：`VoiceSessionController` 状态机和启动装配入口。
- `audio/`：内存 PCM 录音骨架、RMS、停止规则。
- `injection/`：剪贴板注入器，可 fake 测试。
- `transcriber/`：faster-whisper 内存 PCM 适配层和 fake 测试引擎。
- `hotkey.py`、`permissions.py`、`ui/`：macOS 运行所需的热键、权限、菜单栏和原生声波浮窗。

已验证：

- 单元测试 70 个通过。
- `python -m codexvoice --check` 通过。
- 真实热键语音输入 smoke 已由用户确认成功，转文字速度体感较快。
- 尚未完成多 App、长句、异常路径和打包验收。

---

## 2. 架构目标

CodexVoice v3 的架构目标是用尽量少的模块交付稳定的 macOS 本地语音输入闭环：

```
Hotkey -> Record PCM -> Local Whisper -> Normalize Text -> Paste -> Restore Clipboard
```

旧版本中的 HTTPS 代理、PF、证书、PyQt 多页 UI、Qwen 标点、个人词库和流式增量注入都不属于 MVP 架构。

---

## 3. 运行时模型

MVP 使用单进程应用：

- 主线程：macOS AppKit run loop、菜单栏、浮窗、热键回调调度。
- 音频回调线程：采集 PCM，计算音量和 VAD 状态。
- 转录工作线程：调用本地模型，避免阻塞主线程。

不引入 asyncio，不引入后台 daemon，不引入 LaunchAgent 常驻。

---

## 4. 当前目录结构

```
CodexVoice/
  pyproject.toml
  config.example.yaml
  src/codexvoice/
    __init__.py
    __main__.py
    app.py
    config.py
    logging_setup.py
    hotkey.py
    permissions.py
    types.py
    audio/
      __init__.py
      recorder.py
      vad.py
    transcriber/
      __init__.py
      base.py
      fake.py
      faster_whisper_engine.py
      normalize.py
    injection/
      __init__.py
      clipboard.py
    ui/
      __init__.py
      status_item.py
      overlay.py
  tests/
    test_app.py
    test_cli.py
    test_config.py
    test_corrections.py
    test_hotkey.py
    test_injection.py
    test_normalize.py
    test_overlay.py
    test_recorder.py
    test_runtime_lock.py
    test_vad_rules.py
  docs/
    overlay-ui-implementation-brief.md
    waveform-motion-design.md
    streaming-transcription-design.md
```

MVP 中仍不得新增与 Qwen、词库、代理或流式增量注入相关的模块。

---

## 5. 数据流

### 4.1 正常路径

```
用户按热键
  -> HotkeyManager 调用 VoiceSessionController.toggle()
  -> AudioRecorder.start()
  -> Overlay 显示 recording
  -> 用户再次按热键
  -> AudioRecorder.stop() 返回 AudioBuffer
  -> Overlay 显示 processing
  -> LocalTranscriber.transcribe(AudioBuffer)
  -> normalize_transcript()
  -> ClipboardInjector.inject(text)
  -> Overlay 显示 idle 或 error
```

### 4.2 静音自动停止

```
AudioRecorder 检测到已说话
  -> 连续静音超过 post_speech_silence_sec
  -> 触发 StopReason.SILENCE
  -> 进入同一条 stop -> transcribe -> inject 流程
```

### 4.3 错误路径

```
权限缺失 / 麦克风不可用 / 模型不可用 / 注入失败
  -> 返回结构化错误
  -> 日志记录
  -> UI 显示 error
  -> session 进入 ERROR 并保留约 3 秒
  -> 3 秒后自动回到 IDLE，避免麦克风恢复后仍卡在错误状态
  -> 不注入空文本或乱码
```

---

## 6. 模块职责

### 5.1 `app.py`

应用编排层。负责：

- 初始化配置、日志、权限检查、UI、热键、录音、转录、注入。
- 管理录音 session 状态。
- 保证同一时刻只有一个录音或转录任务。
- 处理错误并更新 UI。

### 5.2 `config.py`

配置层。负责：

- 加载默认配置。
- 合并用户配置。
- 校验取值范围。
- 提供 dataclass 或等价结构给其他模块。

### 5.3 `hotkey.py`

全局热键层。负责：

- 注册 `Cmd+Shift+Space` 等键盘热键，支持方向键和 `shift+cmd` 这类纯修饰键组合。
- 将系统事件转换为一次 `on_toggle()` 回调。
- 注销热键。

MVP 不支持 Fn 键，不支持按住松开模式。

### 5.4 `audio/recorder.py`

录音层。负责：

- 优先打开当前默认输入设备；如果默认输入不可用或打开失败，重新枚举并尝试其他可用输入设备。
- 采集 16kHz mono 16-bit PCM。
- 维护内存 buffer。
- 提供当前音量。
- 根据 VAD 和时间规则触发停止回调。
- 输入流启动失败后由 session controller 废弃当前 `AudioRecorder` 实例；下一次录音前使用新建 recorder，回到接近应用初始启动的音频运行时状态。
- 每次开始录音前会查询当前输入设备；输入流启动失败后会 best-effort 重新初始化 sounddevice/PortAudio，并在同次或下次重试时显式选择可用输入设备，避免无麦克风报错后新接入麦克风仍持续失败。

禁止写临时音频文件。

### 5.5 `audio/vad.py`

轻量语音活动检测。负责：

- 判断 PCM frame 是否有人声。
- 在 WebRTC VAD 前使用 0.003 RMS energy gate 过滤低音量环境噪声假阳性。
- 维护“是否已经说过话”的状态。
- 支持 pre-speech timeout、post-speech silence、max duration 三类边界。

### 5.6 `transcriber/`

本地转录层。负责：

- 定义统一 `LocalTranscriber` 接口。
- 将内存 PCM 转为模型可接受输入。
- 返回结构化 `Transcript`。
- 做最小文本清理。

实现优先级：

1. Apple Silicon 上评估 `mlx-whisper`。
2. 如 MLX 阻塞，则使用 `faster-whisper` 作为稳定基线。

不允许为了调用模型把音频写入 `NamedTemporaryFile(delete=False)` 之类的临时文件。

### 5.7 `injection/clipboard.py`

文本注入层。负责：

- 保存当前剪贴板内容。
- 写入转录文本。
- 触发 `Cmd+V`。
- 等待目标 App 接收粘贴。
- 尽力恢复原剪贴板。
- 返回注入是否成功。

CGEvent 逐字注入不属于 MVP 默认路径。

### 5.8 `ui/`

macOS UI 层。负责：

- 菜单栏状态项。
- 退出菜单。
- 顶部居中、菜单栏下方的原生 AppKit `NSPanel` 声波浮窗，窗口透明且不显示外层胶囊背景。
- 录音中显示 5 色 × 100 细线 Siri-style waveform：每色使用 `CAReplicatorLayer` 生成 99 根指数递减线，并叠加 1 条 centerline；overlay 内部 `WaveMotionModel` 把 RMS 映射为 `voice_intensity`，无声时保持基础呼吸幅度 1.0，有声时最多增强到 1.3，动画以 60fps 快起慢落跟随输入；处理中先收缩过渡，再显示不含文字内容的圆点 loading。
- 录音开始播放系统提示音 `Tink`，录音结束进入 processing 时播放系统提示音 `Pop`；提示音来自 macOS `/System/Library/Sounds`，播放前会重置同名 sound 以提升短时间连续触发可靠性。
- 声波动效实现说明记录在 `docs/waveform-motion-design.md`；该方案只改变 overlay 视觉层，不改变音频、VAD、转录或注入模块。
- 状态更新：idle、recording、processing、injecting、error。
- AppKit 操作必须回到主线程；音频线程只写入 level 值，不直接操作 UI。

MVP 不做复杂设置面板。

### 5.9 `permissions.py`

权限层。负责：

- 检查麦克风权限。
- 检查辅助功能权限。
- 提供用户可理解的错误消息。

---

## 7. 状态机

```
IDLE
  | hotkey
  v
RECORDING
  | hotkey / silence / no_speech_timeout / max_duration
  v
PROCESSING
  | transcript ok
  v
INJECTING
  | inject ok
  v
IDLE

任何状态
  | unrecoverable error
  v
ERROR -> IDLE
```

关键约束：

- `RECORDING` 时再次触发热键只停止当前 session，不启动新 session。
- `PROCESSING` 和 `INJECTING` 时忽略新的热键或显示 busy。
- 空文本不注入。
- 麦克风、转录或注入异常不应穿透 AppKit 热键回调；controller 记录日志、进入 `ERROR`，约 3 秒后自动回到 `IDLE`，后续热键可重试。

---

## 8. 配置边界

MVP 配置只保留必要字段：

```yaml
hotkey: "cmd+shift+space"
recording:
  sample_rate: 16000
  channels: 1
  frame_ms: 20
  pre_speech_timeout_sec: 8.0
  post_speech_silence_sec: 1.2
  max_duration_sec: 60.0
transcription:
  engine: "auto"
  language: "zh"
  model: "small"
injection:
  method: "clipboard"
  restore_clipboard: true
ui:
  show_overlay: true
logging:
  level: "INFO"
```

配置键名必须和 `API_REFERENCE.md`、实现代码、未来设置 UI 保持一致。

---

## 9. 隐私和文件系统

- 音频 PCM 只存在内存中。
- 转录文本只用于注入和必要日志。
- 默认日志不得记录完整转录文本，可记录长度、耗时、错误码。
- 模型缓存可以由底层模型库管理，但必须位于用户可理解的缓存目录。
- 不创建临时音频文件。

---

## 10. 测试策略

### 9.1 自动测试

- 配置加载和范围校验。
- 文本归一化。
- VAD 停止规则。
- 注入模块的剪贴板保存/恢复逻辑可用 mock 验证。

### 9.2 手动验收

- Notes/TextEdit。
- Safari/Chrome 输入框。
- 常见聊天输入框。
- 权限缺失路径。
- 麦克风不可用路径。
- 模型缺失路径。

---

## 11. 后续扩展点

以下扩展点只能在 MVP 验收通过后启用：

- 设置面板。
- 麦克风设备选择。
- 自定义 prompt 或术语表。
- Qwen 标点。
- 流式预览。
- 增量注入。
- CGEvent 注入。
- 打包、签名、公证。

---

## 12. 已废弃架构

以下旧架构不得复用：

- 本地 HTTPS 代理拦截 OpenAI API。
- 自签证书和 PF 端口转发。
- PyQt6 作为默认 UI 框架。
- 录音后写临时 wav 再转录。
- 流式 chunk 增量注入作为第一版能力。
- Qwen/词库和主流程强耦合。
