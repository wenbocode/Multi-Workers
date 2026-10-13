# T-26 收口验证批次（第二次 cutover 后：C-31 运行期闭环 + 全量回归）

- Key: mw-dispatch-card-gate｜Wave: 18（收口验证，非实现卡）｜type: coding｜依赖: T-18~T-25（全部终态）+ 两次 cutover

## 上下文
两次 cutover：第一次 `A5B0FC9C…4932` → `975D4066…978D`（T-18~T-22 进 bundle）；第二次 → **`5877E4FD3F035BDBA1E3F26527191B754B680FDB5C9522B4F049097A17FAC669`**（T-25 的构建期版本注入，`0.83.0` 命中 0 → 1）。用户已两次执行 `/mw restart` + `/reload`。
**本卡自身即最终判据**：若 C-31 已闭环，本卡 `task.md` 的身份行版本必须是 **`0.83.0`**（而非 cutover 前的 `0.0.0`）。

## 要求（逐条可验收，**只报告真相**）
1. **C-31 运行期闭环**：读**本卡自己的 `task.md`** 头部区，逐字转载 `card_path:` / `card_sha256:` / `envelope_producer:` 三行。
   - 判据：`envelope_producer` 必须形如 `agent-team-loop-pm@0.83.0`；
   - 若仍为 `0.0.0` ⇒ **明确报告"未闭环"** 并附头部原文（不得解释成别的原因）；
   - 与 `packages/coding-agent/package.json` 的 `version` 字段逐字比对是否一致。
2. **card_audit**：对本 key 运行 `packages/multi-workers/autopilot/card_audit.py`，报告 `cards / dispatched / missing / tampered_cards / unlisted / unlisted_after` 与**退出码**；确认本卡被计为 `dispatched [ok]`、未跌入 `unlisted_after_boundary`；说明 `unlisted_after` 的构成（预期为 cutover 前的历史行）。
3. **独立复跑（必须给出每套的 passed 数与 exit code）**：
   - （`packages/coding-agent`）`test/suite/mwds-t24-orphan-scope-narrowing.test.ts`、`test/suite/mwds-t25-version-and-dotless.test.ts`、`test/suite/mwds-t23-cutover-recheck.test.ts`、`test/suite/mwds-t19-orphan-ownership.test.ts`、`test/suite/mwds-t22-orphan-evidence.test.ts`、`test/suite/mwds-t21-write-intent-soundness.test.ts`、`test/suite/mwds-t02-write-intent.test.ts`；
   - （`packages/multi-workers`）`test_mwds_t25_version_semantics.py`、`test_mwds_t20_roadmap_table.py`、`test_mwds_t14_producer_skew.py`、`test_launcher.py`；
   - 注意 `mwds-t02` 的 AC-010 语料回放必须报 `false_positives=0`。
4. **仓库根全量基线**：`python -X utf8 -m pytest packages/multi-workers -q` —— 报告 `failed/passed` 数与**失败用例全名**（期望恰为两条既有基线：`test_autopilot_readcap_injection.py::test_baseline_left_end_bound`、`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`）。
5. **`npm run check`**：报告退出码与末行（若 biome 会改写你写面之外的文件，**先停下在报告中说明**）。
6. **全局安装面同源**：比较全局 bundle 与 repo bundle 的 sha256，期望 **`5877E4FD3F035BDB…FAC669`**（用 `mw_common.global_ext_dir()` 取全局目录以规避 `~/.pi/agent` 字面触发的 protected-config 守卫；**不得**绕过守卫、不得改任何配置）。
7. **真实越界仍红（复核一次即可）**：`launcher.py` 声明无 `[WRITE_FILE]` 事件 ⇒ `extra` 必须包含它；`scripts/deploy`（无扩展名）有事件 ⇒ 不判 extra、无事件 ⇒ 判 extra。

## 种子（seed）
- **目标锚点**：`.agenticdoc/goal.md`（「核心交付」段：*mw 后台服务 + agent-team-loop 扩展*、*文件驱动的去中心化协调* —— 本卡是对该交付在 cutover 后运行期的整体验收）。
- **锚点**（符号名定位；行号为当前基线）：
  - `packages/coding-agent/src/config.ts:508`（`VERSION = buildVersion || pkg.version || "0.0.0"`）
  - `packages/multi-workers/mw.py:4328`（`define: { __PI_CODING_AGENT_VERSION__: … }`）、`:4368`（`_build_bundle(out=…)`）
  - `packages/multi-workers/launcher.py:1021`（`producer_version_is_unknown`）、`:1039`（`_PRODUCER_VERSION_UNKNOWN_MARKER`）
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts:253`（`isExistingDotlessCandidate`）
  - `packages/multi-workers/autopilot/card_audit.py:189`（`audit()`）

## 改动历史（本卡依赖的上游改动）
- **cutover #1**：`mw build --install --allow-dirty`，bundle `A5B0FC9C…4932` → `975D4066…978D`（T-18~T-22）。
- **cutover #2**：同一命令，bundle → **`5877E4FD…FAC669`**（T-25 构建期版本注入；构建输出 `version=0.83.0`）。
- **T-25**：`config.ts` 增 `__PI_CODING_AGENT_VERSION__` define + `buildVersion` 优先；`mw.py` 注入；`launcher.py` 把全零版本判为"未知"（`producer-version-unknown`，不判 skew、仍 fail-closed）；`change-ledger.ts` dotless 存在性仲裁。
- **服务**：两次重启，PID 79536 → 158412 →（本次重启后以 `mw_status` 实测为准）。

## 交付格式
- 写入允许面：本 worker 目录 taskDir（报告与临时脚本）；如确需测试辅助，可新建 `packages/coding-agent/test/suite/mwds-t26-closeout-verify.test.ts`（仅只读断言）。
- 写入禁止面：`packages/coding-agent/src/**`、`packages/multi-workers/**`（除只读调用）、`test/extensions/**`、`.agenticdoc/**`（除本 worker 目录 taskDir）、其它 key 目录。
- 报告须含：①头部三行原文 + 与 `package.json` 的比对结论；②`card_audit` 原始输出与退出码；③第 3 条每套测试的 passed 数 + exit code；④全量 pytest 的 failed/passed + 失败用例全名；⑤`npm run check` 退出码与末行；⑥同源 sha256 结论；⑦真实越界仍红的复核输出；⑧结论（C-31 是否闭环、判据是否被放松）+ 残留与未验证 + 上下文来源清单。
- **不做** cutover、不重启服务、不改 task 卡、不改 `src/**`、不写其它 key。全绿不是目标 —— **报告真相**是目标（若有不符判据之处，如实写清）。
