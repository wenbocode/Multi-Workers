# T-01 xkey 核心模块（W1 单写者）

key: `xkey-repair-mechanism` · 依赖: 无（契约冻结见 plan.md） · 覆盖: VC-001…003,005,006,011,012

## 目标

新建 `packages/multi-workers/autopilot/xkey.py`——本机制的全部纯逻辑与文件原语。**conductor 不在本卡范围内**（T-03 负责挂载）。

## 契约（逐字遵守 `plan.md`「契约冻结」节的签名）

公开面：`REGISTRATION_KEYS` / `parse_registration` / `collect_registrations` / `dedup_key` / `ledger_load` / `ledger_append` / `ticket_write` / `ticket_load` / `tickets_iter` / `locate_frozen_block` / `check_boundary` / `apply_block_replace` / `run_verification` / `evidence_bundle_write` / `XKEY_STATUSES`。其余 helper 自由命名。

## 行为要求（每条附 design 决策号）

1. **登记解析（D-001）**：键值对优先（`cross_key_test` / `owner` / `handoff` / `frozen_block`）→ `path::test` 与 owner 形态白名单兜底 → 跨 sources 合并去重。**缺 `(file,test_id)` 或 owner 不可解析到具体 key ⇒ 返回 None**。禁用角色值当 owner：`兄弟 key` / `PM` / `conductor` / `owner`（实测 FM 语料里确有这三种）。**不猜 owner**。语料逐字样本见 `.agenticdoc/xkey-repair-mechanism/evidence/research/design-registration-carrier-20260926.md`（10 字形 S-A…S-J）。
2. **账本（D-002）**：`_autopilot/xkey/ledger.json`，形状 `{rows:[{dedup_key,source_key,owner_key,test_id,file,frozen_block,status,request_id,history[{ts,event,detail}]}], updated_at}`；`ledger_append` 同 `dedup_key` **不新增行**（只可追加 history）；写 = 锁内 RMW + `tmp` + `os.replace`（锁接口 `mw_common.acquire_lock`，见 `packages/multi-workers/mw_common.py:1480` 附近；`gates.py:198` 是原子写范式）。
3. **工单（D-003/D-004）**：`tickets/xkey-<request_id>.md`（frontmatter 形状仿 gate 协议）+ `tickets_iter` 目录枚举；`request_id` 由调用方传入（conductor mint，T-03 负责生成），本模块不生成。
4. **冻结块定位（D-006）**：`locate_frozen_block(root, file, test_id)` 用 `ast` 做 **fail_line → test_id → FunctionDef → 模块级唯一引用 → Assign 行范围**；任一不确定（命中 ≠ 1 / 动态 `getattr` / 跨文件常量 / 条件赋值 / 局部遮蔽）**返回 None**（=降级仅提案）；返回 `{"file","symbol","line_range","old_block_sha256"}`。
5. **边界校验（D-005/D-012）**：`check_boundary(proposal, ticket)` 判"提案行集合 ⊆ 工单声明行集合 ∧ 未触碰 untouchable 清单 ∧ 未涉及其它文件"；**哈希用字节精确 sha256**（保持 CRLF/LF 原样），同记录附 `sha256_eol_normalized`（`mw_common.sha256_eol_normalized`，`packages/multi-workers/mw_common.py:2926` 附近）。
6. **应用（D-005）**：`apply_block_replace` = 行级 block replace（范式 `packages/multi-workers/mw.py:2054` `_replace_top_level_block`，但按**行号范围**而非 `key:` 头），写前**重算**目标行范围字节 sha 并与工单值比对，不等即 raise（不写盘）；原子写；返回新 sha256。
7. **验证执行（D-007）**：`run_verification` 用 `subprocess.run(cmd, shell=False, timeout=...)`，list argv；超时保留部分输出；原始 stdout/stderr 落 `run_dir`（append-only 文件 + 自锚 sha256），红数解析用 **pytest summary 行**（不要用 `mw_common.scan_build_error_lines`，那是 UE 专用）；返回 `{"stdout_path","sha256","red_counts"}`。
8. **证据包（AC-006）**：`evidence_bundle_write` 写 `evidence/<request_id>/`，五项 = old/new sha256、reason、`relaxed_assertion`(bool)、定向复跑命令与原始 stdout 路径、全量红数 before→after；**缺项不静默**（返回的 bundle 里标记缺失项，供 conductor 判 closed=False）。

## 验收

- `python -X utf8 -c "import autopilot.xkey"`（在 `packages/multi-workers` 下）干净。
- 自测脚本（写 `.tmp/xkey-selftest.py`，跑完删除）证明：① 10 字形解析（KV 命中 / 散文 None）；② `ledger_append` 同键两次 ⇒ rows 长度 1；③ 越界 proposal ⇒ `check_boundary == "violation"`；④ 正常 proposal ⇒ `apply_block_replace` 后文件 sha 变化且返回值 = 新 sha；⑤ 证据包缺一项 ⇒ 标记缺失。
- 无新外部依赖；纯标准库 + 仓内既有模块。

## 纪律

- **只写 `autopilot/xkey.py`**（+ 临时自测脚本）。不得改 `conductor.py` / `config.py` / 任何测试文件 / TS 文件。
- 不得 import conductor（避免循环依赖）。
- 不碰 `__pycache__` 之外的任何目录。

## 证据

报告须含：文件路径 + 行数、自测脚本输出（逐条 ①-⑤ 的真实输出）、`import` 检查结果、用到的 `mw_common` 锚点（file:line）。
