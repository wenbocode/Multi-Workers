# QG Review — mw-vision-role（独立审查）

- reviewer: `mvr-t16-quality-gate-review`（独立 QG 审查方，非实现方） · date: 2026-09-26
- 代码版本: HEAD `c3edc20fe`；工作区 **dirty**（多 key 未提交并发：本 key + `mw-autopilot-slot-capacity` + `mw-autopilot-readcap`）。
- 审查方式: 只读 + 独立重跑 + 一次性临时变异（含还原 sha256 复核）。**未修改任何 `packages/**` 源码/测试，未改证据文档，未 `git add`/commit。**
- 工具面实际: 本会话 bash = PowerShell 5.1 host（POSIX 命令经 `D:\Program Files\Git\bin\bash.exe`）；报告与临时脚本用 here-string + `cat >` 落盘（UTF-8 无 BOM、LF）。

## 0. 结论速览

- **QG verdict: PASS-WITH-NITS**。18 条活跃 AC 全部有可复现证据；两侧镜像逐元素相等；门禁顺序、fail-open、改动面、非空洞性均通过；**0 blocker**。
- `[VERIFY] VC-QG: acs_total=18 acs_pass=18 invariant_violations=0 blockers=0`
- 全部 NIT 为证据/文档口径与测试强度问题，不影响任何 AC 的行为判定（详见 §6.3）。

---

## 1. AC/VC 覆盖矩阵（自算）

**自算方法**（脚本 `%TEMP%/qgvision/matrix.py`，从三份文档各自独立抽取后比对）：
- `spec.md` §3 表 → AC 集合（19）
- `design.md` §7 → VC 定义（19），§8 → AC↔VC 映射（19 行）
- `evidence-requirement.md` → 19 个 `## AC-xxx` 小节内的 VC 引用

自算输出：

```
spec ACs: 19  ['AC-001' ... 'AC-019']
spec OBSOLETE: ['AC-018']
active ACs: 18
design VC defined: 19  ['VC-001' ... 'VC-019']
design §8 rows: 19
spec ACs missing from §8: []
§8 ACs not in spec: []
ereq AC sections: 19 ; ereq missing AC: []
VC-018 in design §7: True | AC-018 obsolete: ['AC-018']
AC-018 counted as active: False
```

结论：三份文档 **1:1:1 对齐**；`AC-018` 在 spec 表内明确 `[OBSOLETE @ 2026-09-26]`、design `ac_count: 19（AC-018 已 OBSOLETE → 有效 18）`、VC-018 为 `n/a obsolete=true`，**未计入 19 条判定**。活跃 AC = 18。

（唯一映射差异：`evidence-requirement.md` 的 AC-009 小节里引用了 `readcap VC-007/008`，那是 **另一个 key 的同号 VC**（readcap 套件的编号），不是本 key 的 VC-007/008。见 N-4。）

### 逐 AC 判定（证据 = 我本次重跑观察到的原始行，非 PM 转述）

| AC | VC | 我观察到的证据（重跑） | 判定 |
|----|----|------------------------|------|
| AC-001 | VC-001 | `[VERIFY] VC-001: vision=timi/deepseek-v4-flash-vision-exp rc=0` | PASS |
| AC-002 | VC-002 | `[VERIFY] VC-002: rc=nonzero roles=5` + argparse stderr `(choose from main, coding, review, research, vision)` | PASS |
| AC-003 | VC-003 | `[VERIFY] VC-003: source=config:vision task_override=task`（测试经真实 `launcher._read_task_md_fields` + `resolve_dispatch_model`） | PASS |
| AC-004 | VC-004 | `[VERIFY] VC-004: role_for_vision=vision mirror_ok=true` + 我的逐元素镜像脚本 18/18 PASS | PASS |
| AC-005 | VC-005 | `[VERIFY] VC-005: allowlist_vision=read,write,edit,bash,find,grep,ls parity=true` + 我的逐 key 工具集比对 | PASS |
| AC-006 | VC-006 | `[VERIFY] VC-006: refused=true queue_delta=0 dir_exists=false`（断言含 `images`/`mw model set vision`/`images: no`） | PASS |
| AC-007 | VC-007 | `[VERIFY] VC-007: queue_delta=1 images_line=yes order_ok=true`（精确行匹配 + 严格 `type<phase<images<model`） | PASS |
| AC-008 | VC-008 | `[VERIFY] VC-008: failopen_ok=true queue_delta=1` + `VC-008: unknown_branches=10`（10 条 unknown 分支全部断言）+ 我的反例 F | PASS |
| AC-009 | VC-009 | `[VERIFY] VC-009: zero_byte=true frozen_copy=true` + `VC-009-order: ... order_ok=true`；我另跑 TS 精确串 `"type: coding\n"` = true | PASS |
| AC-010 | VC-010 | `[VERIFY] VC-010: doctor_rc=0 states=suggestion,ok,skip`；真实仓库 `mw doctor --json` rc=0、`healthy=true`、`images=no` suggestion 列表 = `[]` | PASS |
| AC-011 | VC-011 | `[VERIFY] VC-011: image_cap_line=true exit=1 control_ok=true` + **我独立重跑真进程 L2**（源 builtin `-ne`）：`[IMAGE-CAP] model=deepseek-v4.1-flash ... declared=images:yes`、rc=1、output.md 落盘 | PASS |
| AC-012 | VC-012 | 我重跑：`npx tsgo --noEmit` rc=0 零输出；`npx biome check --error-on-warnings .`（全仓、无 `--write`）rc=0；`check:pinned-deps`/`check:ts-imports`/`check:shrinkwrap`/`check:install-lock:coding-agent`/`check:browser-smoke` 均 rc=0；Python 203 passed/2 failed（E-04/E-06 基线）；TS 210 passed/0 failed | PASS（带 N-1 口径） |
| AC-013 | VC-013 | `[VERIFY] VC-013: no_rc=1 yml_unchanged=true force_rc=0`（含 unknown skip 支、`--force` 仅 vision 支） | PASS |
| AC-014 | VC-014 | `[VERIFY] VC-014: surfaces=4 token_set_ok=true`；我另核对 4 处源文本（见 §2.4） | PASS |
| AC-015 | VC-015 | `[VERIFY] VC-015: show_images=yes/no/unknown rc=0`；我真实跑 `mw model show` → 5 行角色均带 `images=`；TS 渲染单测含 `images=` | PASS |
| AC-016 | VC-016 | `[VERIFY] VC-016: auto_route=true type_unchanged=true explicit_model_untouched=true` + 我的反例 A | PASS |
| AC-017 | VC-017 | `[VERIFY] VC-017: types=vision,review type_unchanged=true effective_vision=2 auto_route_fired=1`（修正后口径，语义未改） | PASS |
| AC-018 | VC-018 | OBSOLETE，`n/a obsolete=true` | N/A |
| AC-019 | VC-019 | `[VERIFY] VC-019: conductor_dispatchable=true unknown_type_refused=true` + 我的镜像脚本 `conductor_dispatchable[vision]=true` | PASS |

`acs_total=18`，`acs_pass=18`，`invariant_violations=0`。

---

## 2. 不变量核验（逐元素 / 顺序 / fail-open / 改动面）

### 2.1 两侧镜像逐元素相等（脚本 `%TEMP%/qgvision/mirror.mjs`，非人眼）

脚本直接 import TS 模块（`dispatch-models.ts` / `worker-mode.ts`，node 24 strip-types）拿真实导出，并用子进程 `python -c` import `mw_common` / `autopilot.dispatch` 拿真实 Python 表，然后逐项 JSON 比对：

```
py roles: ["main","coding","review","research","vision"]
ts dispatchable: ["coding","review","research","rag-research","vision"]
registry keys py: roadmap-writer,phase-writer,verifier,reviewer,repair,rag-research,vision

PASS TASK_TYPE_TO_ROLE == DISPATCH_ROLE_BY_TYPE
PASS map key order
PASS roleForTaskType(vision) ; PASS roleForTaskType(unknown)
PASS DISPATCH_ROLES == /mw model set usage roles
PASS tools[roadmap-writer] ; PASS tools[phase-writer] ; PASS tools[verifier]
PASS tools[reviewer] ; PASS tools[repair] ; PASS tools[rag-research] ; PASS tools[vision]
PASS DISPATCHABLE_TYPES subset of registered TS types
PASS vision allowlist literal
PASS conductor_dispatchable[vision] ; PASS conductor_dispatchable[rag-research]
PASS MODEL_PREFIX_TO_PI_PROVIDER == PREFIX_TO_PROVIDER_ID
MIRROR_RESULT: pass=17 fail=1
```

那 1 条 `FAIL` 是**我脚本自身的比较写错**（把 `PROVIDER_ID_TO_PREFIX` 与 `PREFIX_TO_PROVIDER_ID` 当成同一张表比），不是产品缺陷。更正后的独立复核：

```
PROVIDER_ID_TO_PREFIX inverse-of-prefix-map: true
{"timi":"timi","anthropic":"claude","openai-codex":"codex","deepseek":"deepseek","zai-coding-cn":"zai"}
```

即真实结论 **18/18 通过**：

- `TASK_TYPE_TO_ROLE`（Python，10 键）↔ `DISPATCH_ROLE_BY_TYPE`（TS，10 键）：**键序与取值逐元素相等**，`vision -> vision`。
- `DISPATCH_ROLES`（Python，5 角色，`vision` 末尾）↔ `/mw model set` USAGE 角色串（TS）：集合/顺序相等。
- `REGISTRY` 工具集（Python，7 键）↔ `toolsForType()`（TS）：**7/7 同序逐元素相等**；`vision` = `["read","write","edit","bash","find","grep","ls"]`（TS 侧另有内部 `fallback` 桶，Python 无，属既有设计差异，parity 测试已按此冻结）。
- provider 前缀映射两侧互逆一致。

### 2.2 门禁顺序：auto-route → capability gate → 任何磁盘写入

`pm/ui-bridge.ts` 的 `planDispatchFrontmatter`（`:1031`）是**纯函数**：只 `readRoleModel`（读）、`detectImageNeed`（`existsSync`）、`modelImageCapability` / `validateModelValue`（内存 registry）。调用点：

- `dispatch_worker` tool：`planDispatchFrontmatter` 于 `:1325`，`fs.mkdirSync(taskDir)` 于 `:1341`，`dispatchTask`（写 `_workers.parallel`）于 `:1345`。
- `/worker` 命令：plan 于 `:1723`，`fs.mkdirSync` 于 `:1737`，`dispatchTask` 于 `:1741`。

拒绝分支在 plan 内 `return {ok:false}`，两者都在 **任何 mkdir/write 之前**返回。实测断言（VC-006）：`refused=true queue_delta=0 dir_exists=false`，`expect(dirExists).toBe(false)` + `expect(fx.rows()).toBe(before)`。

auto-route 只改 `model:`：`headLines` 仅由 `input.taskType`/`phase`/`images` 构成（`:1069-1072`），路由分支 `routeLines = [...headLines, 'model: ...', 'model-reason: ...']`（`:1127`），`type:` 字节不变。实测：反例 C2 输出 `type: review\nphase: 1\nimages: yes\nmodel: ...`（`type:` 未动）；VC-017 断言 `type_unchanged=true`。

### 2.3 fail-open 契约（自己读代码 + 自己跑）

`shared/dispatch-models.ts::modelImageCapability`（`:225`）按 `validateModelValue` 同款早退顺序，9 条不可判定分支全部返回 `"unknown"`：空值 / `registry===undefined` / `cli!=="pi"` / 无 model id / `codex_cli|claude_cli` 前缀 / 未知前缀 / 无 provider / provider 在 registry 无条目 / `registry.find` miss；整体再包 `try/catch -> "unknown"`。门禁只在 `capability === "no"` 时拒绝（`:1107-1110`）。

Python 侧 `mw_common._probe_model_rows`（`:1425`）在 `which` miss / `OSError` / `TimeoutExpired` / rc≠0 / 解析 0 命中时返回 `None` → `model_capabilities` 归入 `"unknown"`，`mw.py model set` 只有硬 `"no"` 才拒绝（`:3182-3193`）。

实测：`[VERIFY] VC-008: unknown_branches=10`（10 条分支逐条 `expect(...).toBe("unknown")`）；我的反例 F（`images: yes` + `codex_cli/gpt-5` → `ok:true`）。

### 2.4 改动面 / 核心零改动

- `src/core/**` / `src/cli/**` 内 **无任何 vision 特性标记**（`modelImageCapability`/`detectImageNeed`/`IMAGE-CAP`/`model_capabilities`/`DISPATCH_ROLES`/`dispatch-models` grep = 0）。
- 工作区内**唯一** `src/core` 改动是 `packages/coding-agent/src/core/tools/bash.ts`（+38 行 bash 心跳，代码自述 `T-04`），属**其他 key**（worker 看门狗），非本 key。
- 本 key 特性代码全部落在 `packages/coding-agent/src/extensions/agent-team-loop/**` + `packages/multi-workers/**`。
- `.mw/dispatch.yml` 未变（本仓库实际内容仍只有 `main/coding/review/research` 四键，无 `vision`）；无 `providers.json` / auth / `settings.json` / `models.generated.ts` / `.mw/window-model` 的 tracked 改动（`git status` 对这些路径为空）。
- `settings.json` 的 `defaultModel` 优先级未动：`applyMainModelConfig` 的 `hasCliModelFlag() || settingsDefaultModel()` 早退在 diff 中**零改动**（`dispatch-models.ts` 的 diff 只新增能力函数与两个表条目）。
- 本 key 的四处 PM 文本面实测：`dispatch_worker` 的 `type` 描述 token 集 == `DISPATCHABLE_TYPES ∪ {"codex"}`（L0 真集合相等断言）；`/worker` USAGE 含 `--type ...|vision`；`/mw model set` USAGE 角色 == `DISPATCH_ROLES`；`PARALLEL_PROTOCOL` 第 6 条含 `type: vision` 与"引用图片"。

**方法学限制**：工作区把 3 个 key 的未提交改动混在一起，`git diff` 无法单独切出本 key 的 diff。上述结论用「特性标记 grep + 逐文件 diff 语义归类」得出，不是靠 `git blame`。

---

## 3. 对抗式反例与结果（我自行设计，脚本 `%TEMP%/qgvision/adv.mjs`，直接调 `planDispatchFrontmatter` + 真实 registry 形状）

| # | 边界输入（规则文档未写） | 期望（按 AC 意图） | 实测 | 判定 |
|---|--------------------------|--------------------|------|------|
| A | `images: yes` + 显式 `model:` 指向**能**看图模型（+必需 `model_reason`） | 通过，不得误拒；显式模型保留、不 auto-route | `ok=true`，head = `type: review / phase: 1 / images: yes / model: timi/deepseek-v4-flash-vision-exp / model-reason: pixel diff`，echo 无 auto-route | PASS |
| B | 显式 `images: no` + 描述引用**存在** `.png` + 角色默认纯文本 + `vision` 已配且能看图 | 显式声明优先（D-013），**不**写 `images: yes`、**不**改道 | `ok=true`，head = `.../images: no`，无 `model:` 行、无 auto-route | PASS |
| C1 | `images: "YES"`（大小写变体）+ 无图片引用 | 行为可解释 | `ok=true`，无 `images:` 行（未知值按"未声明"处理，fail-open） | PASS（N-2） |
| C2 | `images: "YES"` + 描述引用存在 `.png` | 行为可解释 | 落回 auto-detect → `images: yes` + auto-route（与"未声明"同路径） | PASS（N-2） |
| C3 | `images: "maybe"` + 存在 `.png` | 行为可解释 | 同 C2（未知值被忽略，走 auto-detect） | PASS（N-2） |
| D | `type: vision` 但描述无任何图片引用、无 `images:` 头 | 不误伤、零副作用 | `ok=true`，head == `type: vision\nphase: 1\n`（无 `images:` 行） | PASS |
| E | `images: yes` + 显式能看图模型 + `vision` 角色**未配置** | 通过（显式模型已满足能力） | `ok=true` | PASS |
| F | `images: yes` + 显式 `codex_cli/` 前缀 | fail-open 不阻塞（AC-008 同契约） | `ok=true` | PASS |
| G | `images: yes` + 纯文本角色 + `vision` 未配 | AC-006 拒绝且消息含三个修复 token | `ok=false`，消息含 `images` / `mw model set vision` / `images: no` | PASS |
| H | `detectImageNeed`：大写扩展名 / glob / URL | 大写命中；glob、URL 跳过 | `SHOTS/LOGIN.PNG`→true；`*.png`→false；`https://x/login.png`→false | PASS |

```
ADVERSARIAL_RESULT: fails=0
```

补充：`/worker --images maybe` 在命令解析层即拒绝（`--images must be 'yes' or 'no'`）并零副作用（既有用例 + 我复核源码 `ui-bridge.ts:1668-1674`）；`dispatch_worker` 的 `images` 参数是 `Type.Union([Literal("yes"), Literal("no")])`，非法值在 schema 层被拒。因此 N-2 的静默回落只在"绕过 typed 参数直接调纯函数"时可达。

---

## 4. PM 证据抽检（重跑命令 + 原始输出）

### 4.1 `npx tsgo --noEmit`（仓库根）

```
(empty - no diagnostics)
TSGO_RC=0
```

### 4.2 `python mw.py model show --project H:/git/Multi-Workers`

```
config: H:\git\Multi-Workers\.mw\dispatch.yml
window model: timi/deepseek-v4-flash-vision-exp
main: timi/deepseek-v4.1-flash images=no
coding: timi/deepseek-v4.1-flash images=no
review: timi/glm-5.3 images=no
research: timi/deepseek-v4.1-flash images=no
vision: (unset) -> timi/deepseek-v4-flash-vision-exp [window] images=yes
RC=0
```

5 条角色行均带 `images=`（AC-015）。`vision images=yes` 是因为用户把 `.mw/window-model` 改成了视觉模型（已知旁注），与 E-10 当时的 `images=no` 差异可解释。

### 4.3 `python mw.py doctor --project H:/git/Multi-Workers --json`

```
dispatch= {"exists": true, "models": {"coding":"timi/deepseek-v4.1-flash","main":"...","research":"...","review":"timi/glm-5.3"},
           "window_model":"timi/deepseek-v4-flash-vision-exp",
           "images": {"coding":"no","main":"no","research":"no","review":"no"}}
healthy= True
issues= []
suggestions= ["extension bundle older than source - run '/mw build' or 'mw.py build --install'",
              "routes without credentials (env of the mw process): claude ...; claude-cli ...; deepseek ..."]
bundle= {"available": true, "global_bundle_mtime": "2026-09-26T15:15:39", "source_newest_mtime": "2026-09-26T18:05:30", "stale": true}
img_suggestions= []
RC=0
```

复核 E-10/E-11/T-15：`dispatch.images` 全角色齐全；`healthy=true`；`images=no` suggestion 列表 = `[]`（T-15 收窄生效，文本角色不再告警）；退出码 0。与 PM 记录一致。

### 4.4 Python 触达面（8 文件，`-q -s`）

```
2 failed, 203 passed in 17.89s
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound - As...
FAILED test_autopilot_readcap_injection.py::test_existing_regression_files_untouched
```

本 key 的 `[VERIFY]` 行逐条在原始 stdout：`VC-001/002/003/005/009/009-order/010/013/014/015/019`。两红逐条归因（我核对了测试源码）：

- `test_baseline_left_end_bound`：冻结副本 sha ≠ `HEAD:` blob（E-04，环境/历史遗留，与 `images:` 无关）。
- `test_existing_regression_files_untouched`：断言 `test_autopilot_config.py`（**其他 key** 未提交）与 `test_autopilot_dispatch.py`（**本 key T-03 授权重冻**）与 `HEAD:` 逐字节相等。它在第 1 个名字即失败；属"未提交工作区"现象，提交后自动消失。**但它确实含有本 key 授权改动的成分**，见 N-1。

### 4.5 TypeScript 触达面（5 文件）

```
Test Files  5 passed (5)
     Tests  210 passed (210)
```

本 key 的 `[VERIFY]` 行：`VC-004/006/007/008(failopen+unknown_branches=10)/011/016/017`。（PM 记录为 201 passed/4 文件；我多纳入 T-04 的 `agent-team-loop-vision-capability.test.ts`（+9）→ 210 passed，无红。）

### 4.6 静态检查

```
npx biome check --error-on-warnings packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test
  -> Checked 317 files. No fixes applied.  BIOME_RC=0
npx biome check --error-on-warnings .        # 全仓、无 --write
  -> Checked 1104 files. No fixes applied.  BIOME_FULL_RC=0
npm run check:pinned-deps / check:ts-imports / check:shrinkwrap / check:install-lock:coding-agent / check:browser-smoke
  -> 全部 RC=0（shrinkwrap/install-lock 均 "up to date"）
```

### 4.7 真进程 L2-1（AC-011，源 builtin `-ne`，我独立重跑）

```
[worker] start task=l2t type=coding phases=-
[IMAGE-CAP] model=deepseek-v4.1-flash provider=timi task=l2t declared=images:yes
rc=1
--- trace.log ---
[ERROR] ... [IMAGE-CAP] model=deepseek-v4.1-flash provider=timi task=l2t declared=images:yes
--- output.md ---
## Exit Reason
[IMAGE-CAP] model=deepseek-v4.1-flash provider=timi task=l2t declared=images:yes
```

注意：直接 `pi-test.sh -ne` 调用下 **不产生 `worker.log` 文件**（该文件由 mw launcher 派发时捕获 stdout 创建）；机读行走 stdout + trace.log。生产（launcher）路径下 stdout → `worker.log`，AC-011 字面成立。见 N-3。

### 4.8 已知遗留复核（B2 部署陈旧）

```
<agent 目录>/extensions/agent-team-loop.js  (mtime 2026-09-26 15:15, 925286 B)  IMAGE-CAP count = 0
packages/multi-workers/dist/extensions/agent-team-loop.js (同 mtime/size)       IMAGE-CAP count = 0
```

与 `mw doctor` 的 `bundle.stale=true` 一致。属**部署陈旧**（未 `mw build`/`/mw restart`），非本 key 代码缺陷，不计入 blocker（按 T-16 卡明确要求）。

---

## 5. 测试非空洞性判断

**我自己的独立变异对照（唯一一处临时变异，已还原）**：删除 `shared/dispatch-models.ts` 第 68 行 `\tvision: "vision",`，跑 `agent-team-loop.test.ts -t 'VC-004'`：

```
BEFORE ab325e3099267dcbaeea4d49f8141844ce2c8b80f14f274b935b17ebbdfa85f6
MUTATED cad8c33375ea8ecd88dc045ed51a1da8b46e49748bac78e921b9d2387283fffc
VITEST_RC=1
AFTER ab325e3099267dcbaeea4d49f8141844ce2c8b80f14f274b935b17ebbdfa85f6
FAIL  ... > VC-004: vision maps to its own role on the TS half and mirrors the Python table
AssertionError: expected [ 'coding', 'phase-writer', …(7) ] to deeply equal [ 'coding', 'phase-writer', …(8) ]
Tests  1 failed | 8 passed | 168 skipped (177)
```

即 VC-004 是**真断言红**，且还原后 sha256 与改前**逐字节一致**。仓库工作区无残留（`git status` 复查无新增改动）。

**对 T-14 §7 四条对照的原始失败输出核查**（看断言行，不看自述）：

- VC-006：`AssertionError: expected 'Dispatched worker ... ' to contain 'images'` —— 真断言红。
- VC-008：`expected 'Task declares images ... ' to contain 'Dispatched worker'` —— 真断言红（unknown 被误当 no 时确实拒绝）。
- VC-009：`AssertionError: ("...type: verifier\nphase: EXECUTE\n... - images: \n model: ...")` —— 差分里明确出现多出的 `images: ` 行，真断言红。
- VC-011：`expected "Mock" to be called with arguments: [ 1 ] / Number of calls: 0` —— `process.exit(1)` 未被调用，真断言红。

**空洞用例扫描**：

- 5 个本 key TS 测试文件内 `it.skip` / `xit` / `describe.skip` / `it.todo` / `.only(` = **0**（唯一 grep 命中是注释里的 "exit("）。
- `expect.soft` 仅出现在 VC-007 用例（5 处），soft 断言失败同样使用例变红，不构成假绿。
- 非恒真检查：
  - VC-005 的 parity 测试从 `worker-mode.ts` **动态解析** TS 表（`_parse_ts_allowlists`），不是复制常量；同时 `test_autopilot_l0.py` 用 Python REGISTRY 与解析出的 TS 表做逐 key 同序相等断言。
  - VC-014 的工具描述 token 集是与 `DISPATCHABLE_TYPES ∪ {codex}` 的**集合相等**断言，不是子串。
  - VC-003 走真实 `launcher._read_task_md_fields` + `resolve_dispatch_model`，不是手传桩。
  - VC-009 的"冻结副本"是 `_pre_images_module()`（预存 pre-images 模块，无 git-HEAD 回退），并断言该冻结模块签名里**没有** `images` 参数 → 对照 `live == frozen` 非恒真。
  - VC-019 驱动真实 `dispatch.dispatch(task_type="vision")` 并检查 `_workers.parallel` 行，未知类型反向对照同用例。
- 全部 `[VERIFY]` 行都在**断言之后**才 print，断言红则行不出现（我重跑时逐行核对过）。

---

## 6. 结论

### 6.1 QG verdict: **PASS-WITH-NITS**

18 条活跃 AC 全部 PASS（AC-018 为 OBSOLETE，未计入）；核心不变量（两侧镜像逐元素、门禁顺序、auto-route 只换 model、fail-open、核心零改动）全部成立；无 blocker；非空洞性经我独立变异 + 四条对照原始失败输出核实。NIT 均为证据/文档口径与测试强度问题，不改变任何 AC 的行为判定。

### 6.2 BLOCKER 列表

**无。** T-14 记录的两个 BLOCKER 均已闭环：

- B1（`tsgo` 4×TS2741）：T-17 修 `description?` 可选，我重跑 `rc=0` 零输出 → closed。
- B2（陈旧 bundle）：按卡定位为**部署遗留**（`bundle.stale=true`），非代码缺陷 → 不计 blocker，登记于 §6.4。

### 6.3 NITS / 建议（不阻塞）

- **N-1（AC-012 口径）**：AC-012 字面要求"`npm run check` 全绿"，但 `npm run check` 第一步是 `biome check --write .` —— 在本三 key 并发脏工作区里跑会**自动改写他人文件**，故未按字面执行；我改为逐条跑其只读组件（全仓 biome `--error-on-warnings`、tsgo、pinned-deps、ts-imports、shrinkwrap、install-lock、browser-smoke）全绿，并提供 `biome --write` 的替代证据。另：Python 触达面 2 红中的 `test_existing_regression_files_untouched`，其失败对象之一（`test_autopilot_dispatch.py`）正是本 key T-03 的授权重冻；虽然提交后即消失，但它说明 AC-012 的"全绿"在本 key 未提交状态下严格不成立。建议：把 `npm run check` 的写模式拆出只读门禁，或在 readcap 的"与 HEAD 逐字节相等"断言里显式排除被授权重冻的文件。
- **N-2（非法 `images` 值静默回落）**：`planDispatchFrontmatter` 对非 `"yes"/"no"` 的 `images` 值（大小写变体、`maybe` 等）不报错，静默按"未声明"走 auto-detect。用户可达路径（tool schema / `--images`）都已显式拒绝，纯函数层不可达；建议在纯函数入口对非法值 fail-loud（或注释写明"未知值 == 未声明"的契约）。
- **N-3（AC-011 的 `worker.log` 字面）**：源 builtin 直接调用不落 `worker.log`（只落 stdout/trace.log/output.md）；`worker.log` 由 mw launcher 捕获 stdout 时创建。生产路径满足字面，但复现配方应写明"需经 launcher 或看 stdout/trace.log"。
- **N-4（跨 key VC 编号）**：`evidence-requirement.md` 的 AC-009 小节引用 `readcap VC-007/008`，与 readcap 套件同号 VC 混淆。属文档歧义，非覆盖缺口。
- **N-5（AC-015 doctor 行）**：真实仓库 `vision` 未配置，`mw doctor` 的 `dispatch.models` 不含 `vision`，因此派发行没有 `vision` 行（"角色未配置 → skip"语义）。字面"每个角色行均含 `images=`"对**已显示**的行成立；若 PM 希望未配角色也显示行，需另开需求。
- **N-6（测试强度）**：VC-014 的 `/worker` USAGE 与 `PARALLEL_PROTOCOL` 断言是子串（`"vision"` / `"type: vision"`），弱于 AC 的完整 token 集要求；VC-009 缺一条 TS 精确串 `"type: coding\n"` 断言（我已独立验证该值正确）。
- **N-7（evidence-requirement 测试入口过期）**：其"测试入口"段只列 2 个 TS 文件，漏了实际承载 VC-006/007/016/017 的 `vision-gate` / `vision-autoroute` 与 T-04 的 `vision-capability` 文件。

### 6.4 未验证项与原因

- `npm run check` 字面命令（写模式 biome）——**未跑**，原因见 N-1（会改写其他 key 在飞文件）。
- 真实 PM 窗口的 TS doctor 渲染（`ui-bridge.ts` 的 `images=` 行）——**未在活窗口验证**：运行中的窗口仍加载陈旧 bundle（B2），本 key 的 TS 渲染只有单测覆盖。属已登记遗留，需用户决定 `/mw build` + `/mw restart`。
- T-14 §6 的真实视觉 round-trip（L2-2：读 PNG 返回 `red square`）——**未由我重跑**（会消耗真实 provider token）；我引用 PM 记录，不独立复现。
- 真实仓库对**已配置** `vision` 角色的 doctor suggestion（`images=no`）——**未跑**：本仓库 `vision` 未配置，跑它需要写 `.mw/dispatch.yml`（会污染用户配置）；三态行为由 VC-010 单测覆盖，真实探针的 yes/no 由 `mw model show` 只读路径覆盖。

---

[VERIFY] VC-QG: acs_total=18 acs_pass=18 invariant_violations=0 blockers=0
