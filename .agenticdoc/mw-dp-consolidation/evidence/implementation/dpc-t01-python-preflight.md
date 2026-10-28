# T01 实施前静态核对：Python 生产调用/生成入口、缓存加载边界、现有 diff 与未覆盖迁移面

> 性质：只读静态核对（research）。未运行任何 CLI/产品测试/pytest/build/install/provider/决策探针，未起停服务或 monitor；未读活 `.mw/decide.json` / `.mw/decide-points.json` / gate / ledger / 签收 / 凭证 / 其他 key 运行材料；只写本文件（唯写面），未改任何源码/配置/生成物/旧证据。下文所有"会被拒绝/不会生效"均为代码路径推断，不是实测（见「残留与未验证」）。
>
> 复核基线：`H:\git\Multi-Workers` 工作树当前字节（含其它会话未提交改动，见 §E2）。
> 本文件 SHA256：`0FDAAB112AD9DD2FD0B5B497616E2F077016D705A186741EB57F567B087000EF`（23385B，初版；勘误后以本节外最终 read 回读为准）。

## 结论

1. **可以开始 M01 的源码实施，但不能在"当前活窗口"内完成切换。** 正常派发链是每次决策新起 Python 子进程（`python -X utf8 <mw.py> decide run --dp <id> --stdin --json`），Python 侧**无跨调用 registry 缓存**；而 TS 侧的 dp 枚举与 registry 是 build 时烘进 bundle、pi 启动时加载。两侧生效边界不同，切换必然出现一个"旧 bundle + 新 Python"的中间窗口。在该窗口里，仍编号的 PM/Worker 会用旧 id 调用，新 Python 会明确拒绝（`DecisionInputError` → exit 2），即**当前旧编号派发链无法合法工作**。这不是可以通过别名/旁路规避的问题，也无法在本卡内消除：消除它需要 (a) `mw build --install` 重装全局 bundle、(b) 重启所有在跑的 pi 窗口、(c) 重启 `mw decide monitor`；三者都超出本卡授权的写面/动作（禁 install/服务重启），**必须由 PM 另行安排切换窗口**。

2. **三条具体阻塞/前置（不在本卡授权内，不做）**：
   - B1 运行身份：全局安装 bundle `C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js` 与仓库 `packages/multi-workers/dist/extensions/agent-team-loop.js` 当前字节相同（SHA256 `D7EFE818…35DEFC`，1,471,556B），即"源码可改、活进程不改"。`shared/mw-runner.ts:55-58` 原文为 "The new bundle loads on the next pi start."。
   - B2 观察集合：`/api/dps` 由长驻 `decision_monitor.py` 从内存 `decision_points.DP_REGISTRY` 渲染（`decision_monitor.py:1849`），八名观察集合要生效必须重启 monitor；写面清单同一行写着"不顺带monitor重启"（`design-write-scope.md:27`）。
   - B3 活配置旧行：`.mw/decide-points.json` 的 per-dp 行按旧 id 键存（`decision_points.py:3188-3189` `_CONFIG_CACHE` 以 `(st_mtime_ns,st_size)` 为键；`3167-3169` `effective()` 按 `point.id` 取行）。改名后旧行成为孤儿行：显式 `enabled=false`/`mode` 覆盖**不会自动跟随**到新名字。dp25 现为 P2 默认开启（`decision_points.py:859-905`），若生产曾对旧 id 关闭过，切换后会被默认重新开启——属安全性实质变化，需 PM 以只读方式核对该文件键集合后再定切换顺序（本卡禁读该文件，故列为未验证）。

3. **回执链不阻塞。** `mw decide lifecycle --stdin` 只校验 `meta`/`stage`/`dp` 字段与 `decision_id` 必须以 `<dp>:` 为前缀（`decision_lifecycle.py:190`、`:697-700`；`mw.py:4360-4445`），**不查 DP_REGISTRY**。因此切换后，对切换前已发生的旧 id 决策回执仍然合法、可写；AC-002"新增有效业务裁决=0"讨论的是新请求，不是历史回执。

4. **一个必须先处理的顺序缺陷（AC-002 相关）：** 版本化入口把 replay 判据放在 registry 解析之前——`mw.py:1151-1167` 先查 `logical_id` 既有 start 行，命中即返回 `_decide_replayed_payload`（`mw.py:1083-1106`，`replayed: True`），**不校验 dp**；registry 解析在 `mw.py:1175-1182` 之后。而 design-write-scope 对 `mw.py` 的要求正是"CLI active-before-replay"（`design-write-scope.md:32`）。另 `mw.py:1295-1378` 的 legacy `questions` 路径根本不做 registry 解析（默认标签 `dp1`，注释见 `mw.py:1304-1307`），旧 label 可原样进入 `client.decide(dp=dp)`。这两条是"旧 id 可从运行入口到达"的真实静态缺口，需按 M01 改，不能靠删检查。

5. **四旧 case 的生成副作用会越界。** `scripts/build_decide_cases.py` 硬门只接受四个旧 case id（`:363`），默认输出目录就是 `decide_cases/`（`:72`、`:408`）；按现状重跑生成器会**覆盖四个已冻结的旧 case 文件**。实施时必须让生成器输出新八名 case 且不重写旧四份（卡明确"四旧 case"禁改），否则违反冻结面。

6. 其余需要改动的文件都在 `design-write-scope.md:15-56` 已列写面内（含 `decision_book.py`、`decision_context.py`、`decide_signoff.py`、`decision_signoff_result.py`、`decision_monitor.py`、`decide_book_template.json`、`worker-mode.ts`、`pm-orchestrator.ts`、`triage-client.ts`、`xkey-gate-guard.ts`），**未发现必须在清单外新增的源文件**；未列但相关的是 44 个 Python 测试文件与 `packages/coding-agent/test/suite/**`（回归面，不属迁移写面）。

## 证据

### E1 核对命令（PowerShell，cwd `H:/git/Multi-Workers`；全部只读）

| # | 命令（摘要） | rc |
|---|---|---|
| 1 | `rg -l 'RQ18\|RQ19\|RQ21\|RQ22' .agenticdoc/mw-dp-consolidation` | 0 |
| 2 | `git status --porcelain` | 0 |
| 3 | `rg -c 'dp(1\|2\|…\|25)-' packages/multi-workers packages/coding-agent/src --glob '*.py' --glob '*.ts' --glob '*.json' --glob '!test_*' --glob '!*.map'` | 0 |
| 4 | `rg -n 'EXPECTED_DP_COUNT\|DP_REGISTRY\|_REGISTRY_BY_ID' packages/multi-workers/decision_points.py` | 0 |
| 5 | `rg -n 'DecisionPoint\(' packages/multi-workers/decision_points.py` | 0（唯一工厂 `_point`，`decision_points.py:544-565`） |
| 6 | `rg -n 'DECIDE_REGISTRY\|ASK_DECISION_DP_IDS' packages/coding-agent/src/extensions/agent-team-loop` | 0 |
| 7 | `rg -n 'spawnSync\|--dp\|PYTHON_EXE\|findMwPy' packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts` | 0 |
| 8 | `Get-FileHash <file> -Algorithm SHA256` + `Length` + CRLF 探测（§E2） | 0 |
| 9 | `git diff --numstat -- <8 files>`（§E3） | 0 |
| 10 | `rg -n 'dp\d+-' <生产文件>`（§E5 行号锚点） | 0 |
| 11 | `Get-ChildItem packages/multi-workers -Filter conftest.py -Recurse`（空结果）；`rg pytest_plugins`（无命中）；`Get-Content packages/multi-workers/pytest.ini` | 0 / 1 / 0 |
| 12 | `Test-Path .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t01-python-preflight.md` → `False`（本文件此前不存在，无并发 writer） | 0 |

### E2 现有 dirty 基线（字节 / SHA256 / EOL），仅记录不修改

| exact path | bytes | SHA256 | EOL |
|---|---|---|---|
| `packages/multi-workers/decision_points.py` | 247920 | `A92BBDC2F12E6559C6E40BD571336655D190D84AA73268BBFF4EE0DC8BDF1243` | CRLF（5769 行；git 侧 `warning: CRLF will be replaced by LF`） |
| `packages/multi-workers/mw.py` | 569942 | `35FA4689101C69F6172C1565D99A834A25A3ADE5DD3E151C924A8410B9B48757` | CRLF（13043 行；同上 warning） |
| `packages/multi-workers/decide_registry.json` | 56194 | `0A5E16D64AB83B9F84A6A6776CEF55B16D87349010B24BB1B40DA4207D1283AE` | LF |
| `packages/multi-workers/decide_book_template.json` | 2367 | `755253B61429271B4EB1FC5CB22CC2FB4E77A7FCE07E7A67AA111DD896640DF2` | LF |
| `packages/multi-workers/scripts/gen_decide_registry_ts.py` | 11684 | `A0ED7A80EDF816C6FAFB4DAB6E3437690C4D45AED3A11809BF947F658317077D` | LF |
| `packages/multi-workers/decide_cases/dp1.json` | 1645 | `3131C02F4830B96994E3BEA94EFE1BE8511FD7936F8C983CF579596218A6C9FF` | LF（冻结） |
| `packages/multi-workers/decide_cases/dp2.json` | 2689 | `A03E1A29540BA9636A0A37BF478598BB530C357FC65D54B5EAAF6326E16342EA` | LF（冻结） |
| `packages/multi-workers/decide_cases/dp3.json` | 2320 | `82FF47E50AB5F24CFD84C793C07E2D15484EA89C24A90C8595306C468F407F2D` | LF（冻结） |
| `packages/multi-workers/decide_cases/dp25.json` | 2682 | `BDA25144A8C5CD73978603A3DC4C9B429D8D451485679D99EF46CFCC4C2CC7FD` | LF（冻结） |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts` | 30264 | `699719C2BF7E64CBB51866F8FDA39784C6D0EE9B09D7762C9C49E5FBB30127E4` | LF（生成物，25 个 dp 键） |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts` | 89846 | `3C1388F5CE8EE8D4336BE7207083F918C70C6E681C089D62522A36FC671F9F9E` | LF（2069 行） |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts` | 48631 | `70551A67C82BD463EE040267758D2D3A2D19AE3387D9329B9A6817581C651D58` | LF |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | 1471556 | `D7EFE8189D4D27BA9E019DBEB8ABE0A94ED3F240E12312711142D7A3A335DEFC` | LF（生成物） |
| `C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js`（全局安装，活进程加载面） | 1471556 | `D7EFE8189D4D27BA9E019DBEB8ABE0A94ED3F240E12312711142D7A3A335DEFC` | LF（= dist 字节） |

### E3 相关既有 diff（`git diff --numstat`，仅统计）

| exact path | + / − |
|---|---|
| `packages/multi-workers/decision_points.py` | +3312 / −313 |
| `packages/multi-workers/mw.py` | +2259 / −187 |
| `packages/multi-workers/decide_registry.json` | +1074 / −276 |
| `packages/multi-workers/decide_book_template.json` | +31 / −31 |
| `packages/multi-workers/scripts/gen_decide_registry_ts.py` | +179 / −18 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts` | +822 / −79 |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts` | +1280 / −99 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | +4659 / −2617 |

含义：这些文件已被前序工作改动（含其它会话/未提交），本卡实施者必须**在此基础上叠加**，不得整体格式化/覆盖；`decision_points.py`、`mw.py` 的 CRLF 与 git 的 LF 归一化警告需在提交前协调（不要用自动格式化改变整文件 EOL）。

### E4 当前运行入口与缓存加载边界（静态路径）

| 环节 | 真实入口/路径 | 加载边界 |
|---|---|---|
| 派发（PM→决策） | `pm/triage-client.ts:300-315` `runDecideMw`：`spawnSync(PYTHON_EXE, ["-X","utf8", mwPy, "decide","run","--project=…","--dp",dp,"--stdin","--json"])`，`timeout=20s, windowsHide` | **每决策一个新进程**；进程内 `_CONFIG_CACHE`（`decision_points.py:3188-3189`）不跨调用存活 |
| `mw.py` 解析 | `shared/mw-runner.ts:29-53` `findMwPy()`：`MW_PY` → `~/.pi/agent/extensions/.mw-py-path` → repo 相对 `../../../../../multi-workers/mw.py`；当前 sidecar 记录 `H:\git\Multi-Workers\packages\multi-workers\mw.py` | 改 Python 源码 → **下一次 spawn 生效**，无需重装 |
| 回执 | `pm/decision-tool.ts` 的 `decision_receipt` → `mw decide lifecycle --stdin`（`mw.py:4360-4445`） | 新进程；registry 无关（只校验 dp token + `<dp>:` 前缀） |
| 版本化 registry 解析 | `mw.py:1175-1182` `decision_points.get_decision_point(dp)`；未知 id → `DecisionInputError`（`decision_points.py:908-913`）→ exit 2，**在 record-start 之前**（注释 `mw.py:1171-1174`） | 拒绝机制现成，但位于 replay 判据之后（见结论 4） |
| 派发卡检查 | `mw dispatch check` → `autopilot/dispatch.py:263-320`：`_decision_registry_points()` → `decision_book.registry_points()`（`decision_book.py:214-217`）→ `decision_points.registry_snapshot()` | **读 Python 内存 registry**（非 JSON 文件），仍是新进程 |
| 签名/签收 | `decide_signoff.py:98` `SIGNOFF_DP_ID="dp25-signoff-conclusion"`；`decision_signoff_result.py:69` `DP_ID` 同值；`decide_signoff.py:411-416` `get_decision_point(SIGNOFF_DP_ID)` + `config.effective()` + "disabled" 拒绝 | 新进程；但**两份硬编码常量**不随 registry 改名，若只改 registry 则签收直接不可用 |
| 观察服务 | `decision_monitor.py:81` import registry；`:1849` `registry_snapshot()`；`:209-212` `_CASE_FILES` 四旧 id 固定表；`/api/dps` | **长驻进程，内存快照**；改名需重启 monitor |
| TS 工具面 | `pm/decision-tool.ts:132-158` `ASK_DECISION_DP_IDS`（25 个字面量）；`:1646-1649` `DP_ENUM_SCHEMA` 由它生成；`shared/decide-registry.generated.ts` 25 键；`pm/ui-bridge.ts:563`、`pm/decision-tool.ts:429/514` 以 `DECIDE_REGISTRY[dp]` 为材料合同 | **build 时烘进 bundle，pi 启动时加载**；源码改动不热更新 |
| 生成锁 | `scripts/gen_decide_registry_ts.py`（`--check` 漂移锁，`test_decide_registry_ts_lock.py`）；`mw decide dp export --write` → `decide_registry.json`（`mw.py:2867/2959+`）；`decision_points.registry_snapshot_text` 单一序列化 | 生成物需按序重生成，不能手改 |

### E5 旧 id 引用盘点（生产面，`rg -c` 匹配数；分类见 E6）

| exact path | 匹配数 | 关键行锚点 |
|---|---|---|
| `packages/multi-workers/decision_points.py` | 74 | `EXPECTED_DP_COUNT = 25`（`:191`）；`DP_REGISTRY` 25 条（`:574-889`）；`_validate_registry` 计数硬门（`:901-905`） |
| `packages/coding-agent/.../pm/decision-tool.ts` | 37 | `ASK_DECISION_DP_IDS`（`:132-158`）；`ASK_DECISION_PM_ONLY_DP_IDS`（`:214`）；material 集合（`:157/174/222`） |
| `packages/multi-workers/mw.py` | 29 | `import decision_points`（`:49`）；`_decide_run_versioned`（`:1108`）；registry 解析（`:1175-1182`）；`_dp_export`（`:2959+`） |
| `packages/multi-workers/decide_registry.json` | 26 | 25 points + 头部（生成物） |
| `.../shared/decide-registry.generated.ts` | 25 | 25 个 registry 键（生成物） |
| `packages/multi-workers/scripts/build_decide_cases.py` | 16 | 四 case 硬门（`:363`）；输出目录（`:72`） |
| `.../worker/worker-mode.ts` | 9 | `DP3_ID="dp3-worker-clarify"`（`:5007`）；marker 前缀（`:4927/5013`） |
| `.../pm/triage-client.ts` | 7 | `DP1_ID="dp1-dispatch-type"`（`:77`）；无障碍字段行（`:429`） |
| `packages/multi-workers/decision_book.py` | 6 | `BOOK_DP_SLOTS`（`:112-117`，含已退役 dp4/dp7 行） |
| `packages/multi-workers/decide_book_template.json` | 6 | `dp3-worker-clarify`（`:3-8`）、`dp6-qg-verdict`（`:31-36`） |
| `packages/multi-workers/decide_signoff.py` | 4 | `SIGNOFF_DP_ID`（`:98`）；`:309/350/411` |
| `packages/multi-workers/decision_monitor.py` | 4 | `_CASE_FILES`（`:209-212`） |
| `.../pm/pm-orchestrator.ts` | 3 | `DP2_CHECKPOINT_ID`（`:1947`）；marker/header（`:1960/1965`） |
| `packages/multi-workers/decision_signoff_result.py` | 2 | `DP_ID`（`:69`）；decision_id 前缀校验（`:412`） |
| `packages/multi-workers/decision_context.py` | 1 | `producers: ("dp4-failure-handling","dp6-qg-verdict","dp7-gate-failure")`（`:110`） |
| `packages/multi-workers/autopilot/dispatch.py` | 1 | 卡示例注释（`:218`） |
| `packages/multi-workers/decide_cases/{dp1,dp2,dp3,dp25}.json` | 各 3 | `dp`/`book.decision_point`/`state.decision_point`（冻结） |
| `packages/multi-workers/test_*.py` | **44 个文件**引用旧 id（`test_decision_points.py` 122 处、`test_decision_dashboard_contracts.py` 55、`test_decision_history.py` 47…） | 回归面 |

### E6 分类（active / history / security / regression）

- **active（运行注册与真实调用）**：`decision_points.py`（注册+计数硬门）、`decide_registry.json`、`decide-registry.generated.ts`、`decision-tool.ts`（工具枚举与材料合同）、`triage-client.ts:77`、`worker-mode.ts:5007`、`pm-orchestrator.ts:1947`、`decide_signoff.py:98/411`、`decision_signoff_result.py:69/412`、`decision_book.py:112-117`、`decide_book_template.json`、`decision_monitor.py:209-212`、`decision_context.py:110`、`mw.py` 解析/导出/replay。
- **history（只读/历史解释）**：`decide_cases/*.json` 四旧 case（卡明令冻结，用途=readonly regression）、`xkey-gate-guard.ts:303/377` 注释、`dispatch.py:218` 注释、`decision_book.py` 中 dp4/dp7 行（职责已退出）。
- **security（安全相关，非菜单）**：`decide_signoff.py` 的 `SIGNOFF_DP_ID` + "disabled" 拒绝、`decision_signoff_result.py:412` 的 `decision_id` 前缀绑定、`decision_lifecycle` 的 token 校验——改名时必须同步，否则签收要么整体不可用（只改 registry）要么历史签收过滤失效（只改常量不留旧行解释）。
- **regression（测试）**：`packages/multi-workers/test_*.py` 44 个文件 + `packages/coding-agent/test/suite/**`（vitest）。

### E7 生成副作用路径（谁写、写哪里）

| 生成物 | 写入方 | 证据 |
|---|---|---|
| `packages/multi-workers/decide_registry.json` | `mw decide dp export --write`（`_dp_export_doc/_dp_export`） | `mw.py:2867/2907/2948/2959+`；序列化 `decision_points.registry_snapshot_text:1094-1103` |
| `packages/coding-agent/.../shared/decide-registry.generated.ts` | `python scripts/gen_decide_registry_ts.py`（`--check` 漂移锁） | 脚本头 `:2-16`；锁测试 `test_decide_registry_ts_lock.py` |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` | `mw build`（esbuild + jiti self-check） | `mw.py:9971` `_BUNDLE_REL`、`_BUILD_NODE_SCRIPT` |
| `~/.pi/agent/extensions/agent-team-loop.js` + `.mw-py-path` | `mw build --install` | `mw.py:10178-10193`；`mw-runner.ts:55-58` |
| 项目 `.pi/extensions/agent-team-loop.js` | `mw init/setup`，**仅当无全局副本** | `mw.py:10378-10392` |
| `packages/multi-workers/decide_cases/*.json` | `python scripts/build_decide_cases.py`（读 `decide_registry.json`，默认目录 `decide_cases/`） | `build_decide_cases.py:72/74/408`；四 id 硬门 `:363` |
| `packages/coding-agent/dist/extensions/agent-team-loop/**` | coding-agent 自身 build（本卡未核脚本名） | `git status` 显示 40+ 个 dist 镜像已改 |

### E8 pytest 插件 / conftest 隔离风险

- `packages/multi-workers` 下**没有 `conftest.py`**，仓库内也无 `pytest_plugins`（`rg pytest_plugins` 无命中，`Get-ChildItem -Filter conftest.py -Recurse` 空）。
- `packages/multi-workers/pytest.ini` 只设 `addopts = -m "not e2e_real and not e2e_l2"` 与两个 marker，无 `testpaths`/`norecursedirs`；测试是包根平铺的 `test_*.py`。
- 因此风险不在插件自动加载，而在：(a) 迁移测试若按 `-k` 局部跑仍需从包根启动（否则 `import mw`/`import decision_points` 失败）；(b) 现有测试大量直接 `import mw`/`decision_points` 并可能触碰仓库级 `.agenticdoc/_autopilot/*.jsonl`（`git status` 显示这些文件已被别的会话改动），隔离用 `tmp_path`/fixture 的覆盖情况本卡未逐文件核（未验证）。
- 本卡按禁止项**未运行 pytest**，以上只是采集面结论，不是隔离性实测。

## 残留与未验证

1. **未实测**：全部结论为静态代码路径推断。未运行 `mw decide run/lifecycle/dp export/check`、未跑 pytest/vitest、未 build/install、未启停服务（含 monitor）、未调 provider。
2. **未读**：活 `.mw/decide.json`、`.mw/decide-points.json`（故 B3 的实际键集合与 `enabled` 取值为未知）、任何 gate/ledger/签收/凭证/其它 key 运行材料；未读 `decision.py`、`decision_wire.py`、`decision_history.py`、`decision_playground.py`、`decision_dashboard.*`、`pm/ui-bridge.ts` 正文，也未读 44 个测试文件正文（只做 `rg -c` 计数）。本报告**不宣称全仓审计**。
3. **运行身份未核**：仓库 `dist` 与全局安装 bundle 字节相同，但"当前正在运行的 pi/monitor 进程加载的到底是哪一份、是否已热更"未核（需读活 `serve.meta`/进程信息，属禁止面）→ 切换窗口的必要性由此为推断，不是实测。
4. **B3 的影响程度未知**：旧 id 行被孤儿化后，dp25→dp-sign-key 是否从"显式 disabled"变回"默认开启"，取决于生产配置内容；这属于安全性实质变化，需 PM 以只读方式核对后再定切换顺序（本卡不读、不改）。
5. **AC-002 的 replay 语义待设计确认**：现状 `mw.py:1151-1167` 对已存在 `logical_id` 返回 `replayed:True` 而非拒绝，且不查 registry。若 AC-002"已有 logical_id replay 提交需明确 retired 拒绝"按字面执行，需要 `mw.py` 的 active-before-replay 改造（已列写面）并处理"并发 duplicate 也不能误判为 retired 拒绝"，属实现期设计问题，本报告只标出缺口位置。
6. **legacy `questions` 路径**：`mw.py:1295-1378` 明确不做 registry 解析（默认 label `dp1`）。它对 AC-003"旧编号活跃调用=0"的影响（是否算旧 id 可提交面）未决，需在 M01 内分类为 human-only/legacy 只读而非活动入口；本卡不判定。
7. **四旧 case 冻结与八名菜单的边界**：`build_decide_cases.py:363` 只认四旧 id，`decision_monitor.py:209-212` 固定表也只认四旧 id；八名观察 case 需要新生成路径 + 新表项，同时不能重写旧四文件。具体文件命名/菜单注册方式属实现选择，未定。
8. **未验证的运行时面**：`.mw/decide-points.json` cache key 为 `(st_mtime_ns,st_size)`（同秒重写可观测），但"切换期间新旧进程各读一次配置"的一致性未实测；`mw serve` 是否缓存 registry 未核（`cmd_serve` 段未见 `decision_points` 引用）。
9. 本文件为唯一写面，已用 `worker_file` 写入并 `read` 回读确认落盘；未建第二报告、未写任何活对象、未改任何源码。

## 上下文来源

- 任务卡：`.agenticdoc/mw-dp-consolidation/tasks/T01-python-preflight.md`（读到实际 EOF，含状态/写面/AC-VC 摘录）；派发卡：`.agenticdoc/mw-dp-consolidation/workers/dpc-t01-python-preflight/task.md`（读到实际 EOF）。
- 目标/锁定/设计：`.agenticdoc/goal.md`、`.agenticdoc/mw-dp-consolidation/spec.md:6/22/26-33/43-51/61-63/79-87`（八名映射与"名称≠实现"表述）、`.agenticdoc/mw-dp-consolidation/design.md:22/49-52/198-215`、`.agenticdoc/mw-dp-consolidation/design-write-scope.md:11-56/121-141`。
- 复用历史研究（不重新设计、不回填为本次源码审计）：`evidence/research/design-protocol-full-read-20261026.md`（decision_points 5769 行全文、decision_backends 1123、decision-tool.ts 2072 全文；mw.py 仅 870-1290）、`design-conductor-full-read-20261026.md`、`design-observation-server-20261026.md`（monitor/playground 全文、case 装载逻辑、`_CONFIG_CACHE` 位置）、`design-cli-reachability-20261026.md`（mw.py 全文至 EOF、CLI 入口表）。
- 本次静态核对直接源：`packages/multi-workers/decision_points.py`（1-240 / 520-640 / 856-905 / 1039-1106，`_decide_for` 与字段表未逐行读）、`packages/multi-workers/mw.py`（1080-1210 / 1295-1435 / 4360-4520 / 9955-10035 / 10378-10392）、`packages/coding-agent/src/extensions/agent-team-loop/pm/{triage-client.ts,decision-tool.ts}`（定向段）、`shared/{mw-runner.ts,decide-registry.generated.ts}`、`packages/multi-workers/autopilot/dispatch.py:255-325`、`decision_book.py:214-226`、`decide_signoff.py:98/309/411-424`、`decision_signoff_result.py:69/412`、`decision_monitor.py:81/207-212/1849`、`decision_context.py:110`、`decide_book_template.json`、`decide_cases/*.json`（仅 dp1 正文，其余仅键/大小）、`scripts/{gen_decide_registry_ts.py,build_decide_cases.py}`、`pytest.ini`。
- 未使用任何活配置、活账本、凭证或其它 key 的运行材料作为依据。
