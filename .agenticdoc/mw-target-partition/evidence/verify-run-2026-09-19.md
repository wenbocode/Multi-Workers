# Verify Run: mw-target-partition S4 (T-10 / T-11)

## 1. 头部

- 日期: 2026-09-19
- HEAD: `67e70a8c8` (branch `dev/AgentTeam`; S1~S3 交付为未提交工作区改动，本 run 在其上执行)
- Py 全量: `python -m pytest -q` → `660 passed, 8 deselected in 54.93s` (exit 0)
- Py 目标族提取运行 (`--capture=tee-sys`, 6 个目标文件): `198 passed in 13.33s` (exit 0)
- TS 全族: `node ..\..\node_modules\vitest\dist\cli.js --run test/extensions/` → `Test Files 8 passed (8)` / `Tests 377 passed (377)` (exit 0)
- `npm run check` (repo 根): exit 0 — biome 1052 files no fixes/no findings; check:pinned-deps / check:ts-imports / check:shrinkwrap / check:install-lock:coding-agent / tsgo --noEmit / check:browser-smoke 全过

提取方法备注: vitest 配置 `silent: "passed-only"`，TS 运行加 `--silent=false` 提取 console 行；pytest 侧 `--capture=tee-sys` 下 `_parity_marker()` 的输出被 `capsys.readouterr()` 先消费（tee 不会回放已消费的 buffer），`[PARITY] target-config cases=39` 一行改为直接调用测试模块自身的 `_parity_marker()`（同一代码路径、同一 fixture 目录）提取，其余 [VERIFY] 行均取自真实测试运行输出。

VC 编号碰撞备注: 旧 key（mw-dual-workspace / autopilot / launcher 族）复用 VC-00x 编号（如 agent-team-loop.test.ts 主 describe 的 VC-001~011、test_mw_target.py 的 VC-010）。本表只引用 mw-target-partition key 的行，逐条标注来源文件。

## 2. VC 覆盖表

| VC | 结论 | 证据来源 |
|---|---|---|
| VC-001 v2 partition 13 字段 parity | PASS — 双侧同一 39-case 共享夹具集全绿，partition 字段（parent_root/partition_root/roots/vcs/legacy null 形态）逐字段断言 | `[PARITY] target-config cases=39: 001…039` Py 与 TS 输出完全一致（含 015-v2-partition-roots、017-v2-dual-block、026-v2-top-whitelist 等）；Py 660 / TS 377 全绿。（runner 同时打印的旧 key `VC-001: mode=single roots-equal=true (case 001)` 属 mw-dual-workspace 编号，仅佐证 case 001 本身未变） |
| VC-002 缺字段/缺块 → invalid-config 含字段/块名 | PASS | cases 020-v2-missing-block、021-v2-partition-missing-field、039-v2-dual-missing-block 在双侧 runner 内断言 error.kind=invalid-config 且消息含字段/块名（39-case 运行内通过） |
| VC-003 结构层 7 类 → invalid-config 含要素 | PASS | cases 018 (mixed format)、019 (bad active)、022/023 (partition/dual bad block key)、024 (roots reserved key)、025/036 (root relation equal/nested)、026 (top whitelist)、037/038 (roots bad chars/empty key) 双侧通过 |
| VC-004 占位符 mode 分派；未知 token missing-field；dual 零变化 | PASS | cases 015 ({parent}/{partition}/{sdk} 渲染)、034 (partition render 缺根 → missing-field)；case 003 dual 渲染零变化（双侧 `VC-006: rendered-contains-engine=true unresolved-placeholders=0`，旧 key 编号）+ S0 golden 双 MATCH（渲染字节锁定） |
| VC-005 EP 覆盖 + source 3 枚举 + 空白=未设置 | PASS | cases 027 (partition env override)、028 (空白=未设置)、029 (env 无文件激活 source=env)、030 (env 不齐 → error)、031/032/035 (交叉 env 报错)、033 (dual env game)；source 枚举逐 case 断言，双侧通过 |
| VC-006 spawn cwd=partition root；trace/output 写回控制根 | PASS | Py `[VERIFY] VC-006: spawn-cwd=…\test_worker_cwd_partition_root0\shard` (test_partition_dispatch.py)；`test_spawn_partition_cwd_and_control_anchored_task` 断言 trace/output 锚定控制根 |
| VC-007 PROFILE_MARK v2 块（模式行）注入幂等 | PASS | TS `[VERIFY] VC-007: profile_block=present, mode_line=partition` (agent-team-loop-profile-injection.test.ts:363)；partition describe 6/6 通过（含 same-mode re-dispatch byte-identical 幂等） |
| VC-008 read_scope 锚定 partition + control 追加；不并 parent | PASS | Py `[VERIFY] VC-008: scope=[shard\src, shard\docs\readme.md, outside, control]` — 分片根锚定 + control 追加，parent 不在 scope；`test_partition_no_duplicate_control` / `test_dual_single_unchanged` 锁定不回归 |
| VC-009 doctor checks + 指纹重探测 | PASS | Py `[VERIFY] VC-009: checks=[parent_root,partition_root,root:*]` + `[VERIFY] VC-009: reprobe=on-fingerprint-change (env overlay)`；`test_active_switch_reprobes` / `test_old_cache_without_fingerprint_reprobes_once`；E2E 步骤 e doctor JSON 印证（checks 全 ok、probe_cache=probed） |
| VC-010 set exit 0 落盘 / v1 迁移 .bak / 拒绝路径文件不变 | PASS | Py: `VC-010: exit=0, mode=partition, omitted-fields=not-persisted`、`default-partition=control-root-absolute`、`roots+vcs persisted, relative-roots=control-anchored`、`exit=1 missing-paths, yml=unchanged`、`exit=1 root-relation, yml=unchanged`、`exit=1 cross-env ×4, no-migration no-bak`、`migrated=v1-to-v2, bak=complete, content=preserved`；E2E 步骤 a/b/f 实机印证（见 §4） |
| VC-011 缺参 exit 1 / clear 删块 / 无块删文件 / 块缺失 exit 0 | PASS | Py `[VERIFY] VC-011: exit=1 missing-parent, file=unchanged` + `[VERIFY] VC-011: clear=block-removed, no-blocks → file deleted` |
| VC-012 /mw partition 透传字节一致 + 转发一致 | PASS | Py `[VERIFY] VC-012: set-output=deterministic (forwarded vs direct runs identical)` (test_mw_partition.py，转发路径与直连 CLI 输出逐字节一致)；TS `/mw partition (partition-workspace config)` describe 6/6 通过（show/clear/on/off 转发、set 引号路径+重复 --root 的 flag 语法顺序、缺 --parent usage、flag 缺值 usage、未知 verb usage、runner 失败通知） |
| VC-013 零回归：全绿 + 既有用例零修改 + check 0/0/0 | PASS | Py 660 / TS 377 / `npm run check` exit 0；fixture 001~014 零修改；既有测试删行仅 harness 容差（见 §3）；Py `[VERIFY] VC-013: target-set-on-v1=v1-flat-format (zero change)`（v1 路径零改动） |
| VC-016 基线 golden 逐字节一致 | PASS | Py: `[BASELINE] MATCH: test\golden\target-baseline\dual.json` / `…single.json` + `VC-016: baseline_dual=identical` / `baseline_single=identical`；TS: `[BASELINE] MATCH: golden/target-baseline/dual.json` / `…single.json` + 同两条 VC-016 identical 行。双侧四项全 MATCH（golden 为 S0 录制，非本次重录） |
| VC-017 规则表全枚举 parity，行 5 不解析、行 8 零变化 | PASS | 双侧 `[PARITY] active-mode table cases=112 rows=2,3,5,6,7,8,9,10,11,12` + Py `[VERIFY] VC-017: table=rows-2-12 (rows 1/4 via entry tests + fixtures), parity=py-side` + TS `…parity=ts-side`（行 1/4 由入口测试覆盖） |
| VC-018 active 感知：守卫互斥 / 模式行 / partition-only 键 / 指纹随切换失效 | PASS | 守卫: Py `[VERIFY] VC-018: guard=exit-1 (target show → mw partition show)` + E2E 步骤 g 实机印证；模式行: TS VC-007 `mode_line=partition`；partition-only doctor 键: E2E 步骤 e（parent_root/partition_root/roots 键、无 engine/uproject 探测）；指纹失效: `test_active_switch_reprobes` + VC-009 reprobe 行 |
| VC-019 切换后 profile 整体替换；同配置字节不变 | PASS（describe 断言覆盖，无专用 [VERIFY] 行） | agent-team-loop-profile-injection.test.ts `partition profile injection (mw-target-partition AC-007/AC-019)` describe 6/6: `AC-019: active switched to dual → block replaced wholesale (marker to EOF)`、`AC-019: v1-marked legacy block is replaced under partition activation`、`AC-019: active switched to single → stale block stripped, file byte-restored`、`same-mode re-dispatch is byte-identical (idempotent)`、`dual injection keeps the v1 marker and no mode line (AC-016d zero change)`。（输出中 `VC-019` 行属 autopilot timeline key，非本 key） |
| VC-020 撕裂 → failed "config torn"，不 spawn | PASS | Py `[VERIFY] VC-020: task=failed, reason=config_torn, spawned=no` (test_partition_dispatch.py: `test_torn_partition_block_under_dual` / `test_torn_v1_dual_block_under_partition`)；`test_single_injected_v1_block_not_torn` 锁定 v1 块按 Game root 行判 mode 的防误判（见 §5 偏差 2） |
| VC-022 set 幂等 / 手维护段保留 / 原子替换 / .bak 完整 | PASS | Py `[VERIFY] VC-022: preserved=pass (hand sections + comments byte-identical)` + `idempotent=pass (fresh + migrated paths)` + `atomic=pass (replace-failure → file intact, no residue)`；E2E 步骤 f 实机印证（.bak 440/440 字节完整，dual 块原字段保留） |
| VC-023 on/off 翻转 / 块缺失 exit 1 / v1 报错 / 转发一致 | PASS | Py `[VERIFY] VC-023: on=active-flip, off=single-parked, block=kept` + `[VERIFY] VC-023: target on/off symmetric (v2 flip/park, v1 exit-1)`（v1 报错由 `test_on_off_reject_v1` / `test_target_on_off_symmetric` 断言 exit 1 + "v1 format" 提示）；E2E 步骤 d 实机印证 |

E2E 冒烟的 [VERIFY] 汇总行（对应 VC-010/016/018/022/023）：

```
[VERIFY] VC-010: e2e set exit=0, yml active=partition, fields=parent/partition/vcs/roots.sdk, dual-block=absent
[VERIFY] VC-010: e2e v1-migration exit=0, bak=440B-byte-complete, dual-block-fields=preserved, default-partition=control-root
[VERIFY] VC-016: baseline dual/single golden MATCH on both sides (from T-10.1/2 runs, not E2E)
[VERIFY] VC-018: e2e target-show guard exit=1, hint=mw partition show; doctor partition-only keys present
[VERIFY] VC-022: e2e hand-sections (toolchain/ignore/contract/game/engine/vcs) preserved in dual block, comments intact
[VERIFY] VC-023: e2e off→active=single (partition block kept), on→active=partition
```

## 3. 零修改审计（AC-013 红线核验）

### 3.1 fixture 目录

`git status --short -- packages/multi-workers/test/fixtures/target-config-cases`：仅 `??` 新增目录 015~039（25 个），既有 001~014 **零修改**（无任何 M/条目）。结论：**PASS**。

### 3.2 既有测试文件 numstat 与删行逐条归类

| 文件 | +/− | 删行内容 | 归类 |
|---|---|---|---|
| `packages/multi-workers/test_common_target_config.py` | +27/−1 | `out = out.replace("{game_root}", config["game_root"])` → `config["game_root"] or ""` | harness 空值容差（or "" 容差）— 允许 |
| `packages/coding-agent/test/extensions/agent-team-loop-target-config.test.ts` | +67/−5 | ① `vcs?: string;` → `vcs?: string \| null;` ② `config.gameRoot` → `config.gameRoot ?? ""` ③ `discoverUproject(config.gameRoot, …)` → `discoverUproject(config.gameRoot as string, …)` ④⑤ `expect(config.gameRoot/engineRoot).toBe(fs.realpathSync.native(path.join(…)))` → `expectRoot(…)`（realpath 失败时回退最长存在前缀的规范化，镜像 Py `Path.resolve(strict=False)`） | ①② 为空值容差（?? null 容差）；③④⑤ 为同一容差的必然涟漪（gameRoot 可空后的调用签名/存在性回退）。既有 case 001~014 的目录均存在，`expectRoot` 走 realpath 分支与原表达式逐字节等价；断言语义零变化 — 允许 |
| `packages/coding-agent/test/extensions/agent-team-loop-profile-injection.test.ts` | +253/−0 | 无删行（纯新增 partition describe，既有 `workspace profile injection (mw-dual-workspace AC-007)` describe 7 用例零改动） | 允许 |
| `packages/coding-agent/test/extensions/agent-team-loop.test.ts` | +94/−0 | 无删行（纯新增 `/mw partition` describe） | 允许 |
| `packages/multi-workers/test/test_target_baseline.py` | 新增文件 | 本 key S0 交付（例外，不在既有清单内核验） | — |
| `packages/multi-workers/test_mw_target.py`（mw_target 相关既有测试） | 0/0 | 未出现在 `git status` 修改列表 | 零改动，PASS |

结论：既有测试的 6 处删行全部属于 runner 空值容差（or ""/?? null）及其类型/存在性回退涟漪，**无断言语义修改**。**PASS**。

### 3.3 既有源码/产物改动 vs S1~S3 报告清单

`git diff --numstat`（全部跟踪文件）与 S1~S3 交付清单一一对照：

| 改动文件 | 归属 |
|---|---|
| `packages/multi-workers/mw_common.py` (+501/−29) | S1 T-01（解析层）+ S2 T-06（doctor/缓存）— 清单内 |
| `packages/coding-agent/src/…/shared/target-config.ts` (+465/−35) | S1 T-02 — 清单内 |
| `packages/multi-workers/test_common_target_config.py` (+27/−1) | S1 T-03 runner 增量字段 — 清单内 |
| `packages/coding-agent/test/extensions/agent-team-loop-target-config.test.ts` (+67/−5) | S1 T-02/03 — 清单内 |
| `packages/multi-workers/test_active_mode.py`、`packages/coding-agent/test/extensions/agent-team-loop-active-mode.test.ts`、`test/fixtures/active-mode-table.json` | S1 新增（??）— 清单内 |
| `test/fixtures/target-config-cases/015~039` | S1 T-03 新增（??）— 清单内 |
| `packages/coding-agent/src/…/pm/task-dispatcher.ts` (+136/−7) | S2 T-04 — 清单内 |
| `packages/coding-agent/test/extensions/agent-team-loop-profile-injection.test.ts` (+253/−0) | S2 T-04 新 describe — 清单内 |
| `packages/multi-workers/test_partition_dispatch.py` | S2 T-05/06 新增（??）— 清单内 |
| `packages/multi-workers/launcher.py` (+101/−12) | S2 T-05 — 清单内 |
| `packages/multi-workers/autopilot/dispatch.py` (+18/−10) | S2 T-05 — 清单内 |
| `packages/multi-workers/mw.py` (+934/−9) | S3 T-07 — 清单内 |
| `packages/multi-workers/test_mw_partition.py` | S3 T-07 新增（??）— 清单内 |
| `packages/coding-agent/src/…/pm/ui-bridge.ts` (+94/−6)、`shared/mw-runner.ts` (+6/−1) | S3 T-08 — 清单内 |
| `packages/coding-agent/test/extensions/agent-team-loop.test.ts` (+94/−0) | S3 T-08 新 describe — 清单内 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` (+494/−68) | S3 T-09 bundle 重建 — 清单内 |
| `packages/coding-agent/dist/extensions/…`（task-dispatcher/ui-bridge/mw-runner/target-config 的 .d.ts/.js/.map） | S3 T-09 `--install` 对齐 coding-agent dist — 清单内 |
| `packages/multi-workers/test/test_target_baseline.py`、`packages/coding-agent/test/extensions/agent-team-loop-baseline.test.ts`、`test/golden/`、`test/extensions/golden/` | S0 T-00 新增（??）— 清单内 |
| `.agenticdoc/_index.md` (1/1)、`.agenticdoc/_index.parallel` (2/0) | PM/框架簿记（worker 注册表），非 src/test 实现改动 — 预期 |
| 未跟踪且与本 key 无关: `.agenticdoc/mw-provider-routing/`（另一 key 工作目录）、`docs/zai_guider.md`（外部文件） | 非本 key 交付，不计入清单对照 |

结论：**无超出 S1~S3 报告清单的实现改动。PASS。**

## 4. E2E CLI 冒烟记录（真实 subprocess，临时目录 `%TEMP%\mwtp-s4-e2e`）

布局: `ctrl\`（控制根）、`parent\`（独立父目录）、`shard\`（独立分片目录）、`sdk\`（命名根）、`ctrl-v1\`（v1 迁移控制根）。运行目录 `packages/multi-workers`，逐命令记录 exit code。

| 步 | 命令 | exit | 关键输出/断言 |
|---|---|---|---|
| a | `python mw.py partition set --project …\ctrl --parent …\parent --partition …\shard --root sdk=…\sdk --vcs git` | **0** | `[mw partition] mode: partition (source: target-yml)` + parent/partition/sdk/vcs 摘要行 |
| b | 读 `ctrl\.agenticdoc\target.yml` | — | `active: partition`；partition 块: `parent:`/`partition:`/`vcs: git`/`roots.sdk`；**无 dual 块**；模板含 toolchain/ignore/contract 注释脚手架 |
| c | `python mw.py partition show --project …\ctrl` | **0** | 同摘要（mode: partition (source: target-yml)、parent root/partition root/root sdk/vcs 行） |
| d | `python mw.py partition off` → 读 yml → `python mw.py partition on` → 读 yml | **0 / 0** | off: `[mw partition off] active: single (partition block kept…)`，yml `active: single` 且 `partition:` 块保留（parked）；on: `[mw partition on] active: partition…`，yml `active: partition` |
| e | `python mw.py doctor --json --project …\ctrl` | **1**（见注） | target 段: `mode: partition (source: target-yml)`、config 含 `parent_root`/`partition_root`/`roots.sdk` 键（game_root/engine_root/uproject 为 null，无 engine/uproject 探测）；checks = `parent_root`/`partition_root`/`root:sdk` 全 `ok: true`；`probe_cache: "probed"`。exit 1 唯一 issue = `mw service not running`（裸临时控制根无 mw 服务，环境性、与 target 段无关；另有 orphan-proxy/credentials 建议） |
| f | `ctrl-v1` 预置 v1 flat target.yml（mode: dual + game/engine/vcs: p4 + toolchain/ignore/contract 手维护段）→ `python mw.py partition set --project …\ctrl-v1 --parent …\parent --vcs git`（省略 --partition） | **0** | `migrated v1 target.yml to v2 (all v1 fields moved into the dual block); backup: …target.yml.bak` + 摘要（partition root = 控制根绝对路径，默认展开）。`.bak` 存在且与原 v1 文件逐字节相等（440/440 bytes）；迁移后 yml: `active: partition`、`dual:` 块含原 game/engine/vcs: p4/toolchain(build,cook)/ignore.deny_globs×2/contract(forbidden_paths, conventions, docs)、`partition:` 块就位（parent + partition=ctrl-v1 + vcs: git） |
| g | `python mw.py target show --project …\ctrl`（active: partition 下） | **1** | stderr: `[mw target show] Error: active mode is partition — use \`mw partition show\` (partition fields are not part of the target/dual view)` |

步骤 e 后 target 段 JSON（节选）:

```json
{
  "yaml_available": true,
  "config": {
    "mode": "partition", "source": "target-yml",
    "game_root": null, "engine_root": null, "vcs": "git", "uproject": null,
    "parent_root": "…\\mwtp-s4-e2e\\parent",
    "partition_root": "…\\mwtp-s4-e2e\\shard",
    "roots": { "sdk": "…\\mwtp-s4-e2e\\sdk" }
  },
  "checks": [
    { "name": "parent_root", "ok": true, "detail": "…\\parent" },
    { "name": "partition_root", "ok": true, "detail": "…\\shard" },
    { "name": "root:sdk", "ok": true, "detail": "…\\sdk" }
  ],
  "probe_cache": "probed"
}
```

步骤 f 迁移后 target.yml（节选，v2 头注释 + 双块）:

```yaml
# Workspace target config (v2 — migrated from the v1 flat format by `mw partition set`).
active: partition
dual:
  game: ../gameproj
  engine: ../engine
  vcs: p4
  toolchain:
    build: build.bat {game} {engine}
    cook: cook.exe {game} -out={engine}
  ignore:
    deny_globs:
    - '**/Intermediate/**'
    - '**/DerivedDataCache/**'
  contract:
    forbidden_paths:
    - Content/Sealed
    conventions: '- never edit sealed content

      - keep public API stable

      '
    docs:
    - docs/README.md
partition:
  parent: '…\mwtp-s4-e2e\parent'
  partition: '…\mwtp-s4-e2e\ctrl-v1'
  vcs: git
```

（yaml round-trip 由 `yaml.safe_dump` 生成，注释不保留属预期——AC-022 断言的是内容级保留，.bak 保住原字节；本例 .bak 与预置 v1 文件 440/440 字节相等。）

## 5. 遗留/偏差清单

1. **AC-007 / D-005 修订（PM 已裁定）**: v2 标记（`PROFILE_MARK v2` + `[mw] mode:` 行）仅用于 partition 注入；dual/single 维持 `<!-- mw-profile: v1 -->` 标记与逐字节不变的渲染文本。理由：S0 golden 以 v1 标记录制，AC-016d（逐字节一致）优先级高于 D-005 字面的"dual 注入改为 v2 标记"。锁定测试: `dual injection keeps the v1 marker and no mode line (AC-016d zero change)`。
2. **撕裂校验的 v1 块解读（PM 已裁定）**: 任务文写"v1 标记视为 mode=dual"，但现行（golden 锁定）行为对 single+sections 工作区同样注入 v1 标记块——字面执行会把合法 single 任务全部误判撕裂。实现为：v1 块含 `Game root:` 行（仅 dual 注入产出）→ dual，否则 → single。锁定测试: `test_single_injected_v1_block_not_torn`。
3. **doctor E2E exit 1 的归因**: 裸临时控制根下 doctor 唯一 issue 是 `mw service not running`（另附 orphan-proxy/credentials 建议），target 段自身全绿。属冒烟环境预期，非 target 实现缺陷。
4. **提取方法偏差**: `[PARITY] target-config cases=39` 一行因 pytest capture 语义（`readouterr()` 消费先于 tee 回放）改为直接调用测试模块的 `_parity_marker()` 提取；其余 [VERIFY]/[BASELINE]/[PARITY] 行均来自真实测试运行输出。
5. **VC-019 无专用 [VERIFY] 行**: 本 key 的切换整体替换语义由 profile-injection describe 的 AC-019 用例名断言覆盖（输出中的 `VC-019` 行属 autopilot timeline key 编号碰撞）。
6. **dist bundle 双份**: `packages/multi-workers/dist/extensions/agent-team-loop.js`（mw 自带）与 `packages/coding-agent/dist/extensions/**`（install 对齐）均为 S3 T-09 重建产物，属清单内预期改动。
7. **design §9 VC-013 证据口径精化（PM 已裁定）**: 原文“`git diff --exit-code` 既有测试文件”字面过严；与 AC-013“既有用例零修改”的语义红线对齐后改为“既有夹具 001~014 零字节修改；既有测试文件仅允许纯新增 describe/case 与 runner 空值容差行；既有断言零修改”。质检 mwtp-verify-gate D 项审计按此口径执行通过。本补记于 2026-09-19 verify 阶段。
8. **VC-013 reviewer 签署原缺失（本补记闭环）**: 初版本文件未落 reviewer target-path diff 签署，质检 FAIL 项 2；现补 §6 签署节。
9. **E2E spawn/profile 缺口（已闭环 2026-09-19）**: 质检 FAIL 项 1：本文件 §4 仅 CLI 层 E2E；由 worker mwtp-e2e-spawn 补真实 spawn E2E：独立 launcher 进程拉起真实 pi worker（glm-5.3，22s，exit=0），cwd 证据文件 = 分片绝对路径，v2 profile 经 dist 产物 dispatchTask 真实注入，trace/output 写回控制根，另验 config-torn 负路径（任务 failed 含 config torn、无 spawn）。证据 evidence/e2e-spawn-2026-09-19.md（含 [VERIFY] VC-006+VC-007+§0-E2E 结论行）。

## 6. Reviewer 签署（VC-013 第四类证据，2026-09-19 补记）

- 评审人：独立质检 worker mwtp-verify-gate（模型 gpt-5.6-sol，与实现者无重叠）
- 审查范围与结论：
  - target 路径 diff：mw.py v1 `target set` 保留原 bootstrap 更新与直接写盘路径，show/clear v1 行为未见回归 → **通过**
  - fixture 001~014：零状态与内容差异 → **通过**
  - 既有测试删行 6 处：全部归类为 runner 空值容差（Py `game_root` or ""；TS `vcs` nullable、`gameRoot ?? ""`、nullable 调用类型处理、两处 `expectRoot` 非存在路径规范化），未发现削弱既有断言 → **通过**
  - P-002：新增源码 diff 无 `~/.pi/agent` 或凭据文件写入路径 → **通过**
- 签署形态：质检回读全文存 workers/mwtp-verify-gate/（worker.log/output.md），本节为其结论的结构化落盘。
