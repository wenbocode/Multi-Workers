# Quality Gate Report: mw-provider-routing

**时间**: 2026-09-20T20:10:00+08:00
**触发**: VERIFY 阶段收口（T1–T6 全部 done 后全量质检）
**范围**: 全量（8 AC / 10 VC / Coverage Matrix F1–F7）

## 前置门禁

| 检查项 | 结果 |
|--------|------|
| spec.md 存在 AC 编号 | ✅ AC-001~008（8 条） |
| design.md 存在 VC 编号 | ✅ VC-001~010（10 条） |
| AC→VC 映射覆盖 100% | ✅ §8 表：8 AC → 10 VC，无空映射 |
| evidence-requirement.md 存在 | ✅ generated_at 2026-09-17（D-001 改选 C 后同步） |
| ac_fingerprint 一致 | ⚠️→✅ 锚定通过（见下「指纹锚定」） |
| task ac_refs 非空 | ✅ T1:AC-004 / T2:AC-001,002,003,006 / T3:AC-008 / T4:AC-005 / T5:AC-005 / T6:AC-007 |
| Error Fingerprint | ✅ 无 open 错误记录 |

### 指纹锚定（沿 mw-dual-workspace / mw-widget-terminal-lifecycle 先例）

- 记录值 `1f3b42bb09a9` 为 ad-hoc 口径，canonical 管道（`grep -oE 'AC-[0-9]{3}' spec.md | sort -u | sha1sum | cut -c1-12`，本会话 Python 等价实现含尾换行验证）对当前 spec 计算为 `541028221b8a`——与 ai-baseline-repair 键记录值相同（同一 AC-001~008 集合），佐证公式等价。
- AC-id 集合与 evidence-requirement 记录的 `ac_ids`（AC-001~008）**完全一致**；`.agenticdoc/mw-provider-routing/` 全部文件首提交即 a395b0af2，之后无 AC 变更提交（git log --follow 仅 1 条）。
- 结论：失配为生成时公式口径差异，非 AC 变更，不阻断。

## 问题清单与核查结果

### A. AC 层（spec §3）

| 问题 ID | 描述 | 状态 | 证据引用 |
|--------|------|------|---------|
| Q-AC-001 | 无 port 路由直连注入（无 localhost、含 PI_WORKER_TASK） | ✅ 充分 | test_launcher.py `TestPiZaiRouting::test_env_env_source` / `test_env_file_source`（env/auth.json 双源各一次 PASS，本日 -k zai 10 passed） |
| Q-AC-002 | 直连凭证缺失 → RuntimeError 含路由名与缺失描述 | ✅ 充分 | `test_env_missing_raises`（match="zai-coding-cn"；launcher.py 分支消息拼接 `describe_missing`） |
| Q-AC-003 | zai worker env 不含其他 provider 凭证 | ✅ 充分 | `test_env_isolated_from_other_credentials`（四凭证注入后全部缺席） |
| Q-AC-004 | route_precheck 列出 zai-coding-cn 可用性 | ✅ 充分 | test_common.py `test_zai_coding_cn_route_flip`（available 双态翻转）+ `test_zai_coding_cn_file_source`（file 源） |
| Q-AC-005 | 真实端到端派发（glm-5.3 往返、退出码 0） | ✅ 充分 | evidence/e2e-zai-smoke-2026-09-17.md（`-m e2e_real` 2 passed in 40.12s；launcher-out model=zai/glm-5.3 source=task、status=done、output.md 含真实回复） |
| Q-AC-006 | 默认路由保持 timi | ✅ 充分 | `test_default_route_stays_timi`（TIMI 在、ZAI 缺席）+ `test_command_requires_explicit_model` / `TestModelSelection::test_pi_timi_default_model_when_empty`（回归守护） |
| Q-AC-007 | 全量 pytest 0 failed | ✅ 充分 | 本日全量：**689 passed, 0 failed, 9 deselected**（59.00s；见「备注 N1」） |
| Q-AC-008 | 仅直连凭证不 spawn proxy | ✅ 充分 | test_serve_doctor.py VC-008 用例（hermetic TEST_* 凭证，spawn 列表不含 proxy_multi.py） |

### B. VC 层（design §7）

| 问题 ID | 描述 | 状态 | 证据引用 |
|--------|------|------|---------|
| Q-VC-001 | zai env 注入 + localhost 缺席 + PI_WORKER_TASK | ✅ 充分 | 同 Q-AC-001 |
| Q-VC-002 | 双源皆缺 → RuntimeError 含 provider 名与缺失描述 | ✅ 充分 | 同 Q-AC-002 |
| Q-VC-003 | 凭证隔离（ANTHROPIC/DEEPSEEK/TIMI 缺席） | ✅ 充分 | 同 Q-AC-003 |
| Q-VC-004 | precheck 路由条目 + available 翻转 | ✅ 充分 | 同 Q-AC-004 |
| Q-VC-005 | e2e_real 真实往返 + exit 0 | ✅ 充分 | e2e 证据文件（2026-09-17 实跑留底） |
| Q-VC-006 | 默认 provider=timi、TIMI 在、ZAI 缺席 | ✅ 充分 | `test_default_route_stays_timi` |
| Q-VC-007 | failed=0 deselected=9 | ✅ 充分 | 本日全量 689 passed / 0 failed / 9 deselected |
| Q-VC-008 | proxy_spawned=no | ✅ 充分 | 同 Q-AC-008 |
| Q-VC-009 | zai 无默认模型 raises；timi 默认 glm-5.3 | ✅ 充分 | `test_command_requires_explicit_model` + `TestModelSelection::test_pi_timi_default_model_when_empty` |
| Q-VC-010 | 双侧 prefix map 互逆同步 | ✅ 充分 | py: test_dispatch_models.py `test_prefix_map_matches_ts_mirror`（_TS_MIRROR 含 zai-coding-cn）+ 本日静态核验 mw_common.py:124；ts: agent-team-loop.test.ts parity 用例（本日 vitest 158 passed）；逆映射双侧均由前向 map 推导，结构互逆 |

### C. Coverage Matrix 层（design §6）

| 问题 ID | 路径 | 状态 | 证据引用 |
|--------|------|------|---------|
| Q-COV-F1 | 正常/边界（env 源 vs auth.json 源）/异常（缺凭证） | ✅ 充分 | VC-001（双源）+ VC-002（异常） |
| Q-COV-F2 | prefix 解析 / 裸 ID 不动路由 / 未知 prefix | ✅ 充分 | `test_zai_prefix_maps_provider` + `test_bare_model_keeps_route`；未知 prefix → RuntimeError 为**现状代码**（launcher.py:184，本 key diff 未触及，git show a395b0af2 验证），兼容层有 `test_unknown_prefix_incompatible`，错误注入分支有 `test_effective_entry_rejects_wrong_cli`（mw-dispatch-models 键交付并门禁过） |
| Q-COV-F3 | timi 默认 glm-5.3（回归）/ zai 无 model 异常 | ✅ 充分 | VC-009 双分支 |
| Q-COV-F4 | 凭证隔离 | ✅ 充分 | VC-003 |
| Q-COV-F5 | precheck 可见性 + auth.json file 源 | ✅ 充分 | VC-004 |
| Q-COV-F6 | 仅直连凭证 → 无 proxy spawn | ✅ 充分 | VC-008 |
| Q-COV-F7 | 端到端真实派发 / 退出码非 0 | ✅ 充分 | VC-005（exit 0 断言）；非 0 路径为通用 worker 失败处理（`test_missing_credential_marks_task_failed` 等，全量绿） |

### D. 交叉问题

| 问题 ID | 描述 | 状态 | 证据 |
|--------|------|------|------|
| Q-X-001 | 显式 zai 派发与默认 timi 路由是否互不污染（AC-005 × AC-006） | ✅ 充分 | `test_default_route_stays_timi` 显式双向断言（ZAI 凭证在场仍不进 timi env）；e2e 队列行 provider=timi 默认 + task.md model 行驱动路由，两路由共存验证 |
| Q-X-002 | precheck 可见性与 serve spawn 判定对同一无 port 路由是否一致（AC-004 × AC-008） | ✅ 充分 | 两用例共用同一 hermetic providers.json 形态；serve 判定仅按 port 存在性，precheck 仅按凭证链，正交无冲突 |
| Q-X-003 | TS 派发面与 py launcher 的 prefix 命名空间是否漂移 | ✅ 充分 | 双侧 parity 锁测试（VC-010）；npm run check 本日全绿 |

## 汇总

- **总问题数**: 28（8 AC + 10 VC + 7 COV + 3 交叉）
- **通过（充分）**: 28（100%）
- **有条件通过（不足）**: 0
- **未通过**: 0

**质检结论**: ✅ 通过

## 二次印证结论

- spec §2 约束逐条覆盖：平台无关（代码无平台分支，测试+e2e 在 Windows 实跑）；凭证双源（VC-001/004）；P-002 hermetic（测试全部 tmp_path/env 隔离，未触真 `~/.pi/agent/auth.json`——测试代码逐条核验）；凭证隔离语义（VC-003）。
- Function Flow 节点 A→N 全部落位：A/B/C 派发与 task.md 写入（e2e 实路径）、D/E `_resolve_entry_model`（TestLauncherResolution）、F prefix 重映射（VC-010 py）、G window 继承（VC-006）、H zai env 分支（VC-001/002/003）、I timi 分支零触碰（全量回归 + `test_env_has_timi_key` 等）、J 凭证判定（VC-002）、K 注入（VC-001）、M 命令构造（VC-009 + `test_command`）、N 真实往返（VC-005）、O timi 默认（VC-009）。
- 风险隔离主张（D-001）经 diff 验证：a395b0af2 对 launcher.py 的改动仅 zai 分支 + 直连元组 + docstring + `flush=True`，timi/anthropic/deepseek/openai-codex 路径零触碰。
- 无 task 空绑定；无 ❌/⚠️ 遗留。

## 备注（非阻断）

- **N1（deselect 8→9 漂移，design 已调和）**: AC-007 括注「deselect 维持 8」撰写于 T5 之前；本 key 按计划新增 1 条 e2e_real 用例（AC-005 要求）使 deselect=9，design VC-007 输出行已按 9 定稿。AC-007 的不变量「0 failed」成立（689 passed ≥ 433 递增基线）。判定：符合设计演进，非违例。
- **N2（commit 归属混杂）**: T1 的 mw_common.py 改动（prefix map `"zai"` 行 + `_DEFAULT_CONFIG` zai 条目）先被同工作树的 mw-partition-parent-extended 键提交 `2b5f259e2`（2026-09-20 16:17）携带入库，本键主提交 `a395b0af2`（17:31）因而无 mw_common.py diff。最终代码状态与 design §3 完全一致、全量测试绿；多 worker 共享工作树的已知归属风险，历史不重写，仅留痕。
- **N3（docs/zai_guider.md 脱敏）**: git status 确认 untracked（`??`），未入库——spec §4 风险的硬性要求满足。「落地后脱敏」为建议项，作为后续清理跟进，不阻断本门禁。

## 验证运行记录（本日新鲜证据）

| 运行 | 结果 |
|------|------|
| `python -m pytest .`（multi-workers 全量） | 689 passed, 0 failed, 9 deselected（59.00s） |
| `python -m pytest test_launcher.py test_common.py test_serve_doctor.py -k zai` | 10 passed |
| vitest `test/extensions/agent-team-loop.test.ts` | 158 passed（3.49s） |
| `npm run check`（repo 根） | 全绿（含 shrinkwrap/install-lock/browser-smoke） |
| 静态核验 mw_common.py ↔ dispatch-models.ts | zai ↔ zai-coding-cn 双侧互逆存在 |
