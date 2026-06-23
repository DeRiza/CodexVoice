# Overlay UI Implementation Brief

> 日期：2026-06-22  
> 状态：当前 overlay 实现约束，供 CodexVoice macOS 浮窗开发和验收使用

## 目标

实现一个 macOS 原生悬浮录音状态浮窗，显示在当前屏幕顶部居中、菜单栏下方。它只显示声波/圆点本体和轻量阴影，不显示外层胶囊背景；必须表达录音中、语音转文字处理中、注入中和错误状态，但不得展示最终转写文字。

## 非目标

- 不做完整设置面板。
- 不展示转写文本内容。
- 不引入 PyQt、WebView 或 SwiftUI。
- 不改变录音、转写、注入链路。
- 不让动画改变窗口尺寸。

## 声波动效实现

当前声波实现见 [Waveform Motion Design](waveform-motion-design.md)：overlay 内部 `WaveMotionModel` 负责把 RMS 映射为视觉运动，渲染层使用 `CAReplicatorLayer` + centerline 的 5 色 × 100 细线方案。新的 ribbon fill + sparse mesh 思路暂存于临时文档 `waveform-ribbon-sparse-mesh-temp.md`，尚未实现。

## 位置和尺寸

- 窗口宽度：`300px`，但窗口背景透明。
- 窗口高度：`72px`，但不显示外层圆框或胶囊底板。
- 基于 `NSScreen.visibleFrame()` 定位，不用原始屏幕 frame。
- 水平居中。
- 顶部距离 `visibleFrame.maxY` 至少 `16px`。
- 声波最大高度：`40px`。
- 声波最小高度：`6px`。
- 动画只能在固定窗口内部变化，不得向上压到菜单栏。

## macOS 窗口行为

- 使用原生 AppKit `NSPanel`。
- 无边框、透明背景，不显示圆框或胶囊底板。
- 置顶显示。
- 不成为 key window。
- 不激活应用。
- 鼠标穿透。
- 支持当前桌面 Space 和全屏辅助显示。
- AppKit view 创建、显示、隐藏和重绘必须在主线程执行。

## 状态设计

### `IDLE`

- 浮窗隐藏。

### `RECORDING`

- 浮窗显示。
- 中间显示 5 色错位彩色 Siri-style 横向 sine wave。
- 每种颜色使用 1 个 `CAReplicatorLayer` 渲染 99 根指数递减细线，并叠加 1 条 centerline，形成每色 100 根可见线。
- 声波后方显示一层约 `10%` 透明度、轻微偏移的 shadow wave，shadow 跟随声波动画同步变化。
- wave 振幅不直接使用原始 RMS，而是由 `WaveMotionModel` 映射为 `voice_intensity`：无声时保持基础呼吸幅度 `1.0`，最大声音时增强到 `1.3`。
- 动画 tick 使用 60fps；音量上升时快速响应，音量下降时慢速回落，避免抖动但增强实时感。
- `set_level()` 可能来自音频回调线程，因此不得直接操作 AppKit。

### `PROCESSING`

- 录音结束后浮窗不立刻消失。
- 声波振幅先收缩/淡出，再切换为 5 个小圆点 loading。
- 小圆点从左到右依次高亮，表示“语音转文字处理中”。
- 不展示转写文本。

## 系统提示音

- 录音成功开始后播放系统提示音 `Tink`。
- 录音结束并进入 processing 时播放系统提示音 `Pop`。
- 声音来源为 macOS `/System/Library/Sounds`，不引入自定义音频文件。
- 同一提示音会复用缓存的 `NSSound`，每次播放前 stop/reset，避免短时间连续触发时被 token 去重或播放位置吞掉。
- 提示音是 UI 反馈，不改变录音、转写或注入流程。

### `INJECTING`

- 短暂显示绿色/青绿色状态，表示正在把结果输入到当前 App。

### `ERROR`

- 显示红色状态。
- 不抛出 UI 异常影响主流程。

## 接口约束

外部接口保持不变：

```python
overlay.show(state)
overlay.hide()
overlay.set_state(state)
overlay.set_level(level)
```

调用方不需要知道 NSPanel、NSView、动画或主线程调度细节。

## 验收标准

- 热键启动录音后浮窗出现。
- 录音中声波会随音量变化。
- 自动静音停止或手动停止后浮窗进入 processing loading 状态。
- 转写完成并注入后浮窗隐藏。
- 浮窗不抢输入焦点。
- 浮窗不阻挡鼠标。
- 浮窗不覆盖菜单栏。
- 录音、转写、注入原有测试通过。
