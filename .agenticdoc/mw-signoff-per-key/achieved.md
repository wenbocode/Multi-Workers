# achieved — mw-signoff-per-key

## 结案摘要

用户裁定：`dp25-signoff-conclusion` 不是某一个 key 的专属签收点，而是**任意 AgenticTask key 收尾**的通用决策点；并要求它落进 `.mw/decide-points.json`（唯一授权源）而不只靠注册表默认值生效。

本次把三处缺口补齐，行为从"本 key 专用 + 表里没有行"变成"任意 key 通用 + 表里有真实一行"。

## 系统行为变化

1. **签收点对任意 key 通用（不改语义，只固化与可审计）**
   - `decision_points.py` 的 dp25 `description` 改为"任意 key 收尾的签收结论（按 key 计算，替代人签）"，
     `q-conclusion` 的 `instructions` 首句改为"给出该 key 的收尾签收结论（任意 AgenticTask key 通用，key 由调用方传入）"。
   - 调用面不变但被明文化：`mw decide sign --key <key>` 或 `--project .agenticdoc/<key>`；state 的 `key` 来自调用方，
     `decide_signoff.collect(project, key)` 只折叠该 key 的档案行（新增用例证明另一个 key 的行不会串进来）。
   - `decide_registry.json` 的 dp25 `wiring_note` 补上"任何 key 的 on-demand CLI 调用方"与两种调用形式。

2. **授权表里出现真实一行**
   - `xkey-gate-guard` 不再拦 `mw decide dp refresh`：它是注册表→表的单向合并（`mw._dp_refresh` 只 append 缺失行，
     从不改已有 `enabled`/`mode`，P0/P1 缺行也是按注册表默认值补成关），因此不会放宽授权；
     `on|off|set|apply` 仍被拦（那才是翻开关、必须人来）。
   - 执行 `mw decide dp refresh --project .` 后 `.mw/decide-points.json` 从 24 行变 25 行，
     `dp25-signoff-conclusion = {tier: P2, enabled: true, mode: auto, note: ""}`，`updated_by: refresh`，
     并追加 `authority-change` 行（`by=refresh`、`change=add missing row dp25-signoff-conclusion`）。
   - `mw decide dp show --project . dp25-signoff-conclusion` 现在报 `source=config`（不再 `default`），
     `dp list` 仍是 `25 decision point(s), enabled=10, layer=OK`。

3. **守卫文案与文档**
   - `xkey-gate-guard.ts` 的说明文字改为"`on|off|set|apply` 写表行，`refresh` 只能补缺失的注册表行"，
     并把 `refresh` 从 `TABLE_WRITE_CLI_RE` 移出；`decision-signoff.test.ts` 增加两条 `refresh` 放行断言与一条
     `dp on ... --i-understand-p0` 仍拦的断言。
   - `docs/decision-points.md` 授权来源一节补 refresh 例外；dp25 段补"对任意 key 通用 + 已落表（source=config）"。
   - `flowcharts.md`/`flowcharts.html` §2.7 标题改为 `mw decide sign --key <任意 key>`（10 图 / 23 导航链接，结构校验 0 悬空锚点、0 U+FFFD）。

## 验证

- `pytest`：decision 相关 13 套件 **647 passed**（含新增 1 例跨 key 签收）。
- `vitest`：`decision-signoff.test.ts` + `xkey-gate-guard-coverage.test.ts` **25 passed**。
- `mw decide dp check --project .`：0 error / 0 warning；`gen_decide_registry_ts.py --check` rc=0；`dp export --write` 25 points / 3 wired。
- `tsgo --noEmit`（packages/coding-agent）：rc=0。
- `npm run check`：**rc=1**，3 warnings 全部落在别人会话正在改的 `packages/coding-agent/test/suite/mwoc-matrix-t07.test.ts`
  （useTemplate ×2、noUnusedImports、useOptionalChain，工作树中该文件未提交修改），本次触碰的 3 个文件 biome 干净。

## 遗留

- **运行期仍是旧 bundle**：`mw decide dp refresh` 的放行与 dp25 新文案要 `npm run build` + `/mw restart` + `/reload` 后才在 pi 会话里生效（命令行 `python packages/multi-workers/mw.py ...` 立即生效）。→ 待用户放话重建 `dist/**`。
- **本 key 的签收在表更新之后**：签收文件按 `counted_rows`/`rows_sha256`（档案口径）校验，与授权表 sha 无关，所以既有 `mw-decision-substitution` 签收仍然有效（`check_gate(done)` 复跑 True）。→ 无需重签。
- **`refresh` 的等价调用**：首次落表时运行中的 guard 是旧 bundle，实际是用等价的 in-process 调用（`mw._dp_refresh`）完成的；guard 改动落地并重建后，同一动作可直接用 CLI 跑。→ 记入本文件，重建后回归一次即可。
- **其他 21 个未接线 dp 是否补 `REQUIRED_STATE_FIELDS`**、**D-044（`ask_decision` 对 dp1/2/3 恒 `input-incomplete`）**、**`narrow` 结论是否据此收窄 dp1/dp3 的 mode** 仍是上一 key 留下的待用户裁定项。→ 不随本 key 处理。
