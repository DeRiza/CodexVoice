# Changelog

所有重要变更记录在此文件中。

格式参考 Keep a Changelog，但本项目在 v3.0 reset 后以“真实状态优先”为原则：未实现功能不得写成已发布功能。

---

## [v3.0.0-reset] - 2026-06-22

### Added

- 创建 Python src-layout 包骨架：`src/codexvoice`。
- 新增 `pyproject.toml` 和 `config.example.yaml`。
- 实现 dataclass 配置系统、日志初始化、共享类型。
- 实现 `VoiceSessionController`：toggle/start/stop/process/cancel 状态机。
- 实现内存 PCM `AudioRecorder` 骨架和 `StopRuleTracker`。
- 实现剪贴板注入器，支持 fake backend 单元测试。
- 实现 faster-whisper 转录适配层，使用内存 PCM，不要求临时音频路径。
- 实现 macOS hotkey、permissions、status item、overlay 的保守骨架。
- 新增并持续扩展单元测试，覆盖配置、停止规则、注入和 session 状态机。
- 新增单实例文件锁，防止多个 CodexVoice 同时抢全局热键。
- 新增转录、注入和总处理耗时日志。
- 录音依赖改为 `start()` 时按需导入，避免安装依赖后旧进程仍持有 stale import 状态。
- 新增单实例锁测试。
- 新增低风险准确率后处理：繁体转简体、中文标点归一化、长中文句末补句号。
- 新增 `tests/test_normalize.py`。
- 新增短语级纠错后处理，覆盖故事测试中出现的高置信同音/近音错误。
- 新增 `tests/test_corrections.py`。
- 短语纠错规则重构为 `PhraseCorrection`，优先长上下文规则，并增加误伤防护测试。
- 新增用户配置路径 `~/Library/Application Support/CodexVoice/config.yaml`。
- 新增 `--set-hotkey HOTKEY`，支持用命令修改快捷键。
- 热键匹配支持方向键和纯修饰键组合，当前用户配置已切换为 `shift+cmd`。
- 中英文混合 normalize 改为保留英文单词空格，仅清理中文字符之间的空格。
- WebRTC VAD 前新增 0.003 RMS energy gate，低于该值直接判定为静音，减少环境噪声假阳性导致的自动停止失效，并降低轻声输入误判为 no_speech 的风险。
- 新增顶部居中的原生 AppKit 声波浮窗：录音中显示无背景动态声波和约 10% 透明度跟随阴影，处理中先收缩过渡再显示圆点 loading，成功/错误使用状态色反馈。
- 新增 `docs/overlay-ui-implementation-brief.md`，记录浮窗位置、尺寸、主线程和验收约束。
- 新增 `tests/test_overlay.py` 覆盖浮窗 geometry、动画上限和 no-op interface。
- 文档同步：补齐 `app.py` Protocol seam 的输入/输出契约，更新架构目录测试列表和 overlay 线程约束。

### Verified

- `.venv/bin/python -m pytest`：51 passed。
- 当前用户配置热键已设置为 `shift+cmd`。
- `.venv/bin/python -m compileall src tests`：通过。
- `.venv/bin/python -m codexvoice --check`：通过。
- 真实运行 smoke：用户确认热键语音输入可以成功转文字，速度体感较快。
- 单实例验证：第二个 `python -m codexvoice` 会以 exit code 3 退出并提示已有实例运行。

### Known Gaps

- 已安装并验证真实 audio/transcribe/ui extras 可启动。
- 尚未完成多 App、长句、异常路径和打包验收。
- 菜单栏和浮窗仍是保守骨架，未做视觉 polish。

### Changed

- 项目进入重建阶段，旧实现代码、虚拟环境、构建产物和历史副本已删除。
- 产品方向从“大而全的 macOS 听写替代品”收敛为“稳定可运行的本地语音输入 MVP”。
- MVP 范围明确为：菜单栏应用、toggle 热键、录音、本地转录、剪贴板注入、基础浮窗和错误提示。
- 默认热键行为统一为 `Cmd+Shift+Space` toggle，不再同时描述“按住说话、松开结束”。
- 默认文本注入方式改为剪贴板粘贴并恢复剪贴板，稳定性优先。
- 停止规则统一为手动停止、说话前超时、说话后静音停止、硬上限四类。
- README、PRD、ARCHITECTURE、API_REFERENCE 改为重建阶段文档。

### Removed From MVP

- Qwen 0.5B 语义标点。
- 个人词库、jieba、SQLite、TF-IDF。
- 流式增量注入。
- 编辑不中断。
- Fn 键触发。
- OpenAI API 代理、证书、PF 转发、hosts 修改。
- PyQt 多页设置面板作为第一版架构。
- Apple ANE 加速承诺。

### Documentation

- `CodexVoice-PRD.md` 重写为 v3.0 reset PRD。
- `AGENTS.md` 重写为重建阶段 PM/Worker 指引。
- `README.md` 改为当前 MVP foundation 状态和运行说明。
- `ARCHITECTURE.md` 重写为目标架构。
- `API_REFERENCE.md` 重写为当前源码接口表。
- `docs/streaming-transcription-design.md` 改为后续阶段设计，不属于 MVP。

---

## Superseded History

v1.x 和 v2.x 文档曾描述过 HTTPS 代理、PF、PyQt UI、Qwen 标点、个人词库、流式注入等方案。这些内容已被 v3.0 reset 取代，不再代表当前项目目标或已实现能力。

旧历史只作为背景参考，不作为实现依据。
