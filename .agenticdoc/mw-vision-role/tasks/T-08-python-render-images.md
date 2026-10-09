# T-08 Python `images:` 渲染与零字节回归

- key: mw-vision-role · 波 1 · 独占写面：`packages/multi-workers/autopilot/dispatch.py`（`render_task_md` 段）、`packages/multi-workers/test_autopilot_readcap_injection.py`
- ac_refs: AC-009 · vc_refs: VC-009
- 依赖: T-01（同文件串行于 REGISTRY 段） · 预估: 45-60min

## 目标

Python 渲染器支持条件 `images:` 行；未声明时**逐字节不变**；并固化一条不依赖 live HEAD 的零字节回归。

## 契约（逐字遵守）

```diff
 def render_task_md(task_type: str, prompt: str, *, loop: str, attempt: int,
     ...
     model: str = "",
     phase: str = "",
+    images: str | None = None,
     profile_block: str | None = None,
```
```diff
     if phase:
         lines.append(f"phase: {phase}")
+    if images:   # None / "" -> 零字节（AC-009）；声明时写 images: yes|no
+        lines.append(f"images: {images}")
     if model:
         lines.append(f"model: {model}")
```

- 插入位 = `:300`（`if phase:` 块）与 `:301`（`if model:`）之间 —— 代码里唯一能满足 `type < phase < images < model` 的位置
- **禁止** `if images is not None:`（会让 `images=""` 渲染出 `images: no`，违反 AC-009）
- 生产调用点 `dispatch.py:514` 保持默认（conductor 不写该头）

## 已知触点（必须同卡处理）

- `test_autopilot_readcap_injection.py:898/906 test_render_task_md_signature_shape` 的 `extra` 期望列表需加 `"images"`（否则必红）
- **不得**用 `:885 test_baseline_left_end_bound` 作零字节证据（该断言本机现状即为红：冻结副本 sha256 ≠ git HEAD，与本 key 无关）

## 步骤

1. 改签名与渲染（两处）。
2. 补 `extra` 期望。
3. 新增零字节用例（复制 `_head_module()`/`head_render()` 范式 `:165-186/254-258`，冻结一份改造前渲染器模块副本，不依赖 live HEAD）：
   ```python
   live  = dispatch.render_task_md("verifier", "do it", images=None, **kw)
   empty = dispatch.render_task_md("verifier", "do it", images="",  **kw)
   head  = _pre_images_module().render_task_md("verifier", "do it", **kw)
   assert live == empty == head and "images:" not in live
   ```
4. 跑既有 4 处 golden（`test_rag_phase.py`、`test_autopilot_dispatch.py`、`test_autopilot_conductor_exec.py`、readcap VC-007/008）确认全绿（应无需重冻）。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_autopilot_readcap_injection.py test_rag_phase.py test_autopilot_dispatch.py test_autopilot_conductor_exec.py -q -s
```

## 证据格式

`[VERIFY] VC-009: zero_byte=true frozen_copy=true`（`print(..., flush=True)`）

## 非空洞对照

把真值判断改成 `is not None` ⇒ 零字节用例红；把插入位挪到 `model:` 之后 ⇒ 顺序断言（T-06 的 TS 侧对应断言 + 本卡的 `images` 位置断言）红。

## 交付

`dispatch.py` 两处改动 + readcap 测试改动 + 原始输出。
