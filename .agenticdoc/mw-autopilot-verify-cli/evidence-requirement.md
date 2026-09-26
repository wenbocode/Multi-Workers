# Evidence Requirement: mw-autopilot-verify-cli

| 项 | 值 |
|---|---|
| spec_path | `.agenticdoc/mw-autopilot-verify-cli/spec.md` |
| spec_locked_at | 2026-09-26T05:40:00Z（v2，14 AC；U-1…U-6 经用户确认） |
| ac_fingerprint | `9c90fbb3e171`（算法：`sha1("\n".join(sorted(unique AC IDs)) + "\n")` 前 12 位；由 spec.md 机器抽取，14 条） |
| ac_ids | AC-001 … AC-014（14 条） |
| vc_ids | VC-001 … VC-016（design.md §7） |
| design | `design.md`（D-001…D-014，16 VC）+ `evidence/research/design-*-20260926.md` ×6 |
| plan | `plan.md`（波次按文件边界；契约冻结 §2；风险 R1–R12） |
| tasks | `tasks/T-01 … T-10` |
| generated_at | 2026-09-26T06:34:27Z |

## 逐 AC 判据标准（PASS 门槛与证据形态）

| AC | 机器判据 | 证据形态 |
|---|---|---|
| AC-001 | `mw autopilot verify set --project D -- --flag x` 后 `load_config(D)["xkey_verify_cmd"] == ["--flag","x"]`（flag 形 token 逐字）；`--project` 出现在 `--` 之后 ⇒ 报错且文件不存在/字节不变（VC-001/VC-002） | L1 测试（直调 + 子进程 argparse）+ 落盘字节 |
| AC-002 | 同参数二次 `set` 后文件 sha256 不变；规范化形状 = indent 2 / LF / 尾换行 / 13 键全量（VC-002） | L1 测试 + 前后 sha256 |
| AC-003 | 无 `os.utime`、不清缓存、**同字节长度**裸字节改写 ⇒ 下一次 `cached_load` 读到新值；对照 `mw.py` 1 s 复查读到新 `enabled`（VC-003） | L1 测试（含 stat 冻结使碰撞确定性）+ 反证（旧实现必红） |
| AC-004 | `show --json` 四键的 `origin ∈ {project, machine, default}`；三层 fixture 逐字段；文本含展开后 argv 与 cwd（VC-004） | L1 测试 + 文本快照 |
| AC-005 | `clear` 后其余 9 键值与字节形状不变、**文件仍存在**；无键时文件 mtime 不变（VC-005） | L1 测试 + 前后字节 |
| AC-006 | ≥12 payload 差分两侧结论一致（含 `4.0`/`4.5`/`1e2`/范围边界/partial/未知键）；跨侧写入 sha256 相同（含非 ASCII）；语料冻结 sha256 + 用例数（VC-006/VC-015） | TS vitest（`spawnSync` python，fail-closed）+ Python 半表 + 语料哈希 |
| AC-007 | 机器层 12 用例真值表：覆盖/缺失/非法/未知键 × value+origin+diagnostics；`MW_AUTOPILOT_FILE` 缺失 ⇒ 层空不回落；只读零足迹（VC-007） | L1 测试 + `[VERIFY]` 行 |
| AC-008 | `xkey_repair=true` + 空 argv ⇒ doctor JSON 机器字段 + 文本含 `mw autopilot verify set` + `healthy=false` + 退出码 1；timeline event == 1（重复不累加）；`xkey_repair=false` 或命令非空 ⇒ 无告警（VC-008） | L1 测试 + 真跑 `mw doctor` 输出 |
| AC-009 | (a) `git -c core.fileMode=false diff --exit-code -- packages/*/dist` 为空；(b) 陈旧产物 fixture ⇒ A1b stale、新鲜 ⇒ healthy，含"仅注释路径"反例；(c) A2b sourcemap 判据在 `181a75332` 形状上为红；(d) mock 断言 `_apply_update_env` S1 先 build 后 deploy，build 失败 ⇒ 不 deploy；(e) 脏树护栏（VC-009/VC-010/VC-012） | 命令输出 + fixture 断言 + mock 调用顺序 |
| AC-010 | 文档 fenced block 与真实 CLI `--help`/输出逐字节一致（照 `test_rag_docs.py:157-189` 先例）；指令矩阵/锚点表/两层表存在（VC-014 parity 部分） | 测试 + 文档评审行 |
| AC-011 | T1 持锁 ⇒ 返回 1 且目标字节不变、锁未被删；T2 "读在锁内" spy 断言；T3 释放后零残留；T4 两侧锁路径**同名**；T5 TS 侧对应用例（VC-011） | L1 两侧测试 + spy 断言 |
| AC-012 | `xkey_repair=false` 时既有 xkey e2e 全绿、行为逐字不变；默认套件相对基线 `b0a30bc12` 零新增失败（VC-016/VC-002） | 全套件输出 + 基线对照 |
| AC-013 | cwd 真值表 ≥18 行（`control≠partition≠parent` fixture、E2 形状、非法根名 fail-closed）；同族 5 锚点重锚断言（VC-013） | L1 真值表 + 反证（改回 project_root 必红） |
| AC-014 | 整元素占位替换 + 嵌入占位（`{partition}/tests`）fail-closed 且错误含原元素 + 未定义占位 fail-closed + toolchain parity 集全绿（VC-014） | L1 测试 + parity 集输出 |

## 不可回退约束（违反即 FAIL）

- `render_toolchain_command` 行为不变（由 `test_common_target_config.py` parity 集锁定）。
- `shell=False` 与 argv 原样语义不变；占位展开逐元素、不做 shell 分词。
- 项目层校验不得放宽（未知键/类型/范围 fail-closed）；机器层不得整份作废。
- 只读路径（`show`/doctor/conductor/dispatch）不得创建 `.mw/` 或任何目录。
- 跨语言判据对端解释器缺失 ⇒ 硬失败，禁止 `skipIf`/静默 skip（P-016）。
- 每条新用例必须附**非空洞对照**（反证：还原缺陷 ⇒ 该用例变红）。

## 证据包使用说明

`design.md` §7 定义全部 16 条 `[VERIFY] VC-NNN: k=v` 行；`achieved.md` 与 `/quality-gate` 报告逐条勾销。任一 AC 缺证据或证据形态不符即视为未达标。
