# Quality Gate Report: mw-autopilot-verify-cli

- **时间**: 2026-09-26T07:21:58Z（PM 收口）
- **触发**: Stage 完成（execute → verify 门禁）
- **范围**: 全量（14 AC / 16 VC / 17 Coverage 行）
- **覆盖 HEAD**: `8cd472a7b`（本 key 22 个提交）
- **证据汇总**: `evidence/runs/verify-20260926-evidence-collection.md`（下文 `§A…§F` 指向该文件）

## 前置门禁

| 检查项 | 结果 |
|--------|------|
| spec.md 存在 AC 编号 | ✅ 14 条（`AC-001`..`AC-014`） |
| design.md 存在 VC 编号 | ✅ 16 条（`VC-001`..`VC-016`） |
| AC→VC 映射 100% | ✅ 14/14（design §8） |
| evidence-requirement.md 存在 | ✅ |
| ac_fingerprint 一致 | ✅ 复算 `9c90fbb3e171` == 记录值（spec 机器抽取 14 条，编辑 `[REVISED]` 注记不影响 ID 集合） |
| 每个 task 有非空 ac_refs/vc_refs | ✅ 10/10 卡（脚本核对，见收口记录） |
| `evidence/baseline/` 非空 | ⚠️ **目录不存在**（本 key 未建该目录）。基线值改记于 `evidence-requirement.md`「基线」节与 §A1（`b0a30bc12`：`2 failed, 1007 passed, 10 deselected`）。记为验证欠债 1 项，不阻断（判据仍可核：基线红集合与本轮逐字比对一致） |

## 问题清单与核查结果

### 来源 A — spec AC

| 问题 ID | 描述 | 状态 | 证据引用 |
|--------|------|------|---------|
| Q-AC-001 | `set` 逐元素写入 argv、补全 13 键、`--project` 位置约束是否成立？ | ✅ 充分 | §B(AC-001)；T-05 `[VERIFY] VC-001` 两行；PM 子进程 6 项亲验 |
| Q-AC-002 | 规范化写入是否幂等（字节级）？ | ✅ 充分 | §B(AC-002)；T-05 `idempotent_bytes=True size=381`；T-07b `P3` 双向幂等 31/31 |
| Q-AC-003 | 同长度裸字节改写是否被拾取、非 ASCII 是否原样？ | ✅ 充分 | §B(AC-003)；T-01 `same_length_rewrite=9 cache_cleared=false`、`non_ascii_bytes=367 verbatim=true` |
| Q-AC-004 | `show` 是否给出逐字段 origin？ | ✅ 充分 | §B(AC-004)；T-05 `origins=['default','machine','project']` |
| Q-AC-005 | `clear` 是否永不删文件、只删自身键？ | ✅ 充分 | §B(AC-005)；T-05 两行 `VC-005` |
| Q-AC-006 | 两侧对同一 payload 是否同判？ | ✅ 充分 | §B(AC-006)；`P1 crosslang_verdict_match=53/53`（两侧各跑） |
| Q-AC-007 | 机器层域是否正确、空值即未决定是否正确？ | ✅ 充分 | §B(AC-007)；T-02b 6 例真值表 + `材料化场景仍取机器层` + `越域越界告警=2` |
| Q-AC-008 | doctor 是否把"两层皆空"判为 issue 并给修复串？ | ✅ 充分 | §B(AC-008)；T-03b 三条 `[VERIFY]` |
| Q-AC-009 | dist 同步与防复发四子判据是否成立？ | ✅ 充分 | §A2（PM `diff --exit-code`=0）、§A3（A1b/A2b 由 stale→fresh）、T-08 A1b/S1/dirty-guard 四行 |
| Q-AC-010 | 文档是否覆盖且可机器判定部分逐字节一致？ | ✅ 充分 | §A4（4 用例，fenced 417B 逐字节 + 12 锚点）；PM 逐段审阅 |
| Q-AC-011 | RMW 是否在锁内、锁不可得是否 fail-closed 且字节不变？ | ✅ 充分 | §B(AC-011)；T-05 `VC-011: lock_busy=return 1 file_unchanged=True`；T-04 console 锁用例 |
| Q-AC-012 | 默认是否零扰动（含零新增失败）？ | ✅ 充分 | §A1（红集合与基线逐字相同；`e2e_l2 8 passed`；vitest `101 passed`）；零足迹用例 4 组 |
| Q-AC-013 | verify 根锚定是否修复且真值表含 `control≠partition≠parent`？ | ✅ 充分 | §B(AC-013)；T-09 30 行表 + E2 形状 + live 路径；T-06 partition 用例 + 同族 5 锚点 |
| Q-AC-014 | 占位符逐元素展开、未定义 fail-closed、两侧一致？ | ✅ 充分 | §B(AC-014)；T-09 `VC-014` 4 行（含 44 parity case 证明 toolchain 未变） |

### 来源 B — design VC

| 问题 ID | 描述 | 状态 | 证据引用 |
|--------|------|------|---------|
| Q-VC-001 | argv 逐元素 + 位置约束有 PASS 证据？ | ✅ 充分 | T-05 `VC-001` 两行 |
| Q-VC-002 | 两侧同判有 PASS 证据？ | ✅ 充分 | `P1 53/53` |
| Q-VC-003 | 免缓存拾取有 PASS 证据？ | ✅ 充分 | T-01 `VC-003` 两行 |
| Q-VC-004 | origin 三态有 PASS 证据？ | ✅ 充分 | T-05 `VC-004` 两行 |
| Q-VC-005 | clear 语义有 PASS 证据？ | ✅ 充分 | T-05 `VC-005` 两行 |
| Q-VC-006 | 13 键表 + 镜像有 PASS 证据？ | ✅ 充分 | T-01 `VC-016`；`P5` 两侧 registry |
| Q-VC-007 | 空值即未决定（含材料化）有 PASS 证据？ | ✅ 充分 | T-02b 6 例 + 材料化场景；T-02c 复验 |
| Q-VC-008 | doctor issue 有 PASS 证据？ | ✅ 充分 | T-03b 三条 |
| Q-VC-009 | dist 重建 + 锚点有 PASS 证据？ | ✅ 充分 | §A2/§A3 |
| Q-VC-010 | 文档逐字节有 PASS 证据？ | ✅ 充分 | §A4 |
| Q-VC-011 | 锁拒绝有 PASS 证据？ | ✅ 充分 | T-05 `VC-011` |
| Q-VC-012 | 零扰动有 PASS 证据？ | ✅ 充分 | §A1 + T-11 三行 |
| Q-VC-013 | cwd 真值表有 PASS 证据？ | ✅ 充分 | T-09 30 行 + T-06 |
| Q-VC-014 | 占位符 + toolchain 未变有 PASS 证据？ | ✅ 充分 | T-09 4 行 |
| Q-VC-015 | 补默认键（F16）有 PASS 证据？ | ✅ 充分 | 判据**已按 D-004 撤回改写**为双视图：T-01b `partial_keys=1 default_keys=13 effective_keys=13`、T-02c `load_config_keys=1 effective_keys=13` |
| Q-VC-016 | 新键镜像有 PASS 证据？ | ✅ 充分 | T-07b `P5`（真跑两侧）+ T-04 TS 镜像用例 |

### 来源 C — Coverage Matrix（F1–F17，design §6）

| 问题 ID | 描述 | 状态 | 证据引用 |
|--------|------|------|---------|
| Q-COV-F1..F17 | 每条路径是否被实际覆盖并有证据？ | ✅ 充分（17/17） | `§D` 逐行映射；其中 F16 按撤回后语义（双视图）核销 |

### 来源 D — 交叉问题（PM 推导）

| 问题 ID | 描述 | 状态 | 证据引用 |
|--------|------|------|---------|
| Q-X-001 | 新增机器层是否改变了"未配置项目"的既有行为？ | ✅ 充分 | T-02b/T-03b/T-05 三组"只读零足迹"用例（不建 `.mw/`、不建 `_autopilot/`、不建 `~/.agents/`）；§A1 红集合不变 |
| Q-X-002 | 撤回 D-004 后，是否覆盖了任何更早 key 的冻结判据？ | ✅ 充分 | §A5：`test_vc008_missing_fields_byte_identical` **转绿**；`load_config` 仍返回文件实际键集 |
| Q-X-003 | 新 CLI 是否引入了"配置缺键 ⇒ serve 崩溃"这类跨进程故障？ | ✅ 充分（并已修） | T-11 五条 `[VERIFY]`（`{}`/xkey-only/paused-only 三形态不崩；`clear` 端到端后不崩；键存在时行为未变） |
| Q-X-004 | `clear` 之后文件留存、其它键不变、无键时零写？ | ✅ 充分 | T-05 `file_kept=True ... other_keys_intact=True` + `nothing_configured=no write mtime_unchanged=True` |
| Q-X-005 | 脏树护栏是否会挡住正常构建（含 Windows 文件模式位噪声）？ | ✅ 充分 | T-08 dirty-guard 行（non-git ⇒ 跳过、staged/untracked 均可见、`--allow-dirty` 显式绕过）；§A2 在干净树上构建成功 |

## 汇总

- **总问题数**: 52（14 AC + 16 VC + 17 COV + 5 X）
- **通过（充分）**: 52（100%）
- **有条件通过（不足）**: 0
- **未通过（无证据）**: 0
- **验证欠债（非阻断，已记录）**: 1 项（`evidence/baseline/` 目录未建；基线值改记于 evidence-requirement 与 §A1，判据可核）

**质检结论**: ✅ **通过**（无 ❌、无 ⚠️ 阻断项；验证欠债 1 项 ≤ 3 且已记录）

## 未通过问题行动计划

无。

## 二次印证结论

- **检查 1（spec 约束是否都被覆盖）**：14 条 AC 全部有 Q-AC 行；spec §5 的"两侧一致性判据"落在 Q-AC-006/Q-VC-002/Q-AC-014/Q-VC-014；§2.3 的"不可回退约束"落在 Q-X-002（`load_config` 原始视图）+ Q-AC-012（零扰动）。
- **检查 2（Function Flow 节点是否都有 Q）**：design §5 的 F1–F17 与 `§D` 一一对应，17/17 有证据行。
- **检查 3（异常路径是否都有 Q-COV）**：非法根名、嵌入/未定义占位、锁忙、脏树、坏 JSON 机器层、`--project` 放错位置 —— 分别落在 Q-AC-013/Q-AC-014/Q-AC-011/Q-AC-009(d)/Q-AC-007/Q-AC-001。
- **检查 4（task vc_refs 空绑定）**：脚本核对 10/10 卡均有非空 AC+VC 绑定，无遗漏。
- **额外发现（已补入）**：执行期新增 D-015（serve 缺键容错）与 AC-013 括注修订，均已在 design §11 回填并各有证据行（Q-X-003 / Q-AC-013），未产生新的未覆盖问题。

## 诚实披露（非判据失误，供后续 key 参考）

1. **两条既有红与本 key 无关**（§E）：readcap 的陈旧冻结副本、verdict-freshness 读 live 外部项目。基线即红，未修（不属本 key 写面）。
2. **`>2^53` 值域残差**：`2**53`/`2**53-1` 两侧一致并已入语料；`2**53+1` 会两侧分歧，**判定为不修并刻意不入语料**（避免把错误行为固化成契约）。见 design §11 与 `_pitfalls.md` P-022。
3. **本 key 未在真实项目上启用 xkey 通道**：FM/E2 的 `_autopilot/config.json` 无 xkey 键，MW 无 `_autopilot/` 目录 ⇒ 端到端"真项目 opt-in 并转绿"未实测（L2 合成链路已覆盖）。属用户决策项，列入 achieved.md 遗留。
