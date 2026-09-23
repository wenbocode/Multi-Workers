# Spec: mw-rag-window-parity — RAG 跨语言 parity 缺口 + pi 窗口内使用面

- key: `mw-rag-window-parity`
- created: 2026-09-23
- 规模: 小-中（TS 扩展改动 + 测试；Python 只读复用）
- 上游: `mw-rag-integration`（DONE）、`mw-rag-integration-fix`（DONE）、`mw-rag-config-guide`（DONE）

## 0 Goal Alignment

- **对齐 goal.md**：worker/PM 的 RAG 使用链路上有两处**收口缺口**——(1) 同一份配置在 Python 侧合法、在 worker 侧 TS 加载器非法（
  `skill.dir`），破坏「配置一次、两侧一致」的前提，进而可能让 worker 静默偏离 PM 的意图；(2) 用户与 PM 在 pi 窗口里
  无法查看/驱动 RAG（`/mw` 无 `rag`、`/mw doctor` 不显示 RAG 行），只能切终端，导致「配了但没人知道生效没有」——
  这正是 goal.md 要消除的「协调信息不可见」。
- **GC 检查**：GC-2（不修改 pi 核心）——只动 `packages/coding-agent/src/extensions/agent-team-loop/**`（扩展内）；
  GC-5（allowlist parity）——不改 worker 工具白名单/`REGISTRY`，`test_autopilot_l0.py` 必须零 diff；
  GC-1（无中心调度器）——`/mw rag` 只是 CLI 薄封装，不引入新调度路径；GC-7（goal.md 锚点）——本 key 不改 goal.md。
- **预期收益**：配置面「写一次、两侧同义」——不再出现「`mw rag list` 通过但 worker 侧加载失败」的静默分裂；使用面「窗口内可见可控」——PM/用户不必切终端即可确认 RAG 是否配置成功、服务是否可达、审计是否有 findings，把「配了但没人知道生效没有」从流程里移除。
- **依赖**：`mw_common.rag_fingerprint` 与 TS `ragFingerprint` 的字节等价契约（D-009/VC-022）是本 key AC-302 的直接对象；
  `/mw doctor` 的 RAG 数据已由 `mw.py:517`（`report["rag"]`）产出，本 key 只补渲染。

## 1. 问题

1. **跨语言不一致（R-1，`mw-rag-config-guide` 独立验证发现）**：
   - Python `mw_common._rag_finalize_skill`（`mw_common.py:551-559`）接受 `dir` 缺省或 `null`（语义 = 项目根）；
   - TS `rag/config.ts:260-270` 用 `requireString(raw.dir, …)` 要求非空 → 同一份 YAML 在 `mw rag list`（Python）通过，
     在 worker 侧 `loadRagConfig` 抛 `invalid-shape`；
   - 于是手册里「`dir` 可省略 = 项目根」的承诺在 worker 侧不成立（手册已如实标注为遗留，本 key 修实现）。
2. **pi 窗口内不可见/不可驱动（R-2）**：`/mw` 子命令白名单为 build/init/start/stop/restart/status/doctor/update/
   target/partition/model/ack（`pm/ui-bridge.ts`），无 `rag`；`formatDoctorReport`（同文件）不渲染已在 JSON 里的
   `report.rag`，因此 `/mw doctor` 看不到 `rag: enabled=…`。

## 2. 范围

**做**：
- TS 侧 `skill.dir` 与 Python 对齐（接受缺省/`null` = 控制工作区根），且**保持已锁定的跨语言 parity**（解析值仍为 `null`，
  仅在调用 CLI 处落到根目录），配套 TS 测试；
- pi 窗口 `/mw rag <list|probe|audit|sync|init> [args]` 薄封装（Python 仍是解析/校验唯一源）+ `/mw doctor` 增加 RAG 行 +
  `/mw` 帮助文本，配套可测的格式化/参数构造函数。

**不做**：pi 核心改动；任何 RAG 语义（工具集、熔断、预算、引用语法、注入块、fingerprint 算法）变更；
`mw_common.py` 与 `mw.py` 的既有行为变更（只读复用）；新增 RAG 工具或 `/mw rag` 之外的窗口命令；
worker 工具白名单/`REGISTRY`；真实 RAG 服务联调（沿用占位）。

## 3. 验收标准

| AC | 要求 |
|---|---|
| AC-301 | TS `loadRagConfig` 对 `skill` 块的 `dir`：**缺省**与 `null` 均合法（不再 `invalid-shape`），`RagSkillEntry.dir` 可表达 `null`；CLI 调用落在**控制工作区根**；`dir: "skills/x"` 仍按控制工作区解析；`dir: ""` 仍非法（与 Python 同）；`transport: skill` 时 `cli_entry` 缺失仍报 `skill-missing-cli` |
| AC-302 | 同一份配置（`dir` 缺省 / `null` / `"skills/x"` 三种）下，Python `rag_fingerprint` 与 TS `ragFingerprint` **逐字节相等**，且 `mw rag list --json` 与 TS 解析出的 `skill.dir`/`timeout_ms` 语义一致；parity 断言必须能在**未修改的** `test/fixtures/rag/*` 与 golden 上通过（golden 字节不变） |
| AC-303 | `/mw rag <sub> [args]`：`sub ∈ {list, probe, audit, sync, init}` 时以控制工作区为 `--project` 调用 `python mw.py rag <sub>`，把 stdout 呈现给用户；exit 0/1/2 分别映射为 info/warning/error 通知且不抛异常；未知名 → 打印用法（列出合法子命令）且不调用 CLI；`mw.py` 找不到 → 明确错误（含设置 `MW_PY` 的提示）；TS 不解析输出内容、不做参数语义校验（Python 为唯一源） |
| AC-304 | `/mw doctor` 在 `rag.exists` 为真**或** `rag.enabled` 非空时（与 `mw.py:523` 同一门控；`rag` 键缺失或项目完全未配置 RAG 时两侧都不打行）**多一行** RAG 状态行：`not enabled`（含 skill 状态）/ `ERROR - <detail>` / `enabled=<a, b>; probe=<name=reachable|unreachable, ...>（按名排序）; fingerprint=<前12位>; skill=<status>[; required_missing=N]`（`required_missing=0` 不追加），与 `mw.py:_format_rag_doctor_line` 逐字一致。 `REVISED @ 2026-09-23（T-3B 门控对齐 `mw.py:523`；Q-X-09）` |
| AC-305 | `/mw` 帮助文本包含 `rag`；`/mw rag` 的参数构造与 `/mw doctor` 的 RAG 行渲染都是导出函数并被测试覆盖（纯函数，无 I/O） |
| AC-306 | 零回归：`npm run check` exit 0；`extensions/agent-team-loop*` + `autopilot-*` TS 套件与 Python `pytest -q` 无新增失败；`test_autopilot_l0.py`、`test/fixtures/rag/*`、`test/fixtures/rag-block.golden.md` 零 diff；所有 `[VERIFY]` 行可由命令复现 |

## 4. 证据要求（L1）

- 每个 AC 至少一行 `[VERIFY]`，且**至少一个字段取自实测**（例如实测 TS 解析结果的 `dir` 值、实测 exit 码映射、
  实测 fingerprint 两串相等），不得只写布尔断言（AC-108 教训）。
- TS 侧：`[VERIFY]` 用 `process.stdout.write("…\n")`（vitest `silent: "passed-only"`，`console.log` 会被吞）；
  Python 侧沿用 `print` + `pytest -q -s`。
- 反例（由独立验证任务执行）：把 `rag/config.ts` 的 `dir` 改回 `requireString` → AC-301 必须红；
  把 `/mw rag` 的 `--project` 换成工作目录而非控制工作区 → AC-303 必须红；删掉 `formatDoctorReport` 的 rag 行 → AC-304 必须红。
  每条须还原并 sha256 自证。

## 5. 约束与红线

- 不改 `packages/coding-agent/src/core/**` 与 pi dist；不动 `packages/multi-workers/mw.py` / `mw_common.py` 行为。
- 不触碰其它会话的未提交改动（`mw.py`、`README.md`、`docs/`、`launcher.py`、`autopilot/*` 等）。
- 不提交；`dist/extensions/agent-team-loop.js` 只在必要时重建（如需重建，记录 sha256 与 `Self-check OK`）。
- 工具白名单：本 key 的 worker 用 coding 型（`read/write/edit/bash/find/grep/ls`）。

## 6. 风险

- **fingerprint 合约**：若把 `dir` 归一化成 `"."`，TS 与 Python 的 canonical JSON 会不同 → 必须保持 `null` 语义，
  只在 CLI 调用点落根目录（AC-302 专门钉住）。
- **`/mw` 输出体积**：`rag list`/`audit` 输出可能较长，通知通道可能截断 → 设计阶段确认展示策略（必要时截断 +
  指向终端命令）。
- **测试环境**：Windows 下子进程/编码（沿用 D-211 的 `encoding="utf-8"` 纪律）。

## 7. 可证伪假设

- H-1：TS 放宽 `dir` 为 `null` 后，`ragFingerprint` 仍与 Python 逐字节相等 → 若不等（说明 payload 里某处被归一化），
  必须改为「解析值保持 `null`、仅在调用点落根目录」，而不是改 payload；由 VC-305 直接证伪。
- H-2：`dir: ""` 在两侧都非法 → 若 TS 因 `optionalString` 把空串也当缺省，则 VC-303 会红（说明需要 `optionalString` 之外的判定）。
- H-3：`/mw rag` 只做转发即可满足使用需求 → 若用户在窗口里需要读回结构化结果（例如 audit 的 JSON），
  当前设计只能给文本 + 截断提示；由使用面的实测反馈证伪，届时再决定是否加 `--json` 展示模式。
- H-4：`formatRagDoctorLine` 照抄 Python 文本即可跨语言一致 → 由 VC-309 的三组 fixture 逐字比对证伪
  （任一不一致说明字段名/顺序/截断规则有偏差）。

## 8. 可复用资产

- `shared/mw-runner.ts` 的薄封装模式（`runMwCli` 追加 `--project=<dir>`、`findMwPy()` 支持 `MW_PY` 覆盖）→
  `/mw rag` 直接复用，不新增进程管理代码。
- `/mw target` / `/mw partition` / `/mw model` 的窗口分支与 `ctx.ui.notify(text, level)` 呈现模式（`pm/ui-bridge.ts`）
  → `/mw rag` 的参数转发与提示级别照此办理。
- Python 侧已就绪：`mw.py rag {init,list,probe,sync,audit}`（含 `--json`/`--key`/`--out`）与
  `mw.py:517` 已产出的 `report["rag"]`（`_doctor_rag`）→ 本 key **零新增 Python 行为**。
- 既有 parity 测试骨架 `test/suite/rag-parity.test.ts`（TS 侧与 Python 子进程取串比对）→ VC-305 直接扩展。
- fixture `test/fixtures/rag/{machine-servers.yml,project-servers.yml,target.yml,phase-only-target.yml}` 与
  golden `test/fixtures/rag-block.golden.md`（sha256 `00f85e64…4035`）作为零回归锚点（本 key 不改其字节）。
- 已锁定的纪律：`[VERIFY]` 用 `process.stdout.write`（vitest `silent: "passed-only"`）、子进程显式
  `encoding="utf-8"`（D-211）、证据行必须含实测数据（AC-108）。

## 9. 需规避坑点

- **fingerprint 是最容易踩的坑**：任何「顺手归一化」都会让 TS 与 Python 的 canonical JSON 不同，进而让
  `<!-- mw-rag: v1 -->` 里的 fingerprint 与 launcher 的判定不一致（`config tear (rag)` 拒 spawn）。VC-305 覆盖 `dir` 三种变体。
- **退出码语义**：`mw rag audit` 的 exit 1 是「有 findings」（预期内的 warning），exit 2 才是用法/配置错误；
  把两者混成一个 error 会误导用户（VC-308 钉住映射）。
- **输出体积**：`rag list`/`audit` 可能几十行，通知通道会截断 → 必须附「完整命令」而不是静默丢失（VC-308）。
- **`path.resolve(p, null)` 抛 TypeError**：不在解析层归一化的前提下，`cliCall` 必须走 `resolveCliDir`（VC-304 覆盖）。
- **测试环境**：Windows 下子进程/编码（显式 `encoding: "utf8"`）、`probe` 用不可达端口避免 5s 延迟与网络依赖。
- **白名单漂移**：`mw.py rag` 若新增子命令，TS 白名单会落后（本设计把白名单集中在一个常量；
  与 `_RAG_ACTIONS` 的一致性断言若成本高则记为遗留）。
