# Evidence Requirement: xkey-repair-mechanism

| 项 | 值 |
|---|---|
| spec_path | `.agenticdoc/xkey-repair-mechanism/spec.md` |
| spec_locked_at | 2026-09-26T03:55:43Z（AC-004/005/010 已 `[REVISED @ 2026-09-26]`） |
| ac_fingerprint | `b944d7646135`（门禁口径：sorted-unique AC ID 集 sha1 前 12 位） |
| ac_ids | AC-001 … AC-011（11 条） |
| vc_ids | VC-001 … VC-012 |
| design | `design.md`（D-001…D-012；调研留底 `evidence/research/design-*-20260926.md` × 4） |
| generated_at | 2026-09-26T04:30:00Z |

## 各 AC 充分性判定标准

| AC | 充分判定（单次 PASS 即闭环） | 证据形态 |
|---|---|---|
| AC-001 | 同一 `(file,test_id,冻结块指纹)` 重复扫描 N 次后 `ledger.json` 该 `dedup_key` 记录数 = 1，`history` 长度不随重复扫描增长（VC-001） | L1 单测 + 账本实物 |
| AC-002 | 无登记红（缺 `file`/`test_id`，或 owner 为 `兄弟 key`/`PM`/`conductor` 等角色值、不可解析到具体 key）→ `tickets/` 新增 0，escalation 记录 +1（VC-002）；**语料驱动**：FM 散文字形 S-C/S-E/S-F 各一条逐字用例 | L1 单测（真值表）+ 语料出处注释 |
| AC-003 | 工单生成至追认前，被涉及文件 sha256 = 工单创建时记录值（VC-003）；同一 pending 工单经 N tick 的 gate 文件数 = 1（VC-012，flood 红线） | L1 单测 + gate 目录实物计数 |
| AC-004 | 三小项：worker 模式/无 UI 通道作答 → gate 仍 pending；工具层写 gate 目录 → 文件 sha 不变 + 拦截记录 = 1；证据含作答来源字段与"非密码学证明"披露（VC-004） | L1 单测 + L2 场景（真实扩展内 tool_call 拦截） |
| AC-005 | 越界提案（改断言主体/触碰不可触碰清单/其它文件）→ 应用 0 次、目标文件 sha256 = 工单创建时、状态 ≠ applied（VC-005）；边界判据 = 行集合 ⊆ 工单声明集（D-005/D-012 三元组） | L1 单测 + 构造用例（含真值表正反例） |
| AC-006 | 缺五项任一 → `closed=False`；齐备 → `closed=True`（VC-006）；五项 = old/new sha256、reason、是否放宽断言、定向复跑命令与原始 stdout、全量红数 before→after | L1 单测（含逐项缺省负例）+ 证据包实物 |
| AC-007 | 闭合后 `ledger` 行 status=closed、受影响两 key 登记标注数 = 2；重复闭合后行数与标注数不变（VC-007） | L1 单测 + 账本实物 |
| AC-008 | 开关关闭时 xkey 目录新增工件数 = 0 + 既有 conductor/L3 相关测试全绿（VC-008） | L1 单测 + 既有测试运行日志 |
| AC-009 | fixture 全链重放后 fixture 冻结断言红数 1→0，状态序列覆盖 detected→closed（VC-009） | L2 e2e（合成 fixture，非 FM 树） |
| AC-010 | FM 语料 fixture 重放（选路 b：前态由逐字语料构造）后 `tests/test_hitl_channel.py` 红数 1→0、全量红数 1→0，证据含 old/new sha256 与 `relaxed_assertion=False`（VC-010） | L2 e2e + 语料逐字引用（含 `repair-r1-out-…-r3.txt:220` 等锚点）；**不得污染 FM 工作树** |
| AC-011 | 10 种字形（S-A…S-J）解析：键值对字形字段与人工判读逐字段一致；散文字形全部降级 escalate；写侧 prompt 文本含机器行要求（VC-011） | L1 真值表（语料驱动）+ 写侧/读侧双侧测试（P-005 锁） |

## 测试落点与不变量（设计期确立）

- 新测试文件：`packages/multi-workers/test_autopilot_xkey_registration.py`（**避开**两处既有 sha 锁：`test_autopilot_verdict_source_fallback.py:66-67/:529`、`test_autopilot_verdict_freshness.py:68`）
- 既有判定契约不动：`_l3_qualifies:1207` 判定语义不变；`_parse_l3_output`/`_md_section` 所在区域不得改动
- gate 目录写拦截与 `protected-config.ts` 同族（`tool_call` fail-closed）

## 质检门禁使用说明

本文件由质检门禁读取，对 AC-001…AC-011 逐条核查证据充分性；VC 输出行形状见 `design.md` §7（`[VERIFY] VC-NNN: k=v`）。任一 AC 缺证据或证据形态不符即判不充分。
