# verify-run-delta-2026-09-23 — mw-rag-window-parity T-5 增量独立验证

> 结论：**PASS（T-4 的三项遗留闭合；R-6 作为遗留实测确认）**。T-4 之后 PM 直执的 T-3B（doctor RAG 行门控）/T-3C（trim parity + `--project` spawn 钉住）经独立复核：零回归全绿，四条反例 A/B/C/D 全部变红（其中反例 B 在 T-4 全绿，现由新增 VC-308b 打红），R-6 实测证实 padding 的 `path_roots_file` 下 TS≠Python 且差异仅来自该键。反例改动全部 sha256 复原，除本报告外零写入，未 commit。

- key: `mw-rag-window-parity` / task `T-5-VERIFY-DELTA`
- 验证者: 独立 coding worker（第三方视角）
- 基准 commit: `0c7754086`（工作区含多会话未提交改动）
- 唯一写入: 本报告（`.agenticdoc/mw-rag-window-parity/evidence/verify-run-delta-2026-09-23.md`）

## §0 复现命令表（全部在仓根或指定目录执行）

| # | 命令 | 目的 | 结果 |
|---|---|---|---|
| 1 | `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-config.test.ts … test/suite/rag-research-doc.test.ts`（任务书 14 文件原序） | RAG 全系列零回归 | **14 files / 127 passed**，`EXIT=0` |
| 2 | `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-output.test.ts` | 扩展套件零回归 | **2 files / 178 passed**，`EXIT=0` |
| 3 | `cd packages/multi-workers && python -m pytest -q` | Python 零回归 | **839 passed, 9 deselected**，`EXIT=0` |
| 4 | 仓根 `npm run check` | biome+pinned-deps+ts-imports+shrinkwrap+install-lock+tsgo+browser-smoke | **`EXIT=0`**（biome：`Checked 1082 files … No fixes applied.`） |
| 5 | `git diff --stat -- packages/multi-workers/test/fixtures packages/multi-workers/test_autopilot_l0.py` | fixture/golden 零 diff | **空** |
| 6 | `sha256(packages/multi-workers/test/fixtures/rag-block.golden.md)` | golden 字节锚点 | `00f85e646e30d577f434c6e1967a704c65966163a01d1bf4de9630c9717d4035`（= spec 锁定 `00f85e64…4035`） |
| 7 | §2 反例命令（逐条单测） | A/B/C/D 打红 | 全红（§2） |
| 8 | `python %TEMP%/mw-rwp-t5/{mkfixture,r6_py}.py` + `node node_modules/tsx/dist/cli.mjs %TEMP%/mw-rwp-t5/r6_ts.mts` | R-6 最小实验 | padding 下 TS≠PY（§3） |

`[VERIFY]` 原文（步骤 1 同一次运行）：
```
[VERIFY] VC-305b: dir="skills/x" cli_entry="cli.py" ts==py=true prefix=a7ac2452cbb3
[VERIFY] VC-305b: url="http://127.0.0.1:19999/" token_env="RAG_TOKEN" ts==py=true prefix=b30415c5058c
[VERIFY] VC-305b: blank_dir_ts_kind=invalid-shape blank_dir_py_error=true
[VERIFY] VC-308b: argv0=["rag","list","--project=C:\\Users\\WENBOZ~1\\AppData\\Local\\Temp\\mw-rag-spawn-LzkGlD"] argv1_code=1 ok0=true ok1=false
[VERIFY] VC-309b: empty_py_row=false empty_ts_row=false configured_py_row=true configured_ts_row=true
```

> 实验脚本与 fixture 全部写在 `%TEMP%`（仓外）；仓内除本报告零写入（`git status --porcelain` 与实验前逐行相同），未 commit。

## §1 零回归

| 套件 | 结果（原始） | 与 T-4 对比 |
|---|---|---|
| rag 系列 14 文件 | `Test Files 14 passed (14)` / `Tests 127 passed (127)` | T-4 只跑了 7 个（55+16）；本次按 T-5 任务书扩到 14 文件全绿 |
| `agent-team-loop*.test.ts` 2 文件 | `2 passed (2)` / `178 passed (178)` | 与 T-4 完全一致（T-3B/T-3C 未新增该套件用例） |
| Python `pytest -q` | `839 passed, 9 deselected in 83.37s` | 与 T-4 完全一致 |
| `npm run check` | `EXIT=0`；biome `Checked 1082 files … No fixes applied.` | 与 T-4 一致 |
| fixture + `test_autopilot_l0.py` | `git diff --stat` 输出**空** | 一致 |
| golden `rag-block.golden.md` | `00f85e64…4035` | 一致（spec 锁定值） |

本次新增/受改动文件的基线 sha256（实验前＝复原后）：
- `rag/config.ts` `4e6185fea53a7186724c3a275a0de578b29203d981e0618e0835af903177bad9`
- `rag/tools.ts` `ab031102cb60e0a5f61ccf138b324a25780deb602df6043b2b71463fec2e79a0`
- `shared/mw-runner.ts` `f061957cf6d9af648edf1e42ac7ad040cb95fb7521c08a4355c904b02936c6a0`
- `pm/ui-bridge.ts` `147d6e9cb2b22acc0bdc22a6640491671e3b008c559260cb30ec7c642384c4ca`
- `test/suite/rag-window.test.ts` `845b8943f9659bfaa9ee026e8e8e18217fbdbe97294a9f2c157f1bc840d31535`
- `test/suite/rag-trim-parity.test.ts` `5164061dfda751aaafbe50e634b88e383ddc2a2ceca60ddca49902630c4a4d6f`
- `mw.py` `e38668c5…6b72`、`mw_common.py` `f2a5369e…d4ab`（全程未动）

注：`rag/config.ts` 基线 sha 与 T-4 报告的 `7d24c051…` 不同——正是 T-3C 新增 `optionalTrimmedString` + 四处使用造成的 delta；`rag-window.test.ts` 由 T-4 的 `4fba6673…` 变为 `845b8943…`——新增 VC-308b。零回归在上述新基线上通过。

## §2 反例

统一流程：`python %TEMP%/mw-rwp-t5/exp.py {save|patch|restore} <file> <spec.json>`；备份在 `%TEMP%/mw-rwp-t5/backup/`（仓外）。

| 反例 | 改了什么（文件 / 原→新 / sha 前→后） | 看到什么红（原始） | 还原 + sha256 自检 |
|---|---|---|---|
| **A** trim 必要 | `rag/config.ts` 四处 `optionalTrimmedString(` → `optionalString(`（`mcp.url` / `mcp.token_env` / `skill.dir` / `skill.cli_entry`）；`4e6185fe…` → `ae4d7b69…` | `rag-trim-parity.test.ts`：**2 failed / 2 passed**。红：`skill.dir` 得到 `'  skills/x  '`≠`'skills/x'`；`mcp.url` 得到 `'  http://127.0.0.1:19999/  '`≠trim | restore ✓ `4e6185fe…177bad9` = 基线 |
| **B** `--project` 拼接 | `shared/mw-runner.ts` `[mwPy, sub, ...args, \`--project=${projectDir}\`]` → `[mwPy, sub, ...args, "--project=."]`；`f061957c…` → `b9e36e9e…` | `rag-window.test.ts -t VC-308b`：**1 failed / 16 skipped**。实得 `['rag','list','--project=.']`≠`['rag','list','--project=<controlRoot>']`（T-4 此反例**全绿**，现已补钉） | restore ✓ `f061957c…36c6a0` = 基线 |
| **C** doctor 门控 | `pm/ui-bridge.ts:1568` `if (shouldShowRagDoctorRow(report.rag))` → `if (report.rag)`；`147d6e9c…` → `27dd86bb…` | `rag-window.test.ts -t VC-310`：**1 failed / 2 passed / 14 skipped**。红：`a project without RAG config shows no row`，文本里出现了 `rag: not enabled (skill unknown)` | restore ✓ `147d6e9c…384c4ca` = 基线 |
| **D** fingerprint 真的被比 | `rag/config.ts` payload 键 `path_roots_file: entry.pathRootsFile,` → `path_roots_files: entry.pathRootsFile,`；`4e6185fe…` → `f2f12dc3…` | `rag-parity.test.ts`：**4 failed / 5 passed**。红：`VC-027`（`fingerprintMatch=false`、golden 字节不匹配）、`VC-305`（TS `e29c6591…` ≠ Python `5e9bfc00…`） | restore ✓ `4e6185fe…177bad9` = 基线 |

结论：**四条反例全部变红**，无一条是装饰断言。B 的闭合直接回应 T-4 发现 1（`--project` 拼接此前无真 spawn 钉住）；A/C/D 与 T-4 结论一致。四者复原后逐文件 sha256 均等于 §1 基线；`mw.py`/`mw_common.py` 前后一致。

## §3 R-6 实测

自建 fixture（`%TEMP%/mw-rwp-t5/fixture-pad`）：`.mw/rag-roots.json` **真实存在**（内容 `{"roots":["a"]}`）；`.mw/rag-servers.yml` 为 `servers: {S: {transport: mcp, mcp.url: http://127.0.0.1:19999/, path_roots_file: " .mw/rag-roots.json "}}`（首尾各一空格）；`.agenticdoc/target.yml` `rag.enabled: [S]`。两侧均以 `MW_RAG_SERVERS_FILE=<缺席文件>`/`MW_RAG_SERVERS_HOME=<root>` 隔离机器层。

| 侧 | `pathRootsFile` / `path_roots_file` | `pathRootsDigest` / `path_roots_digest` | fingerprint |
|---|---|---|---|
| TS | `" .mw/rag-roots.json "`（**未 trim**） | `null` | `d5b017c6068506ac4f212a266809a53e89e7be2415188b5439e95b81f028535f` |
| Python | `".mw/rag-roots.json"`（已 strip） | `None` | `9ed001e4c3a523c2bcfc108153693039cfeedb28a1e0a3f73f6282abf9bb4545` |

**两侧 fingerprint 不相等**（`d5b017c6…` ≠ `9ed001e4…`）。两侧 digest 均为空：Python `_rag_path_roots_digest(project_root, <未 strip 串>)`（`mw_common.py:636`）与 TS `pathRootsDigest(controlRoot, entry.pathRootsFile)` 都拿未 trim 串拼路径，`" .mw/… "` 解析不到真实文件 → 双双 `null`（即 padding 下 roots 内容**根本没进指纹**）。

**最小实验证明差异仅来自该键**：把 TS 解析结果的就地副本 `pathRootsFile` 手动 trim 后重算 `ragFingerprint`，得 `9ed001e4c3a523c2bcfc108153693039cfeedb28a1e0a3f73f6282abf9bb4545`，**与 Python 逐字节相等**。即：除 `path_roots_file` 一个键外，两侧 payload 完全相同。

无 padding 对照（同 fixture，`path_roots_file: ".mw/rag-roots.json"`）：两侧 `path_roots_file` 同为 `".mw/rag-roots.json"`、digest 同为 `1fa82c8ce70caf4ec64431dc8ac01abce327f1eb7bce02f4edf949a363dc4acd`、fingerprint 同为 `a3e2ee05e22031694d217ea2e11c629c8281ae29cfc5e775725c334d856405b3`。

→ R-6 成立：T-3C **未**修 `path_roots_file`（有意为之，已在 `rag-trim-parity.test.ts` 头部注释声明）。影响：YAML 用引号包了首尾空白的 `path_roots_file` 时，PM（Python）与 worker（TS）的 `config tear (rag)` 判定会分裂，且 roots 内容摘要双侧都为 null（内容变更不会触发 tear）。修复需两侧统一：要么不 strip 字段、要么 digest 也用 strip 后的串（后者会改变既有 fingerprint 语义，需另行评估）。

## §4 逐 VC 表（仅本次 delta 涉及）

| VC | 断言 | 发射位置 file:line | 实测行原文（截断） | 强度 |
|---|---|---|---|---|
| VC-305b | 四字段 `mcp.url/token_env`、`skill.dir/cli_entry` 按 Python `.strip()` 语义；fingerprint 逐字相等；空白值双侧拒绝 | `test/suite/rag-trim-parity.test.ts:145`、`:160`、`:178`；实现 `rag/config.ts:181`（用于 `:263/:267/:277/:278`） | `dir="skills/x" cli_entry="cli.py" ts==py=true prefix=a7ac2452cbb3` / `url="http://127.0.0.1:19999/" token_env="RAG_TOKEN" ts==py=true prefix=b30415c5058c` / `blank_dir_ts_kind=invalid-shape blank_dir_py_error=true` | 强（反例 A → 2 例红） |
| VC-308b | 真 spawn：argv 为 `["rag", <sub>, ...args, "--project=<controlRoot>"]` 且 exit 1 保留 | `test/suite/rag-window.test.ts:440`；实现 `shared/mw-runner.ts:450-453` | `argv0=["rag","list","--project=C:\\Users\\WENBOZ~1\\AppData\\Local\\Temp\\mw-rag-spawn-LzkGlD"] argv1_code=1 ok0=true ok1=false` | 强（反例 B 变红；T-4 缺口闭合） |
| VC-309b | 无 RAG 配置项目两侧都不打 `rag:` 行（门控镜像 `mw.py:523` `exists or enabled`） | `test/suite/rag-window.test.ts:366`；实现 `pm/ui-bridge.ts:1484` | `empty_py_row=false empty_ts_row=false configured_py_row=true configured_ts_row=true` | 强（谓词 + 真实 `mw.py doctor` 文本双侧）；仅测谓词本身，不经 `formatDoctorReport` |
| VC-310 | 无 `rag` 不出现行且不抛；有 `rag` 恰好一行；无配置门控与 Python 同 | `test/suite/rag-window.test.ts:378/:390/:403`；实现 `pm/ui-bridge.ts:1568`+`:1484` | `no_rag_row=true lines=4` / `gate_absent=false gate_inert=false gate_exists=true gate_enabled=true rows=0` / `rag_rows=1 line="rag: not enabled (skill unknown)"` | 强（反例 C、D 分别打红不同断言） |
| VC-301 | `skill.dir` 缺省 → `null` 且解析成功 | `test/suite/rag-window.test.ts:86`；实现 `rag/config.ts:277` | `dir=null parse=ok` | 强（T-4 反例已证；本次复跑绿） |
| VC-302 | `dir: null` → `null` | `test/suite/rag-window.test.ts:94`；实现 `rag/config.ts:277` | `dir=null parse=ok` | 强（同上） |
| VC-303 | `dir: ""` → `invalid-shape` 且指 `skill.dir` | `test/suite/rag-window.test.ts:109`；实现 `rag/config.ts:164-169` | `dir="" kind=invalid-shape mentions_skill_dir=true` | 强（反例 A 下仍绿，说明与 trim 行为边界分开） |

## §5 未覆盖与限制

- **真实 RAG 服务联调**：probe 仍只用不可达端口 `127.0.0.1:19999`；未对接真实 RAG 服务，未验真实 `list_sources`/能力校正。T-3C 的 trim parity 也不涉及真实服务（只比配置层）。
- **pi TUI 手工操作**：未在 tmux/真 TUI 里敲 `/mw rag <sub>`、`/mw doctor`；只验证了纯函数与接线（`pm/ui-bridge.ts:1568`、`:2034` 分支）。窄通知通道下的换行/宽度表现（`RAG_FULL_OUTPUT_HINT` 单行）**未审**。
- **`/mw rag init` 的写盘副作用**：至今未在窗口里人工跑过（init 会写 `.mw/rag-servers.yml` 等）；本次只验证 argv 转发与 exit code，不验证 init 落盘结果。
- **R-6 未修**（有意）：padding 的 `path_roots_file` 下 TS≠Python，且两侧 digest 皆为 `null`（§3）；需要另开 key 定方向（两侧不 strip，或 digest 也用 strip 后的串）。
- **多服务器 probe 排序 / `required_missing>0`** 本次未重跑（不在 T-5 delta；T-4 的 E-4 已实测逐字相等）。
- **VC-309b 不经 `formatDoctorReport`**：它只测 `shouldShowRagDoctorRow` 谓词；但行渲染由 VC-310 钉住，两者互补（T-4 已记）。
- **Windows 基线**：未重跑 `packages/agent`；Python 只跑了 `packages/multi-workers`（已知 89 条环境失败与本次无关）。
- 本报告为仓内唯一写入；所有反例改动已 sha256 复原（§2），未 commit。
