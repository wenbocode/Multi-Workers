# T-03b: launcher 同模型重试预算（launcher.py 修订）

type: coding

## 上下文

- 项目 goal：`.agenticdoc/goal.md`；spec/design 已修订（AC-001/008/009、design §2 D3 修订版）：**每模型 N=2 次进程尝试的预算从 worker 移到 launcher**。
- 现状锚点（T-03 交付，行号自行校对）：`packages/multi-workers/launcher.py:1979` 附近（inject_rag_env / 新增 inject_fallback_env 区）、`_poll_once` reap 循环（exit 3 拦截分支）、`_run_model_exhausted`/`_try_model_redispatch`/`_model_fallback_history`/`_fallback_candidate_available`、`_spawn(model_override/fallback_index/tried_models/main_model)`——链状态从 trace.log 推导、重启安全。
- 契约（design §4 修订）：新 trace 行 `[MODEL_RETRY] <iso> model=<m> attempt=<k>`（同模型重派）；`[MODEL_FALLBACK]` 仅用于模型切换；`PI_WORKER_MODEL_ERR_MAX`（int，默认 2，0=同模型不重试直接切备用）为同模型重试预算（launcher 从自身 env 读取；serve env 透传，_stripped_env 不剥）。

## 要求

1. exit 3（run.json model_exhausted 双确认）时：先从 trace 推导当前模型的既有 `[MODEL_RETRY]` 次数 k；k < 预算 → 同模型重派（`--model` 不变、INDEX/TRIED 不变、新 run_id、追加 `[MODEL_RETRY] model=<m> attempt=<k+1>`）；k ≥ 预算 → 进入既有 fallback 推进逻辑（`_fallback_candidate_available` 预校验跳过不变、`[MODEL_FALLBACK]` 不变）。
2. 预算读取：launcher 进程 env `PI_WORKER_MODEL_ERR_MAX`（serve env 透传；缺失=默认 2；非法值=回退默认并 warn 一次）。
3. 预算耗尽语义与重启安全保持 T-03 设计（trace 为唯一事实源）；重派仍复用原并发槽、不占 pending 队列。
4. 禁止：改 worker TS、mw.py/mw_common.py（如需配置函数入口用 T-02 既有导出）、`~/.pi`、resume-credit。

## 写入允许面

- `packages/multi-workers/launcher.py`

## 写入禁止面

- mw.py、mw_common.py、test_*.py（T-06 所有）、TS 全部、`~/.pi`

## 交付格式

- 修改后的 launcher.py（仅限写入允许面）
- 交付说明：同模型重试计数推导方式、预算读取与回退、与既有 fallback 推进的衔接；验收命令输出摘要

## 验收命令

```
python -m pytest test_launcher.py test_run_identity.py test_mwds_t07_reap_productfirst.py -x
python -c "import ast; ast.parse(open('launcher.py',encoding='utf-8').read())"
```

- 全绿（test_bom_historical_books 环境语料缺失用例可 --deselect 并注明）；行为自测：exit 3 attempt1→[MODEL_RETRY] 同模型重派→attempt2→[MODEL_FALLBACK] 切备→耗尽 failed；PI_WORKER_MODEL_ERR_MAX=0 → 直接切备用；=1 → 一次重试后切备

## 改动历史

- 2026-10-15 创建（D3 修订衍生，依赖 T-03）
