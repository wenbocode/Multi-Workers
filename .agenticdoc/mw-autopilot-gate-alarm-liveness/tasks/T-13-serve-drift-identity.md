# T-13 — serve 身份与漂移自检（`code_digest` 判据 + 4+1 新鲜进程侧入口）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-005, AC-006
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/design.md` §2 D5、§3；
      `evidence/research/design-drq3-drift-selfcheck-20261013.md`、`spec-rq3-serve-metadata-drift-20261013.md`

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（链路自证能力）。
- 已核实锚点（自行复核）：
  - `packages/multi-workers/mw.py:85`（`_write_pid`）、`:122-131`（`_write_serve_meta`，非原子写，字段 `pid/started_at_ms/code_dir`）、`:271`（`_write_pid(pid_path)`）、`:273`（`_write_serve_meta(project_dir)`）⇒ **采集必须前置到 `:271` 之前**，否则一次挂死的 git 会留下"PID 在、服务没起"的假象。
  - `:4097`（`_git()`，今日**无** `timeout`/`CREATE_NO_WINDOW`）、`:5188`（`_git_head_short` 走 `rev-parse --short HEAD` ⇒ **动态长度短 OID**，与 40 位 OID 字面永不相等）、`:5175`（`_git_dirty`）、`:5131`（`_mw_code_newest_mtime`，判据是 `f.name.startswith("test_")` **basename** ⇒ 不跳 `test/` 目录）。
  - `:5362-5390`（serve.meta 读点）、`:5112`（`mw update-env` A3）、`:4354`（`_framework_version`）。
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:195-330`（TS 侧 staleness：`:224-256` 纯 mtime 判据；`doctorMw` 在 `:414`）。
- 关键事实：本机 71 个 runtime 文件里 **49 个（69%）是 `test/` 夹具**（改夹具会把健康 serve 判 stale）；纯 commit 判据在"把 dirty 树提交掉"时**假漂移**（本仓 `packages/multi-workers` 今日即 dirty）；保留窗口实测 **12.8 天 < 漂移 16.98 天**（当年告警也已滚出）。

## 要求

1. **`serve.meta` 身份字段**：新增 commit / dirty / `code_digest`（runtime 文件集 sha256，权威判据）/ `schema`；写入保持/改为原子；旧 meta 必须兼容（缺 `schema` 等价 `schema=0`）。
2. **采集整体前置到 `_write_pid` 之前**（`:271`），并对所有子进程调用补 `timeout` + `CREATE_NO_WINDOW` + None 降级（`_git():4097` 今日两者都缺）。
3. **commit 采集不得复用 `_git_head_short` 的短 OID 形态**：比对用可稳定比较的形态（纯文件读 `.git/HEAD` → loose → `packed-refs` 给 OID；或统一到同一长度），否则永久假漂移。
4. **比对与告警**：启动 + 每 tick 比对；漂移 ⇒ 告警含期望/实际 + 漂移时长 + 修法 `/mw restart`；告警走既有双通道（stderr + timeline `config`），限频键 `(code_dir, meta_commit, head_commit, serve_pid)`；**`code_digest` 相等而 commit 不等 ⇒ 只记 `history-only`，不告警**（D-009）。
5. **skip 集加目录名 `test`**（两侧：Python `_mw_code_newest_mtime` 与 TS 等价物），避免改夹具误判 stale。
6. **4+1 新鲜进程侧入口**：`mw status` / `mw doctor`（drift ⇒ issue，exit 语义与 TS `doctorMw` 兼容）/ `mw update-env` A3（基线改 `meta.code_dir`）/ TS `serveStaleness`；可选 OS 探针（ctypes `GetProcessTimes`）。**至少一个入口不依赖运行中的 serve**。
7. **机器可检的"必须重启"**：`meta.schema < EXPECTED_SCHEMA` 即判"必须重启 serve"。
8. **分工不重复**：TS 侧不新增周期通知（只保留交互恢复）；Python **不自动重启**。

## 写入允许面

- `packages/multi-workers/mw.py`
- `packages/multi-workers/test_mwgal_t13_drift_identity.py`（新增）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`（仅 skip 集与入口对接，不改 staleness 判据语义）
- `packages/coding-agent/test/suite/mwgal-t13-drift.test.ts`（新增）
- 既有测试中因新字段/新 meta 形态而必须更新的**夹具数据**（不改判据）

## 写入禁止面

- `packages/multi-workers/autopilot/**`（属 T-10/T-11/T-12/T-14/T-16）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/**`、`pm/**`（属 T-10）
- 其他 key 目录、其他项目仓库只读（`E:\CLI_workspace\FeatureMigrator\.mw\` 只作只读参考）

## 验收命令

从 `packages/multi-workers`：`python -m pytest test_mwgal_t13_drift_identity.py test_update_env.py -q`
从 `packages/coding-agent`：`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t13-drift.test.ts`

## 改动历史

（填写：`serve.meta` 字段演化、为什么判据换成 `code_digest`、`_write_pid` 前置的理由。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
