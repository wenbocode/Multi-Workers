# Plan: mw-rag-window-parity

- key: `mw-rag-window-parity`
- 依赖: spec.md（AC-301~AC-306）、design.md（D-301~D-310、VC-301~VC-312）
- 写入面纪律见 design.md §6：只允许改 4 个 TS 源文件 + TS 测试 + 两个 CHANGELOG `[Unreleased]`；**Python 零改动**。

## Stage 1 — 跨语言 parity（AC-301/AC-302）

| Task | 内容 | 产出 | Worker |
|---|---|---|---|
| T-1-SKILL-DIR-PARITY | `rag/config.ts`：`dir` 改 `optionalString`、`RagSkillEntry.dir: string \| null`；`rag/tools.ts`：新增 `resolveCliDir(controlRoot, dir)` 并在 `cliCall` 使用；测试 VC-301~304（新 `test/suite/rag-window.test.ts` 的 parity 部分）+ VC-305（扩 `rag-parity.test.ts`，`dir` 三种变体对比 Python `rag_fingerprint`） | 代码 + 测试 + `[VERIFY]` | coding worker |

退出条件：VC-301~305 全绿；`rag-*` 与 `agent-team-loop*` 套件无新增失败；`test/fixtures/rag/*`、`rag-block.golden.md` 零 diff。

## Stage 2 — 窗口内使用面（AC-303/AC-304/AC-305）

| Task | 内容 | 产出 | Worker |
|---|---|---|---|
| T-2-MW-RAG-CMD | `shared/mw-runner.ts`：`runMwCliRaw`（暴露 `code`）+ `ragMw` + 子命令白名单常量；`pm/ui-bridge.ts`：`parseRagArgs` / `formatRagOutput` 纯函数 + `/mw rag` 分支 + help 文本含 `rag` | 代码 + 测试（VC-306~308、VC-311） | coding worker |
| T-3-DOCTOR-RAG-ROW | `shared/mw-runner.ts`：`DoctorJson.rag?`；`pm/ui-bridge.ts`：`formatRagDoctorLine` + `formatDoctorReport` 插入一行 | 代码 + 测试（VC-309、VC-310） | coding worker |

约束：T-2 与 T-3 都改 `pm/ui-bridge.ts` → **串行**（T-3 在 T-2 之后）；T-2 可与 T-1 并行（文件不相交）。

退出条件：VC-306~311 全绿；`/mw doctor` 的 `rag:` 行与 `mw.py doctor` 文本行逐字相等（三组 fixture）。

## Stage 3 — 独立验证（AC-306）

| Task | 内容 | 产出 | Worker |
|---|---|---|---|
| T-4-VERIFY | 第三方复现 VC-301~312；三条反例（`optionalString`→`requireString`、`--project` 用错根、删掉 doctor 的 rag 行）必须变红并 sha256 复原；零回归；「设计文档/手册与实现一致性」抽查 | `evidence/verify-run-*.md` | coding worker（独立） |

退出条件：报告含逐 VC 表 + 反例记录 + 零回归 + 未覆盖项；除报告外不改文件。

## 依赖与顺序

```
T-1 ─┐
     ├─→ T-3 ─→ T-4
T-2 ─┘
```

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 归一化 `dir` 破坏 fingerprint（D-301/D-304 的坑） | VC-305 直接用 Python 实跑取串比对；反例 1 覆盖 |
| 通知通道截断长输出 | `formatRagOutput` 截断 + 附完整命令（VC-308） |
| `/mw rag` 与 `mw.py` 子命令集漂移 | 白名单集中在一个常量，`ragMw` 只转发；漂移记为遗留并给出检测断言 |
| 两个 worker 同时改 `ui-bridge.ts` | T-2/T-3 串行；T-1 只碰 `rag/*.ts` 与 `rag-parity.test.ts` |

## 交付节奏

1. 推 T-1 ∥ T-2 → PM 回读 + 自验（跑指定 suite）；
2. 推 T-3 → PM 回读；
3. 推 T-4（独立验证）→ PM 写质检报告 + achieved.md → 推进 DONE。
