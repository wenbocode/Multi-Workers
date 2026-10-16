# T-03: launcher 重派链（launcher.py）

type: coding

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（worker 进程级隔离；文件驱动协调；mw-dispatch-reliability 的 per-task credential 隔离遗产）。
- spec：`.agenticdoc/mw-model-error-perception/spec.md`（AC-001 有界性、AC-008 重派半、AC-009 trace/预校验半）；design：design.md §3.2（本任务蓝图）、§2 D2/D5/D6、§4 协议契约。
- 关键锚点（TRQ-1/TRQ-3/TRQ-5 取证，行号自行校对）：
  - worker 命令组装（`--provider/--model` flag）：launcher.py:1372-1388
  - env 构建与 PI_WORKER_TASK 注入：launcher.py:280-368（`_build_env`）
  - inject_rag_env 后置注入先例：launcher.py:1979 附近
  - reap/product-first 写队列行：launcher.py:418-454
  - `_exit_to_status`：与 markOutcome 同构（0=done/2=nc/else=failed）——exit 3 须在状态映射前被拦截
- 契约（design §4）：env `PI_WORKER_FALLBACK_MODELS`（csv "provider/model"）、`PI_WORKER_FALLBACK_INDEX`（int 从 0）、`PI_WORKER_TRIED_MODELS`（csv 含主模型）；trace 行 `[MODEL_FALLBACK] <iso> from=<m> to=<n> attempt=<k>`（launcher 写入任务 trace.log）；重派硬上限 = fallback 数组长度，无额外配额，不与 resume-credit 互動。

## 要求

1. `inject_fallback_env`（inject_rag_env 旁）：从 dispatch.yml 顶层 `fallback_models[task_type]`（T-02 提供的读取/校验函数）解析并注入三个 env；未配置类别=不注入（行为与现状一致）。
2. reap 分支：worker exit==3（run.json `model_exhausted: true` 双重确认）且 INDEX+1 < 数组长 → 对下一备用预校验（route 存在 + 凭证可用，复用 mw-dispatch-reliability 既有校验器；不合格**跳过并续试下一个**，跳过也写 trace 行说明）→ 向任务 trace.log 追加 `[MODEL_FALLBACK]` 行 → 同任务重派：`--model <next>`、INDEX+1、TRIED 追加、新 run_id、task_key 不变。链耗尽 → 既有 failed 终态（Exit Reason/queue 行透传 worker 的 model unavailable 信息）。
3. 重派沿用既有 spawn 管线（credential 隔离、worktree 复用语义不变）；重派计数只由 fallback 数组驱动。
4. 禁止：改 mw.py/mw_common.py（T-02 所有）、TS 侧、`~/.pi`、resume-credit/stalled-gate 语义。

## 写入允许面

- `packages/multi-workers/launcher.py`

## 写入禁止面

- `packages/multi-workers/mw.py`、`mw_common.py`（T-02 所有）、test_*.py（T-06 所有）、TS 全部、`~/.pi`

## 交付格式

- 修改后的 launcher.py（仅限写入允许面）
- 交付说明：inject_fallback_env 与 exit-3 reap 分支的实现方式、预校验跳过逻辑、若用了临时 stub 须在此声明；验收命令输出摘要

## 验收命令

```
python -m pytest test_launcher.py test_run_identity.py -x
python -c "import ast; ast.parse(open('launcher.py',encoding='utf-8').read())"
```

- 全绿 + 语法通过；并行说明：mw.py/mw_common.py/test_*.py 由其他并行 worker 负责，其报错不归你修。T-02 未合入期间可用临时 stub 读取函数自测，交付说明中注明（T-06 前必须移除 stub）

## 改动历史

- 2026-10-15 任务创建（T-03，Stage 1）
