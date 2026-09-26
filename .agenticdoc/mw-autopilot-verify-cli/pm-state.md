# PM State: mw-autopilot-verify-cli

## 1. Snapshot
- Key: mw-autopilot-verify-cli
- Phase: DONE
- Next Action: verify 收口（质量门禁报告已出，待 `advance_phase verify` → `done`）
- Started: 2026-09-26 14:18
- Updated: 2026-09-26 15:23
- Completed: 2026-09-26 15:23

## 2. Task Status

| 卡 | 内容 | 状态 |
|----|------|------|
| T-01 / T-01b | config 侧 13 键 + `_STRING_FIELDS` + `ensure_ascii=False`；`load_config` 收窄为原始视图 | done（`77aa92586` / `fc79efaf1`） |
| T-02 / T-02b / T-02c | `autopilot/effective_config.py`：双视图 + 域收窄 + 空值即未决定 + 自补 13 键 | done（`30abe5bcb` / `d6efaecb9` / `a3b5769e4`） |
| T-03 / T-03b | `mw_common`：render_argv / workspace_root / repo_bundle_anchor / sourcemap_drift / doctor 段（顶层导入） | done（`d1d2a0cf6` / `e52f388ce`） |
| T-04 | TS 镜像 13 键 + `configLockPath`/`saveConfigLocked` + reviver + console 四 handler 进锁 | done（`5ffd5c4d6`） |
| T-05 | `mw autopilot verify set\|show\|clear` CLI（含 dry-run、`--project` 位置约束、clear 永不删文件） | done（`183815040`） |
| T-06 | conductor/dispatch 根锚定（`resolve_verify_cwd`、同族 5 锚点重锚、有效层消费） | done（`70901228b`） |
| T-07 / T-07b | 跨语言语料 + 两侧判据（53 例；分层原始/解析视图） | done（`6e6751e18` / `3749b38be`） |
| T-08 | A1b/A2b 内容锚点 + S1 先 build 后 deploy + 脏树护栏 | done（`edf8e1832`） |
| T-09 | cwd/占位符真值表 30 行 + E2 形状回归 | done（`ef6461dfa`） |
| T-10 | 文档（README/UPDATE）+ 文档判据 + dist 重建 + 全量回归 | done（`e34fb8bad`） |
| T-11 | serve 缺键容错（执行期新增，PM 决策 D-015） | done（`be946924e`） |

## 3. Evidence Ledger

| 时间 | 检查 | 结果 | 对应 |
|------|------|------|------|
| 2026-09-26 | `python -X utf8 -m pytest -q`（`packages/multi-workers`） | `2 failed, 1182 passed, 10 deselected`（红集合 == 基线 `b0a30bc12`） | AC-012 |
| 2026-09-26 | `python -X utf8 -m pytest -q -m e2e_l2` | `8 passed, 1186 deselected` | AC-012 |
| 2026-09-26 | vitest 6 个 autopilot/config 套件 | `Test Files 6 passed (6)`、`Tests 101 passed (101)` | AC-006/011 |
| 2026-09-26 | `mw build --install` 后 `git -c core.fileMode=false diff --exit-code -- packages/{multi-workers,coding-agent}/dist` | **exit=0（空）** | AC-009(a) |
| 2026-09-26 | `repo_bundle_anchor()` / `sourcemap_drift()` | `stale=false` / `stale=false`（472/472 匹配；执行期曾 `stale=true` 4/472） | AC-009(b)(c) |
| 2026-09-26 | `test_autopilot_docs.py` | `4 passed`（fenced 417B 逐字节 + 12 锚点 + 矩阵行 + A1b/A2b 行） | AC-010 |
| 2026-09-26 | `test_autopilot_readcap_injection.py::test_vc008_missing_fields_byte_identical` | **PASS**（D-004 撕回后转绿，无覆盖更早 key 的冻结判据） | AC-012 / 跨 key |
| 2026-09-26 | 质量门禁报告 | ✅ **PASS**：52 问题（14 AC + 16 VC + 17 COV + 5 X）全部充分，0 ❌ 0 ⚠️（1 项非阻断验证欠债：`evidence/baseline/` 未建） | 全量 |

PASS：质检结论 ✅ 通过，报告 `evidence/quality-gate-report-20260926-072158.md`，证据汇总 `evidence/runs/verify-20260926-evidence-collection.md`。

## 4. Hypothesis Queue

*(无 open 假设；执行期新增假设均已核销：① "撤回 D-004 会让其它 key 变红" ⇒ 实测 `test_vc008` 由红转绿；② "serve 会因缺键文件崩" ⇒ 实测 5 failed 反证后修复；③ "A2b 会误报" ⇒ 实测抓到的 4/472 是真漂移。)*

## 5. Decisions

- **D-001（exec）**：取消 `cached_load` 的 stat 短路（净负收益：命中比无缓存更慢，且同长度改写漏读）。AC-003 判据改为裸字节写。
- **D-002（exec，用户选项 1）**：机器层域**收窄为 `xkey_verify_cmd` + `xkey_verify_cwd`**，规则「空值即未决定」；`xkey_repair`/`xkey_verify_timeout_s` 越域即告警忽略。
- **D-004（exec，已撕回）**：原打算让 `load_config` 补 13 键——会覆盖 `feature-l3-readcap-injection` 的冻结 VC-008。改为**双视图**（`load_config` 原始 / `default_config()`+`load_effective()` 解析），下游由 T-02c/T-06/T-07b 认领修复。
- **D-015（exec，PM 新增）**：serve 监管步进的 `enabled` 读取改容错（`.get` + `DEFAULT_CONFIG` 默认），因本 key 的 `clear` 能造出缺 `enabled` 的文件而使 `mw serve` 崩。
- **`2^53` 残差**：不修、只记录，且**刻意不把分歧值放进语料**（避免固化错误行为）。
- **AC-013 括注修订**：spec 原「其它模式 = control 根」与 D-008（dual ⇒ game 根）不一致，spec 挂 `[REVISED @ 2026-09-26]` 对齐。

## 6. Turn End Records

- execute→verify：16 张 worker 卡全部终态 done 并 ack；逐卡 PM 亲验（跑测试 + 独立脚本/子进程 + 核对反证），全部入库（22 个提交）。
- 执行期三次自适应：① T-02 因依赖 T-01 语义改入波 2；② 发现域过宽 ⇒ 用户拍板收窄 + 新增 T-02b/T-02c；③ 撤 D-004 ⇒ 新增 T-01b/T-07b/T-11。
- verify 期：PM 亲跑全量回归 + 重建后产物 diff（exit=0）+ 文档判据 + 跨 key 冻结判据交叉验证；输出证据汇总与质量门禁报告，结论 ✅ PASS。

## 7. Process Log

1. spec v2（14 AC）+ 4 份 spec 研究 + 用户确认 U-1..U-6 → `b0a30bc12`。
2. design（D-001..D-014 + VC-001..VC-016 + F1–F17）过 mermaid 门禁；plan + 10 张卡；advance 至 EXECUTE。
3. 波 1：T-01/T-03/T-04（文件边界互斥）；波 2：T-02/T-02b/T-02c/T-03b；波 3：T-05/T-06/T-07；波 4：T-08/T-09/T-10/T-11。
4. 域收窄（用户选项 1）+ D-004 撕回 + `2^53` 残差记录，三者均已挂修订注记并同步卡面。
5. dist 重建两轮：首轮（T-10）补 9 个 catch-up 产物；入库后复跑 `mw build --install` 得**空 diff**，AC-009(a) 判据成立。
6. 质量门禁：fingerprint 复算一致、10 卡 AC/VC 绑定齐、52 问题全部充分 → ✅ PASS。
