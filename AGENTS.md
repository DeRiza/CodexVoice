# AGENTS.md - CodexVoice 项目 AI 助手指引

> 版本: v3.0-mvp-foundation | 日期: 2026-06-22 | 状态: MVP Foundation/Core 已实现，端到端验收未完成

---

## 项目状态

CodexVoice 已清空旧实现代码，并开始 v3 MVP 重建。当前已完成 Python 包骨架、配置、状态机、录音/VAD 骨架、剪贴板注入器、faster-whisper 适配层、macOS UI/权限骨架和核心测试。后续实现必须以本文档、`CodexVoice-PRD.md`、`CodexVoice/ARCHITECTURE.md` 和 `CodexVoice/API_REFERENCE.md` 为准，不得复用旧 v1/v2 的代理、PyQt、流式注入、Qwen 标点或词库假设。

本阶段目标不是恢复旧代码，而是重新做一个稳定、轻量、可验证的 macOS 本地语音输入 MVP。

---

## 产品边界

### MVP 必须做到

- macOS 菜单栏应用可启动、退出、显示运行状态。
- 默认热键仍支持 `Cmd+Shift+Space` toggle；当前用户配置为 `shift+cmd`。
- 默认麦克风录音，16kHz mono PCM，全程内存处理。
- 本地 Whisper 转录，优先服务中文输入。
- 文本注入当前前台 App，MVP 默认使用剪贴板粘贴并恢复剪贴板。
- 简洁浮窗显示录音、处理中、成功、错误状态。
- 最小配置文件、日志和错误提示。

### MVP 明确不做

- Qwen 语义标点。
- 个人词库、TF-IDF、同音词纠错。
- 流式增量注入。
- 编辑不中断。
- Fn 键触发。
- 代理 OpenAI API、证书、PF、LaunchAgent 劫持。
- 声称 Apple ANE 加速。
- 完整设置面板和复杂多页 UI。

---

## PM 原则

1. **先稳定闭环，再做高级功能**：先交付热键 -> 录音 -> 本地转录 -> 注入文本的端到端路径。
2. **文档不许冒充实现**：未实现能力只能写入后续阶段，不能写成已完成功能。
3. **少依赖、少线程、少状态**：优先选择 macOS 原生能力和简单同步边界。
4. **默认稳定优先**：中文文本注入以剪贴板粘贴为默认路径，CGEvent 逐字输入只作为后续优化。
5. **源码事实优先**：当前已有 `src/`，因此 API 文档必须跟真实接口同步；后续任何签名变更都要同步文档。

---

## 当前 Agent 状态

已启动 MVP Foundation/Core。Zhen 已完成第一轮核心实现；其他 Worker 尚未正式分配。

| 代号 | 岗位 | 未来写入范围 | 当前状态 |
|------|------|--------------|----------|
| Zhen（后端工程师） | 应用编排、配置、热键、音频、注入 | `src/codexvoice/app.py`, `src/codexvoice/config.py`, `src/codexvoice/hotkey.py`, `src/codexvoice/audio/`, `src/codexvoice/injection/`, `pyproject.toml`, `config.example.yaml` | Foundation/Core 完成 |
| Galileo（算法工程师） | 本地模型、转录接口、文本归一化 | `src/codexvoice/transcriber/` | 骨架已存在，真实模型验收待分配 |
| Zeno（前端工程师） | macOS 菜单栏、浮窗、设置入口 | `src/codexvoice/ui/`, `resources/` | 骨架已存在，UI polish 待分配 |
| Mendel（系统运维） | macOS 权限、打包、签名、plist 可选项 | `packaging/`, `src/codexvoice/permissions.py` | 未分配 |
| Raman（验收员） | 集成验证、回归测试、打包验收 | `tests/`, 验收报告 | 未分配 |
| Avicenna（项目文档管理员） | PRD、README、架构、API、变更记录 | `CodexVoice-PRD.md`, `CodexVoice/*.md`, `CodexVoice/docs/*.md` | 未分配 |

---

## 实施门禁

### Gate 0 - 文档确认

- PRD 明确 MVP 和后续阶段。
- ARCHITECTURE 明确目标文件结构和数据流。
- API_REFERENCE 明确当前源码接口。
- README 不再声称当前代码可运行。
- CHANGELOG 记录 v3.0 reset。

### Gate 1 - 最小可运行骨架

- 项目可安装基础和 test 依赖。已完成。
- `python -m codexvoice --check` 可运行。已完成。
- 配置和日志可读写。已完成。
- 菜单栏 App 真实启动退出待安装 UI extras 后验收。
- 权限缺失时给出明确提示的路径已实现，待真实 macOS 权限环境验收。

### Gate 2 - 端到端 MVP

- 热键开始/停止录音。
- 停止后本地转录。
- 转录文本注入 Notes、TextEdit、浏览器输入框等常见 App。
- 不产生临时音频文件。
- 当前状态：真实语音输入 smoke 已成功；多 App 矩阵、长句、异常路径和打包尚未验收。
- VAD 补丁：WebRTC VAD 前置 0.003 RMS energy gate 已实现，用于过滤低音量环境噪声假阳性，同时减少轻声输入被误判为 no_speech 的风险。
- 稳定性补丁：单实例锁已实现并验证，转录/注入耗时日志已实现。
- 准确率补丁：简繁统一、中文标点归一化、长句末尾句号、长上下文短语级纠错已实现；禁止全局单字纠错。
- 配置补丁：支持 `--set-hotkey HOTKEY` 写入用户配置；方向键和纯修饰键热键已支持，当前实例已切换为 `shift+cmd`。

### Gate 3 - 打包和验收

- 从源码启动和打包 App 启动都通过。
- 关键错误路径可恢复。
- 文档与代码同步。

---

## 未来调度拓扑

```
Gate 0: 文档确认
   |
Wave 1: Foundation
   |-- 项目骨架、配置、日志、App 生命周期
   |
Wave 2: Core MVP
   |-- 音频录制与停止规则
   |-- 本地转录引擎
   |-- 文本注入
   |
Wave 3: macOS UX
   |-- 菜单栏、浮窗、权限提示
   |
Wave 4: QA + Packaging + Docs
   |-- 端到端验收、打包、文档同步
```

并行执行只允许发生在写入范围完全不重叠时。共享文件如 `pyproject.toml`、`config.example.yaml` 必须由 Foundation 阶段先创建，后续 Worker 追加或通过 PM 协调合并。

---

## 接口契约

所有 Worker 修改代码前必须先读：

- `CodexVoice/ARCHITECTURE.md`：模块边界和数据流。
- `CodexVoice/API_REFERENCE.md`：目标公开接口和回调签名。
- `CodexVoice-PRD.md`：MVP 范围和明确不做项。

任何 Worker 不得凭空新增跨模块接口。需要新增接口时，先向 PM 汇报，由 PM 更新契约或协调相关文档。

---

## Bug 修复流程

1. PM 定位问题归属。
2. PM 将任务发给拥有对应写入范围的 Worker。
3. Worker 只改自己范围内的文件。
4. Raman（验收员）按真实运行路径验证。
5. Avicenna（项目文档管理员）同步文档。
6. PM 汇总结论给用户。

---

## 文档纪律

- README 只描述当前状态和已确认目标。
- ARCHITECTURE 只描述目标架构和已实现架构，不保留旧代码结构。
- API_REFERENCE 在代码未实现前标记为“目标契约”；代码完成后改为真实接口引用。
- CHANGELOG 必须记录 reset、删除旧实现、范围收敛等重大变化。

---

## 已废弃历史方案

以下内容不得回流到 MVP：

- v1 HTTPS 代理、证书、PF 转发方案。
- v2 PyQt 多页设置面板优先方案。
- Qwen 0.5B 标点优先方案。
- 个人词库优先方案。
- 流式增量注入优先方案。
- “按住说话、松开结束”和 toggle 并存的热键设计。
- “静音 800ms / 2s / 30s” 多套互相冲突的停止规则。

这些能力只有在 MVP 端到端稳定、验收通过后，才能作为后续阶段重新评估。
