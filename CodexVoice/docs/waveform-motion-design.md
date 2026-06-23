# Waveform Motion Design

> 日期：2026-06-23  
> 状态：当前实现说明  
> 范围：CodexVoice overlay 内部动效数据层与声波渲染方案

## 当前结论

当前运行实现已回退到较稳定的 `CAReplicatorLayer` + centerline 版本。

这个实现处理的是 overlay 视觉运动，不处理：

```text
录音质量
VAD 判定
转录结果
文本注入
停止规则
```

外部 overlay 接口保持：

```python
overlay.show(state)
overlay.hide()
overlay.set_state(state)
overlay.set_level(level)
```

## 当前渲染结构

每种颜色：

```text
1 个 CAReplicatorLayer
1 条最大幅度 CAShapeLayer source line
99 个 replicator instance，指数递减
1 条 centerline
```

视觉上每种颜色有 100 条可见线。

## 当前动效数据层

内部使用 `WaveMotionModel`：

```python
class WaveMotionModel:
    def set_audio_level(self, level: float) -> None: ...
    def next_frame(self, dt: float) -> WaveRenderFrame: ...
```

当前 `WaveRenderFrame`：

```python
WaveRenderFrame(
    phase: float,
    amplitude_multiplier: float,  # 1.0 - 1.3
    voice_intensity: float,       # 0.0 - 1.0
)
```

无声时保持基础呼吸幅度；有声音时最高增强到 1.3。

## 当前优点

- 性能比 grouped compound path mesh 更稳。
- `CAReplicatorLayer` 由 Core Animation 复制细线，CPU 每帧只更新每色主 path。
- 每色 100 线和 centerline 结构简单，可维护。
- 已有单元测试覆盖线数、centerline、音量映射和系统提示音。

## 当前已知问题

- 同色线条仍偏机械复制，扰动不足。
- 运动主要受振幅影响，曲线频率、横向流速和波包位置没有随声音明显变化。
- 与参考视频相比，当前更像“线性声波”，不像“半透明丝带面 + ridge + 稀疏纹理”。
- 部分颜色在透明叠加后可能接近，尤其粉紫/紫色通道。

## 下一轮临时方案

下一轮重新设计已记录在临时文档：

```text
docs/waveform-ribbon-sparse-mesh-temp.md
```

该临时方案建议从“线条为主”转为：

```text
ribbon fill first
ridge highlight second
sparse mesh texture third
flow speed / frequency / envelope shift 随声音变化
```

该方案尚未实现。

