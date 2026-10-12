# T-02 — AC-005a：派发期可满足性校验（写意图判定）+ 写面契约段与 `write_scope` 头

- key: `mw-dispatch-settle-gates`｜AC: **AC-005a**｜VC: **VC-015…VC-019**｜波次 **2**｜链 1（依赖 T-01 的 `writeDispatchTaskMd` 单点）
- 角色: coding
- **唯一允许改的路径**：① `pm/ui-bridge.ts`；② 新建 `packages/coding-agent/test/suite/mwds-t02-write-intent.test.ts`；③ 自身目录 `report.md`
- 上游：`plan.md §4` 契约 **C1/C2/C3/C4**；`design.md` DD-02/DD-04；证据 `evidence/research/design-write-surface-20261010.md`（判定规则与语料实测）

## 必须实现
1. **角色能力判定（C3）**：从 `activeToolsForType` 取 `{canWrite: write|edit, canShell: bash}`。`canWrite` ⇒ **完全放行**（编码类零影响，不得产生任何新提示语）。新增导出 `isWritelessRole(type)` / `isShellRole(type)` 供 T-03 复用。
2. **写意图判定（仅 `!canWrite`）**：形式 = `(写动词) … (路径)`，路径须在动词后 ≤32 字符；命中且路径不在白名单 ⇒ 候选违规。写动词表：`写入|写到|写到文件|落盘|输出到|保存|创建|生成|追加|覆盖|write|save|create|append|output to|into`（可扩展，须测试可枚举）。
3. **5 类护栏（任一命中 ⇒ 放行）**：① 否定（`不要|不得|禁止|never|do not|don't` 紧邻动词前）；② 读标记（`读取|作为输入|参考|from|input|以…为输入`）；③ fenced code block 内（``` 块）；④ 引语复述（`"…"`/`「…」`/`'…'` 包裹）；⑤ PM 归因（`PM 会|由 PM|PM 收录|框架会|交给 PM`）。
4. **白名单**：`worker_file` 的 `WORKER_FILE_NAME_RE` basename（`progress.md`/`report.md`/`report-<slug>.md`）、自身 taskDir 相对路径、框架自有文件名（`task.md`/`trace.log`/`output.md`/`run.json`/`worker.log`）。**注意**：`output.md` 在白名单里只表示"引用合法"，语义见下条。
5. **拒绝形态**：`!canWrite && !canShell` 且候选违规 ⇒ `ctx.ui.notify(<修正后的任务书怎么写>, "warning")` + `return`，**在任何 mkdir/写盘/入队之前**（与 T-01 的守卫同层）。逃生阀：frontmatter `allow_foreign_write: true` ⇒ 放行，并在 task.md 注入 `allow_foreign_write: true`（审计可见）。
6. **规格与语料口径**：`!canWrite && canShell`（= `research`）**不拒**，只注入契约段 + `write_scope` 头（写面收窄由 T-03 运行期执行）。
7. **契约段注入（C2）**：成对 marker `<!-- mw-write-surface: v1 -->` … `<!-- /mw-write-surface: v1 -->`，紧随 frontmatter 之后，段内固定 3 行：允许写 / 不得写 / 越界后果。幂等：已含 marker ⇒ 字节相等则不动、不等则整段替换；断言 marker 计数恒 1。
8. **`write_scope` 头（C1）**：与既有 `read_scope:`/`deny_globs:` **同渲染器、同语法**；`research` 角色默认写入 `write_scope: .agenticdoc/<key>/workers/<taskKey>, .agenticdoc/<key>/evidence`（缺省不生成该行，绝不生成空值行）。渲染必须走 T-01 的 `writeDispatchTaskMd`。

## 反向用例（必须真跑；语料回归是硬要求）
- **(a) 语料回放（硬判据）**：对 `.agenticdoc/*/workers/*/task.md` 全部任务书跑判定；`!canWrite && !canShell`（= 24 份 review 类）⇒ 命中 ≤2，且经白名单后 **0 假阳性**（唯一真阳性 = `mw-gate-verdict-hardening/workers/mwg-qg-review-20261010`）。把回放数打印进报告。
- (b) 5 类护栏各一条正例不拒（否定/读标记/代码主体/引语/PM 归因）。
- (c) `coding` 类角色：带外部写要求的任务书仍放行（零影响）。
- (d) 幂等：同一任务书注入两次 ⇒ marker 计数 1、字节不变。
- (e) `allow_foreign_write: true` ⇒ 放行且该键出现在落盘 task.md 中。

## 对照协议（`plan.md §5`）
A 摘除写意图判定 ⇒ (a) 的拒绝用例转红；B 反转默认（违规即放行）⇒ 同上转红；C 移除 5 类护栏之一 ⇒ 对应用例转红（说明假阳性来源）。每组贴 sha256 → 逆改 → 红 → 还原 → 绿。

## 证据
```
[VERIFY] VC-015: corpus=286 read_only_books=24 hits=<=2 false_positives=0
[VERIFY] VC-016: read_input_case=allow
[VERIFY] VC-017: coding_roles_affected=0
[VERIFY] VC-018: guards=5 each_allows=true
[VERIFY] VC-019: marker_count=1 idempotent=true
```
命令：`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t02-write-intent.test.ts`

## 禁止
不改 `pm-orchestrator.ts` / `worker-mode.ts` / `shared/worker-store.ts`；不改大测试文件 `test/extensions/agent-team-loop.test.ts`；不 build；不 commit；不跑全量套件 / `npm run check`；不动其他 key 的目录或进程。
