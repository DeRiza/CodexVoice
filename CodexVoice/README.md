# CodexVoice

> macOS 本地语音输入工具。目标是按下热键，说话，再按一次结束，文字稳定出现在当前光标位置。

## 当前状态

项目处于 v3.0 MVP 重建阶段。当前已经落地 Python 包骨架和可测试核心：

- 配置系统。
- 录音/VAD 停止规则，包含 WebRTC VAD 前置 0.003 RMS energy gate，用于减少低音量环境噪声导致的假人声，同时保留轻声输入余量。
- 语音 session 状态机。
- 剪贴板注入器。
- faster-whisper 内存 PCM 转录适配层。
- macOS 热键、权限、菜单栏 UI，以及顶部居中的原生声波浮窗；录音声波使用 overlay 内部 `WaveMotionModel` 驱动，当前已回退为 `CAReplicatorLayer` + centerline 的 5 色 × 100 细线版本。
- 单实例锁，防止多个 App 同时抢热键。
- 转录/注入/总处理耗时日志。
- 低风险文本后处理：繁体转简体、中文标点归一化、长中文句末补句号；中英文混合时保留英文单词空格，只清理中文字符之间的空格。
- 短语级纠错：基于高置信长上下文短语表修正常见同音/近音错误，不做全局单字替换。
- 单元测试和 `python -m codexvoice --check` 自检。

完整端到端运行仍需要安装 audio/transcribe/ui 可选依赖，并在真实 macOS 权限环境中验证。

2026-06-22 手动 smoke 结果：应用已成功启动，用户确认热键语音输入可以完成转文字，且速度体感较快。后续仍需做多 App、长句、异常路径和打包验收。

## MVP 目标

第一阶段只追求一个稳定闭环：

1. 启动 macOS 菜单栏应用。
2. 按 `Cmd+Shift+Space` 开始录音。
3. 再按一次热键停止录音。
4. 本地 Whisper 模型转录语音。
5. 将结果注入当前前台 App 的光标位置。

MVP 默认中文优先、稳定优先、少依赖优先。

## 不进入 MVP 的功能

以下功能暂缓，避免第一版再次变成难以验证的愿望清单：

- Qwen 语义标点。
- 个人词库和同音词纠错。
- 流式增量注入。
- 编辑不中断。
- Fn 键触发。
- 完整设置面板。
- OpenAI API 代理、证书、PF 转发。
- Apple ANE 加速承诺。

## 设计取舍

| 领域 | MVP 决策 | 原因 |
|------|----------|------|
| 热键 | `Cmd+Shift+Space` toggle | macOS 上比 Fn 和按住松开更可靠 |
| UI | 原生菜单栏 + 简洁浮窗 | 更符合 macOS 软件习惯，减少 UI 依赖 |
| 录音 | 16kHz mono PCM，内存处理 | Whisper 友好，避免临时文件和隐私风险 |
| 转录 | 本地 Whisper 引擎 | 音频不出本机 |
| 注入 | 剪贴板粘贴并恢复剪贴板 | 对中文和多 App 最稳定 |
| 停止 | 手动停止 + 语音后静音停止 + 硬上限 | 逻辑少，行为可解释 |

## 计划中的项目结构

```
CodexVoice/
  pyproject.toml
  config.example.yaml
  src/codexvoice/
    __main__.py
    app.py
    config.py
    hotkey.py
    permissions.py
    audio/
    transcriber/
    injection/
    ui/
  tests/
```

当前源码结构和公开接口以 [ARCHITECTURE.md](ARCHITECTURE.md) 和 [API_REFERENCE.md](API_REFERENCE.md) 为准。

## 开发启动方式

创建虚拟环境并安装测试依赖：

```bash
cd CodexVoice
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
```

运行核心自检：

```bash
.venv/bin/python -m codexvoice --check
```

修改快捷键：

`.venv/bin/python -m codexvoice --set-hotkey shift+cmd`

该命令会写入用户配置：`~/Library/Application Support/CodexVoice/config.yaml`。修改后需要重启当前 CodexVoice 实例才会生效。

运行测试：

```bash
.venv/bin/python -m pytest
```

真实语音输入运行需要额外安装：

```bash
.venv/bin/python -m pip install -e '.[audio,transcribe,ui]'
.venv/bin/python -m codexvoice
```

注意：真实运行会要求麦克风和辅助功能权限。当前源码模式下的热键、录音、转写和注入已经通过手动 smoke；打包 App 尚未验收。

## 权限

MVP 需要两类 macOS 权限：

| 权限 | 用途 |
|------|------|
| 麦克风 | 采集本地语音 |
| 辅助功能 | 全局热键和文本注入 |

实现时必须在权限缺失时给出明确提示，而不是静默失败。

## 文档

- [PRD](../CodexVoice-PRD.md)：产品目标、范围、验收标准。
- [ARCHITECTURE](ARCHITECTURE.md)：目标架构、模块边界、数据流。
- [API_REFERENCE](API_REFERENCE.md)：当前源码公开接口表。
- [CHANGELOG](CHANGELOG.md)：版本历史和 reset 记录。
- [Overlay UI Brief](docs/overlay-ui-implementation-brief.md)：顶部声波浮窗的实现约束和验收标准。
- [Waveform Motion Design](docs/waveform-motion-design.md)：当前 overlay 声波动效数据层和 5 色 × 100 细线渲染方案。
- [Streaming Design](docs/streaming-transcription-design.md)：后续阶段的流式设计，不属于 MVP。

## 许可证

待定。实现前不引入许可证假设。
