"""Record the MDC execution log: M-03 absorption (PM verification) into plan.md."""

import pathlib

PLAN = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-dynamic-concurrency\plan.md")

ADD = """
## 7. 执行日志（PM 吸收记录；行号以 symbol 为准）

### 7.1 M-03 终态吸收（配置上界 + 面板三量，PM 独立复核，2026-10-14）

- **卡**：`tasks/T-C-M03-config-panel.md`；终态 `needs-clarification`，唯一"问题"是**记账面**（`recover-incomplete: unrecorded write ... autopilot-config-corpus.json`）——该语料是按本仓既有纪律用脚本做**逐行外科修改**（不是 `json.dumps` 重灌），故 ledger 没有对应工具调用记录。**不是内容分歧**。
- **PM 亲自复算（不采信自述）**：
  - 语料 `sha256 = f5b60e81cd690930cc9afb4ef1ccdee6bd8d517e6d40521a3f1b84e65a13e9c1`（LF 归一化）、`cases = 77`（旧 73）、`bytes = 19388` ⇒ 与自报一致。
  - 聚焦套件：`test_autopilot_config.py`+`test_mwgal_t12_stage_close_auto.py`+`test_mwgal_t15_reattest_confirm.py` = **65 passed**；TS `autopilot-config-parity`+`autopilot-config-sync`+`autopilot-console` = **44 passed**、`autopilot-monitor` = **26 passed**、`tsgo --noEmit` exit 0。
- **PM 追查的两条"疑似分歧"，查完都不成立（记录以免后人重走）**：
  1. **`slotsUsed` 是否与 conductor 同源**：monitor 新口径 = 非终态 ∧ `workerBelongsToKey`（`monitor.ts:518-528`），我一度以为它"多加了 origin 过滤"。实查：`shared/worker-store.ts:65-70` 的 `workerBelongsToKey` **本身**就是 `workerOrigin === "conductor" && ownerKey === key`（D-019），Python 侧 `mw_common.row_belongs_to` 同形（`worker_is_conductor ∧ owner_key`）⇒ **两侧谓词完全一致，面板是忠实单源镜像**。`pending` 计入（非终态）、`manual` 不占槽（谓词内 origin 分支），与 D-106 一致。
  2. **`slotsUsed` 口径是否 keys/rows 混淆**：`slotsUsed = busyKeys.size`（**key 数**），`slotsMax = slotsCap = max_parallel_keys`（key 层上界）⇒ 同层可比，无混淆。
- **既有红（PM 独立确认为外部基线，非本卡）**：`test_autopilot_readcap_injection.py::test_baseline_left_end_bound` —— 断言"冻结副本 == `git show HEAD:...dispatch.py`"，而 `BASELINE_DIR` 默认指向**另一个仓库** `H:\\git\\E2Feature\\.agenticdoc\\feature-l3-readcap-injection\\...\\baseline_20260924`（2026-09-24 冻结），本机存在该 checkout 时必然失配（`219ed809…` vs `960cceec…`）。本卡未触碰 `dispatch.py`/该基线，且比较对象是 **HEAD 提交**而非工作树 ⇒ 结构性既有红。
- **本卡对 `test_autopilot_readcap_injection.py` 的改动是正当重冻**（`_GOLDEN_REGRESSION_SHA256["test_autopilot_config.py"]` 随 20→21 键更新，带注释说明，未放宽任何断言）；该文件其余测试全绿 ⇒ 新 sha 正确性由"只有那条外部基线红"隐式证明。
- **残留与去向**：① `dist/**` 未重建（不在写面，且 `npm run check` 被 P-017 禁）⇒ 与 WFG 的同一项合并，**交用户决定时机**；② `conductor.py:139/:3978` 的"13 键"过期文案（M-02 面，本卡只记录）；③ README/docs 键数文案（不在写面）⇒ 收口前 PM 一并处置；④ 面板 `|F|` 是 conductor `|F|` 的**上界**（TS 不读 claim），已在其注释与 spec 口径内说明。
- **PM 判定**：**接受**（AC-004/005/006/007 证据充分；AC-012 的单源由上述谓词验等证明）。
"""

text = PLAN.read_text(encoding="utf-8")
if "## 7. 执行日志" not in text:
    PLAN.write_text(text.rstrip() + "\n" + ADD, encoding="utf-8")
    print("plan: appended §7 execution log + 7.1")
else:
    print("plan: already has §7")
print(f"plan.md lines={len(PLAN.read_text(encoding='utf-8').splitlines())}")
