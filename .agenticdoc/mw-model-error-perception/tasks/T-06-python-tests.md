# T-06: Python 测试（配置 + launcher 重派）

type: coding

## 上下文

- 项目 goal：`.agenticdoc/goal.md`；Python 测试惯例：packages/multi-workers/test_*.py（pytest）。
- spec：`.agenticdoc/mw-model-error-perception/spec.md`（AC-007/008/009 断言面）；design：design.md §5.4（测试蓝图）、§4 契约。
- 依赖：T-02（mw.py/mw_common.py 配置层）、T-03（launcher.py 重派链）、T-03b（同模型重试预算，2026-10-15 已合入：`_model_err_max`/`_model_retry_history`/`_try_model_redispatch` 两段化）；若交付说明提及临时 stub，须确认已移除。
- 实现锚点（行号以当前文件为准，先自行定位）：`packages/multi-workers/mw_common.py`（`validate_fallback_models`/`load_fallback_models`/`fallback_models_for_task_type`/`FALLBACK_MAX_MODELS`）、`packages/multi-workers/mw.py:3524/3539/3553`（三处 `_model_write`，经 `_dispatch_extra_keys` 读改写）、`packages/multi-workers/launcher.py:1979` 附近（`inject_fallback_env`）、`_MODEL_RETRY_RE`/`_model_retry_count`/`_try_model_redispatch`/`_poll_once` reap 分支。

## 要求

1. 新文件 `test_mep_fallback_config.py`：dispatch.yml 顶层 `fallback_models` 校验（格式/上限 4/非法键/空列表）；三处 `_model_write` 重写后 `fallback_models` 键保留（专项：构造含该键的 dispatch.yml，调用各写路径，断言键仍在——mw.py:3524/3539/3553）；doctor fallback 检查（格式 error/凭证缺失 warn）。
2. 新文件 `test_mep_launcher_redispatch.py`：**D3 修订后双层重派**：① 同模型重试：exit 3 → `[MODEL_RETRY] model=<m> attempt=1` 同模型重派（--model/INDEX/TRIED 不变、新 run_id 同 task_key）→ 再 exit 3 → 预算（默认 2）耗尽 → `[MODEL_FALLBACK]` 切备；② `PI_WORKER_MODEL_ERR_MAX=0` → 直接切备；③ 备用预校验失败跳过并续试；④ 链耗尽 → failed 终态；⑤ 未配置 fallback → 同模型重试耗尽后 failed；⑥ `PI_WORKER_FALLBACK_MODELS/_INDEX/_TRIED` env 注入格式；⑦ 重派不新增 resume-credit 配额、复用原并发槽。
3. 沿用既有 fake spawn/temp dir 模式（test_launcher.py / test_run_identity.py 先例），不真启 pi 进程。
4. 禁止：改 src 实现（发现问题报 PM）；真实网络/凭证。

## 写入允许面

- `packages/multi-workers/test_mep_fallback_config.py`（新建）
- `packages/multi-workers/test_mep_launcher_redispatch.py`（新建）

## 写入禁止面

- mw.py/mw_common.py/launcher.py（实现修复走 PM 决策）、TS 全部

## 交付格式

- 两个新建测试文件（仅限写入允许面）
- 交付说明：断言面与 AC 对映、复用的 fake spawn 模式说明；验收命令输出摘要；发现的实现问题清单（如有，仅报告不修）

## 验收命令

```
python -m pytest test_mep_fallback_config.py test_mep_launcher_redispatch.py -x
python -m pytest test_launcher.py test_dispatch_models.py -x   # 回归
```

- 全绿（packages/multi-workers 下执行）

## 改动历史

- 2026-10-15 任务创建（T-06，Stage 2，依赖 T-02/T-03）；同日修订：补 T-03b 依赖与 [MODEL_RETRY]/预算用例、补锚点与交付格式
