# RQ-5：跨 key 只读守卫「key 身份判据」真实性核查（A5/A6/A7/A9/A11）

- key: `mw-guard-form-hardening`｜phase: SPEC｜type: research（**只读**，未改任何源码/测试）
- 核查对象：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:247` `foreignLiveClaimRefusal()`
- 复核方式：用 `node --experimental-strip-types` 直接 import **生产源码**（`IndexStore` / `claimState` / `foreignLiveClaimRefusal` / `resolveOwnerKeyWithSync` / `readIndexMdActive` / `dispatchDocGaps`）跑真实语料 + 读码。未运行 vitest / `npm run check` / `npm run build` / `mw build`。

## 0. 语料锚点（必读：本文件在核查期间被别人改写）

`.agenticdoc/_index.parallel` 锚点：
- sha256 `4719DD10611E5E5ACE53BF8415FEDFF5A32E53F34738B11D950CDB06042F5956`
- mtime `2026-10-11T15:23:47.0034351Z`｜rows=52

核查期间观察到 **3 个不同快照**（多窗口并发写同一文件）：
1. `t≈15:18Z`：52 行，**全部 `idle`**（`activeEntry()===undefined`），最后一行 `mw-guard-form-hardening`；
2. `t=15:19:27Z`（mtime）：追加 `mw-console-title-clobber | active | SPEC | WENBOZHOU-PC4:1768`；
3. `t=15:23:47Z`（上面的锚点）：`mw-console-title-clobber` 已 `DONE` 且 claim 清空，`activeEntry()===undefined` 再次成立。

⇒ **任何行级数值都必须对本哈希重新锚定**（AC-011 口径）。下文所有结论均已在此快照上复跑，凡依赖快照的行内数值都注明「锚点快照」。

---

## 1. 逐条裁定表

| 议题 | 结论 | 证据（文件:行号 + 输出摘要） | 危害面 | 建议 |
|---|---|---|---|---|
| **A5** `_`/`.` 前缀无条件豁免 | **成立**（豁免行为已复现；活 `_`-key 的触发路径已定位，未实际制造） | `pm/ui-bridge.ts:250` 在 `:251` 的 `findByKey` **之前**无条件 `return null`。函数级复现（只读）：`foreignLiveClaimRefusal(store,"_tmp") → null`（对照：同一 store 上 `xkey-repair-mechanism`(claim `WENBOZHOU-PC4:18200`, live) `→ REFUSE`）。锚点快照 `exempt_prefix_keys=[]`（0 个 `_`/`.` 前缀行，故当前**未**被触发）。触发路径：`ui-bridge.ts:850-871` `/pm-key new <key>` **无 key 形态校验**直接 `takeOverKey`；`.agents/skills/agentic-task/scripts/update_index.py:361-405` `claim` 亦无形态校验且置 `status=active`。 | 任何窗口 `claim` 一个 `_`/`.` 前缀 key（如 `_tmp`、`_incidents`、`.mw`）后，**其他所有窗口的守卫对该 key 恒放行**：`dispatch_worker{key:"_tmp"}` 会在 `.agenticdoc/_tmp/workers/<task>/` 建目录 + 写 task.md + 写队列行（`:1676` 的守卫是唯一闸口，但它返回 null）。若 key 名撞上框架保留名（`_workers.parallel` / `_index.parallel` / `_scratch` / `_autopilot` …）则等于把「框架文件同级路径」当 key 命名空间用，零告警。 | 见 §2 豁免清单 |
| **A6** key 大小写（Windows） | **成立**（读码 + 函数级复现；锚点快照无实际重名，0 例） | `shared/index-store.ts:164-166` `findByKey` = `readAll().find(e => e.key === key)`（**精确字符串**，无 casefold）；`claim()` 的 `rows.findIndex((e) => e.key === key)` `:101`、`upsert()` `:73` 同样精确。复现（只读）：`foreignLiveClaimRefusal(store,"MW-GUARD-FORM-HARDENING") → null`（`row=null`），而精确大小写 `mw-guard-form-hardening`（claim `WENBOZHOU-PC4:117296`，pid ALIVE）`→ REFUSE`。Windows 大小写不敏感由 `fs.existsSync('.agenticdoc/MW-CONSOLE-TITLE-CLOBBER')===true` 与 `.agenticdoc/Mw-CoNsOlE-tItLe-ClObBeR===true` 直接证实。锚点快照 `case_only_dup_groups=[]`、`exact_dups=[]`。 | ② 判定面：他人 live 持有 `mw-key` 时，本窗口用 `key:"MW-KEY"` ⇒ `findByKey` 落空 ⇒ 守卫放行；而 Windows 上 `.agenticdoc/MW-KEY/workers/` 就是 `.agenticdoc/mw-key/workers/` ⇒ **跨 key 写进他人的物理命名空间**。② 写入面更糟：`claim("MW-KEY")` 因 `:101` 精确匹配失败而**追加第二行**（`_index.parallel` 出现仅大小写不同的重复 key，两条 claim 指向同一目录），此后 `findByKey`/`activeEntry` 各自取不同行。 | 守卫入口与 `claim/upsert` 统一按 Windows 语义做大小写归一（`key.toLowerCase()` 比较 + 保留首写大小写用于显示），并在 `claim` 时对「仅大小写不同的已有行」判定为冲突而非新建 |
| **A7** `_index.md active:` 回退绕过守卫 | **成立**（**当前语料即满足前置条件**，已函数级复现） | `pm/ui-bridge.ts:77` `const active = indexStore.activeEntry();` → `:78-81` 只对 `activeEntry()` 做 held-live 降级 → `:82` `const owner = active?.key ?? readIndexMdActive(agenticDocRoot) ?? SCRATCH_WORKERS_KEY;`（**回退结果不经任何 claim 检查**）。`shared/index-store.ts:218-228` `readIndexMdActive` 只读 `_index.md` 的 `active:` 行，不读 claim。`ui-bridge.ts:1676` 工具侧守卫**仅当显式传 `key` 时调用**（`:1677`），隐式分支无守卫。锚点快照实测：`activeEntry()===undefined`（`active_rows=[]`）且 `indexMdActive=xkey-repair-mechanism`，其行 claim `WENBOZHOU-PC4:18200`（pid ALIVE）⇒ `claimState(...)==="held-live"`。桩替 `activeEntry:()=>undefined` 调真实 `resolveOwnerKeyWithSync` → 返回 `xkey-repair-mechanism`；对该 key 守卫文本为 `REFUSE [cross-key-read-only]`，但 `dispatchDocGaps(root, owner, "DONE")===[]`（该 key 有 spec/design/研究笔记，DONE 全链齐备）。 | 无 watch key、未显式传 `key` 的**新窗口**调用 `dispatch_worker` 时，ownerKey 落到他人 live key：docs 门禁放行 ⇒ 在 `.agenticdoc/xkey-repair-mechanism/workers/`（他人的 key）建目录 + 写 task.md + 写 `_workers.parallel` 行。守卫在同一窗口的 `/worker` 路径上会拦住（`:2188` 无条件调用），**只有工具面隐式分支漏**。 | ① `:82` 的回退结果也过 `claimState`（held-live ⇒ 降级 `_scratch` + 告警）；② 或在 `dispatch_worker` 隐式分支同样调用守卫（去掉 `:1676` 的 `if` 条件），失败即拒 |
| **A9** 缺 `run.json` ⇒ 证据新鲜度轴关闭 | **成立（fail-open 轴），但只在交付判定面成立；「跨 key 守卫层」不成立** | `shared/deliverable-evidence.ts:155` `const startedAt = readRunState(taskDir)?.started_at;` → `:168` `if (Number.isFinite(startedAtMs) && stat.mtimeMs < startedAtMs) continue;` —— 无 `run.json`（或 `started_at` 不可解析）⇒ `startedAtMs=NaN` ⇒ **反伪造比较整体跳过**，运行前就存在的 `evidence/*.md` 被当作有效交付证据（`:208-211` 命中 channel=output）。消费端：`worker/worker-mode.ts:1904-1907`（writeless 角色的 done/NC 判定）。doctor 侧同类「按 `run.json` 存在与否开关」的轴：`packages/multi-workers/mw_common.py:2468-2485`（注释「Present only when T-20's run.json exists」）+ 问题文本 `:3306-3311`。**面板不使用 `run.json`**：`autopilot/monitor.ts` 中 `run.json` 出现次数 = 0；`mw_common.py:3057-3075` 的「三轴」是 `_blocked_on_human`（pending gate / 非终态行 / conductor tick），三轴均不读 evidence 或 `run.json`。 | 一个 shell-capable 的 writeless（`research`）worker 只要在运行中删除/损坏自己的 `run.json`，就能让 finish 阶段的「陈旧证据」判定失效：回复里引用**运行前已存在**的 `evidence/research/old.md` 即被判 `delivered`（exit 0 / done，无 `no-product` 告警）；doctor 的 `run-ledger-conflict` 轴同时静默。跨 key 只读守卫**不读** evidence/`run.json`，故 A9 不构成守卫绕过。 | 新鲜度轴改为 fail-closed：`run.json` 缺失/不可解析时，`evidence/*.md` 引用**不计入**交付证据（或降级为 NC + 审计行）；至少在 trace.log 留一条 `[RUN] freshness axis off (no run.json)` 审计 |
| **A11**（本 RQ 重述版）同一 key 在 `_index.parallel` 与 `_index.md`（或阶段不同） | **不成立**（无跨源合并；语义已定死）｜**QG-B 原版 A11（roadmap 跨 stage 重复 key）**：**成立（读码）** | 重述版：`index-store.ts:164-166` `findByKey` **只读 `_index.parallel`**，取**首个**精确匹配行；`index-store.ts:218-228` `readIndexMdActive` **只读 `_index.md`**，完全不返回 claim。两源从不合并 ⇒ 同一 key 两处各一行时，**claim 判定 100% 取 `_index.parallel` 那一行**；`_index.md` 只在 `:82` 作为 owner 指针兜底（无 claim 语义）。锚点快照 `exact_dups=[]`、`case_only_dup_groups=[]`；`empty_claim_rows` 9 个（如 `mw-timi-gpt6-astra-rename`），即「`_index.parallel` 行为空 claim + `_index.md` 指向它」时守卫必放行。同文件内重复行时：`findByKey` 取首个、`claim()/upsert()` **只改首个**（`:73`/`:101`）、`activeEntry()` 取 `updated` 最新（`:175-188`）⇒ 守卫可能读到旧行的 stale claim（当前 0 例）。原版 A11：`autopilot/roadmap.py:477-483` `stage_of_key` = `setdefault`（**首次声明胜出**）；`autopilot/conductor.py:2562-2567` 用它对 gate 的 stage 做终态抑制；`roadmap.py:383-388` `validate_roadmap` **会**报跨 stage 重复 key，但 `mw_common.py:3422-3426` 的 doctor 文案自证「validate_roadmap ran but the conductor does not enforce it yet」⇒ 无效 roadmap 仍被 conductor 消费。 | 重述版：无独立危害（真值源单一且确定）；唯一残留是「同文件重复行」下 guard 行与 `activeEntry` 行不同步（当前 0 例，且只可能由大小写变体或手改引入）。原版 A11：活跃 stage 上的 pending gate 被静默（丢提醒，非漏放写）。 | 重述版：无需改守卫；若要收敛，在 `findByKey` 处对「多行同 key」返回首个并记审计（当前 0 例，低优先）。原版 A11：conductor 对 `validate_roadmap` 的非空结果拒绝消费（或按 stage 逐个 key 去重前先报错） |

---

## 2. 豁免清单建议（A5/AC-006 的判据形态）

### 2.1 框架自己保留的 `_`/`.` 名字（实测 + 常量定义处）

磁盘实测（`.agenticdoc/` 根目录，`reserved_root_entries`）：

| 名字 | 类型 | 是否框架自有（证据） |
|---|---|---|
| `_scratch` | dir | 是：`shared/paths.ts:16` `SCRATCH_WORKERS_KEY = "_scratch"`（唯一被设计为「可写 owner key」的保留名） |
| `.mw` | dir | 是：`shared/index-store.ts:60` 锁路径 `<project>/.mw/index.lock`（索引写锁）+ serve 状态（`.mw/mw.pid`、`serve.meta` 等） |
| `_index.parallel` | file | 是：`index-store.ts:59` |
| `_index.md` | file | 是：`index-store.ts:219` |
| `_workers.parallel` | file | 是：`packages/multi-workers/mw_common.py:1579-1580` |
| `_workers.stale.parallel` | file | 是：`mw_common.py:160` `STALE_FILE_NAME` |
| `_workers.acked` | file | 是：`mw_common.py:1587` `ACKED_FILE_NAME` |
| `_autopilot` | dir | 是：`mw_common.py:2593` `_GATE_DIR_REL`、`:2864` `_CROSSKEY_EVIDENCE_REL` |
| `_project_log.md` / `_arch_snapshot.md` / `_pitfalls.md` | file | 是：`.agents/skills/agentic-task/scripts/advance_phase.py:28` `MEMORY_DOCS` |
| `_incidents` | dir | **否**（`rg -F '_incidents' packages/coding-agent/src` 0 命中；是 IN-3 事故的非框架产物） |
| `.agenticdoc` | dir | 是：`paths.ts:10` `AGENTICDOC_DIR` |

锚点快照结论：`_index.parallel` 中 `_`/`.` 前缀行 = **0**；带 live claim 的 `_`/`.` 前缀 key = **0** ⇒ **当前 0 例真实暴露**，A5 是「判据形态漏洞 + 触发路径已通」，不是「已被触发的既成损害」。

### 2.2 建议判据（替换 `:250` 的无条件前缀豁免）

```
放行（return null）当且仅当满足其一：
  (a) key === SCRATCH_WORKERS_KEY（"_scratch"，唯一设计内的 ad-hoc owner）
  (b) 该 key 未在 _index.parallel 出现 且 不在保留名单内   ← 新 key 引导路径
  (c) 该 key 在 _index.parallel 出现且 claimState(claimId, self) !== "held-live"
拒绝（返回 refusal）：
  held-live 的 key，无论名字是否以 `_`/`.` 开头
另外无条件拒绝（即便 (b) 成立）：
  key ∈ 保留名单（下表）；前缀豁免本身不构成任何豁免理由
```

显式保留名单（拒绝，作为 `key:` 传给 `dispatch_worker` / `advance_phase` / `/worker` 时）：

```
_scratch(仅作为 owner 放行，不作为可 advance 的 key)
_index.parallel  _index.md  _workers.parallel  _workers.stale.parallel  _workers.acked
_autopilot  _project_log.md  _arch_snapshot.md  _pitfalls.md  _impl_gate.log
_incidents  .mw  .agenticdoc(根)
```

理由：这 12 个名字里每一个都已经是**文件/目录**（不是 key 命名空间）；一旦当作 ownerKey，`workerTaskDir(agenticDocRoot, ownerKey, taskKey)`（`paths.ts:38-40`）会生成 `<保留名>/workers/<task>/`，例如 `.agenticdoc/_workers.parallel/workers/t1/`——在队列文件同级建目录，既污染框架文件命名空间又不会被任何守卫拦。

### 2.3 与「新 key 引导」的边界

- `dispatch_worker` 的「新 key bootstrap」语义（`ui-bridge.ts:241-243` 注释：写 spec.md → advance → dispatch）应当以「**未在 `_index.parallel` 出现**」为判据，而不是以「名字带前缀」为判据。
- `advance_phase` 工具已经用前缀做了拒绝（`ui-bridge.ts:2045-2053`，返回「reserved prefix」）——但它拒的是**所有** `_`/`.` 名字（含真实保留名 `_scratch`），而 `claim`/`dispatch` 又恒放行：**同一语义在两处的方向相反**。建议把这段前缀判断与守卫共用同一份「保留名单 + 未索引即新 key」判据，消除方向不一致。

---

## 3. 可复现的反例命令（全部只读）

> 前置：`cd H:\git\Multi-Workers`。以下命令只 import 生产源码 + 读文件，不写任何文件。

### R1 —— A5：前缀恒豁免（函数级）
```bash
node --experimental-strip-types -e "const m=await import('./packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts'); const w=await import('./packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts'); const st=new m.IndexStore('.agenticdoc'); for (const k of ['_tmp','_workers.parallel','.mw','_scratch','xkey-repair-mechanism']) console.log(k, '=>', w.foreignLiveClaimRefusal(st,k)===null?'ALLOW':('REFUSE'));
"
```
锚点快照期望输出：`_tmp => ALLOW`、`_workers.parallel => ALLOW`、`.mw => ALLOW`、`_scratch => ALLOW`、`xkey-repair-mechanism => REFUSE`（后者证明同一 store 上 held-live 会被拒 ⇒ 前缀是唯一豁免原因）。

### R2 —— A6：大小写变体绕过 + Windows 同一物理目录
```bash
node --experimental-strip-types -e "const fs=await import('node:fs'); const m=await import('./packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts'); const w=await import('./packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts'); const st=new m.IndexStore('.agenticdoc'); for (const k of ['mw-guard-form-hardening','MW-GUARD-FORM-HARDENING','Mw-Guard-Form-Hardening']) { const r=st.findByKey(k); console.log(k,'row='+(r?r.claimId:'null'),'guard='+(w.foreignLiveClaimRefusal(st,k)?'REFUSE':'ALLOW')); } console.log('case-insensitive dir:', fs.existsSync('.agenticdoc/MW-GUARD-FORM-HARDENING'));
"
```
锚点快照期望输出：精确名 `row=WENBOZHOU-PC4:117296 guard=REFUSE`；两个变体 `row=null guard=ALLOW`；最后一行 `true`（Windows 上同一目录）。

### R3 —— A7：零 active 行时，隐式路径落到他人 live key（**当前语料即成立**）
```bash
node --experimental-strip-types -e "const m=await import('./packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts'); const w=await import('./packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts'); const p=await import('./packages/coding-agent/src/extensions/agent-team-loop/shared/phase-docs.ts'); const root='.agenticdoc'; const real=new m.IndexStore(root); console.log('activeEntry =', real.activeEntry()===undefined?'undefined (回退可达)':real.activeEntry().key); console.log('indexMdActive =', m.readIndexMdActive(root)); const stub={activeEntry:()=>undefined, findByKey:(k)=>real.findByKey(k)}; const owner=w.resolveOwnerKeyWithSync({sendMessage(){}}, stub, {key:undefined}, undefined, root); console.log('隐式 ownerKey =', owner); console.log('该 key 守卫 =', w.foreignLiveClaimRefusal(real, owner)?'REFUSE':'ALLOW'); console.log('docs gate gaps =', JSON.stringify(p.dispatchDocGaps(root, owner, 'DONE')));
"
```
锚点快照期望输出：`activeEntry = undefined (回退可达)`；`indexMdActive = xkey-repair-mechanism`；`隐式 ownerKey = xkey-repair-mechanism`；`该 key 守卫 = REFUSE`；`docs gate gaps = []`。⇒ 守卫会拒，但 `ui-bridge.ts:1676` 的 `if ((key ?? "").trim())` 使隐式分支**根本不调用守卫**。

### R4 —— A9：新鲜度轴随 `run.json` 缺失而关闭（纯函数级）
```bash
node --experimental-strip-types -e "const d=await import('./packages/coding-agent/src/extensions/agent-team-loop/shared/deliverable-evidence.ts'); const rs=await import('./packages/coding-agent/src/extensions/agent-team-loop/shared/run-store.ts'); console.log('readRunState on a task dir without run.json =', rs.readRunState('.agenticdoc/mw-guard-form-hardening/workers/mwgf-rq5-key-identity')===undefined?'undefined => startedAtMs=NaN => :168 比较被跳过':'present');
"
```
（本 worker 目录在运行中有 `run.json`；把参数换成任一已删除 `run.json` 的历史 task 目录即得 `undefined`。）读码坐标：`deliverable-evidence.ts:155`（取 `started_at`）+ `:168`（`Number.isFinite(startedAtMs) &&` 短路 ⇒ 缺记录即关轴）。

### R5 —— A11：两源不合并 + 原版 A11 坐标
```bash
node --experimental-strip-types -e "const m=await import('./packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts'); const rows=new m.IndexStore('.agenticdoc').readAll(); const g=new Map(); for (const r of rows){const k=r.key.toLowerCase(); g.set(k,new Set([...(g.get(k)??[]), r.key]));} console.log('rows=',rows.length,'exact_dups=',JSON.stringify(rows.map(r=>r.key).filter((k,i,a)=>a.indexOf(k)!==i))); console.log('case_only_dups=',JSON.stringify([...g.values()].filter(s=>s.size>1).map(s=>[...s]))); console.log('prefix_keys=',JSON.stringify(rows.filter(r=>r.key[0]==='_'||r.key[0]==='.').map(r=>r.key)));"
rg -n -F 'stage_of_key' packages/multi-workers/autopilot/roadmap.py packages/multi-workers/autopilot/conductor.py
rg -n -F 'validate_roadmap ran but the conductor does not enforce it yet' packages/multi-workers/mw_common.py
rg -n -F 'run_ledger_conflict' packages/multi-workers/mw_common.py
rg -c -F 'run.json' packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts   # 期望：0 命中（面板不消费 run.json）
```
锚点快照期望：`rows= 52`、`exact_dups= []`、`case_only_dups= []`、`prefix_keys= []`；`roadmap.py:477-483`、`conductor.py:2562-2567`、`mw_common.py:3422-3426`（doctor 自证 conductor 不消费 validate）、`mw_common.py:2468-2496/3306-3311`。

### R6 —— A5 触发路径可达性（读码）
```bash
rg -n -F 'pm-key' packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts | head -5   # :850-871 /pm-key new，无 key 形态校验
rg -n -F 'def cmd_claim' H:/git/Multi-Workers/.agents/skills/agentic-task/scripts/update_index.py  # :361 起，claim 无 key 形态校验，:393 置 active
rg -n -F 'reserved prefix' packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts    # :2053（advance_phase 反而拒所有 _/. 前缀）
```

---

## 4. 未验证 / 边界声明

1. **A5 未做端到端实写复现**：制造「他人 live 持有 `_tmp`」需要在 `_index.parallel` 里新增一行（写操作），本次为只读 research，**未做**。已证的是：(a) 前缀分支在 claim 查询之前且无条件；(b) 同一 store 上 held-live 的非前缀 key 会被拒；(c) `/pm-key new` 与 `update_index.py claim` 均无 key 形态校验且会置 `active`。⇒ 结论强度：**判据与触发路径成立，端到端未实测**。
2. **A7 的前置条件依赖「零 `status==active` 行」**，而该状态在锚点快照成立、在 15:19Z 快照不成立（`mw-console-title-clobber` 曾 active）。是否长期成立取决于其他窗口的 claim 行为，**不是守卫本身的不变量** ⇒ 修复应在守卫侧（回退结果也过 claimState），不应假设该状态不会出现。
3. **A9 中「writeless 角色删除自己 `run.json`」的执行路径未实测**（需真跑一个 research worker）。已证的是读码与纯函数语义：`run.json` 在 `worker-mode.ts:1217`（**任何 agent turn 之前**）写入 ⇒ 正常 run 必有该文件，故轴失效的现实触发是删除/损坏/写失败（写为 best-effort，`run-store.ts:155-166`）。
4. **原版 A11（roadmap 跨 stage 重复 key）未实测**：未构造含跨 stage 重复 key 的 roadmap 跑 conductor。判定依据为 `validate_roadmap` 报错 + doctor 文案自证 conductor 不消费其结论 + `stage_of_key` 首声明胜出 + `conductor.py:2566-2567` 的终态抑制。
5. `_index.parallel` 是**并发写目标**：本节所有行级数值仅对 §0 的 sha256 成立。
6. 未运行 `vitest` / `npm run check` / `npm run build` / `mw build`（按任务纪律留给 PM）。

---

## 5. 危害面排序与最小修复建议（供 PM 定 AC-006/AC-007 范围）

| 优先级 | 议题 | 最小修复 | 判据建议（可机器度量） |
|---|---|---|---|
| P0 | **A7** | `ui-bridge.ts:82` 回退分支补 claim 检查（或 `:1676` 去掉显式 key 条件，隐式分支同样过守卫） | `implicit_foreign_owner_writes == 0`（构造成员：`activeEntry()===undefined` + `_index.md active:` 指向 held-live key + 无 watch key + 无显式 `key`） |
| P0 | **A5** | `:250` 前缀豁免改为「显式保留名单 + 未在 `_index.parallel` 出现」 | `exempt_live_key == 0`（构造成员：活 `_tmp` 必须被拒） |
| P1 | **A6** | `findByKey`/`claim`/`upsert` 统一 `toLowerCase()` 归一（或先查大小写不敏感再判冲突） | `case_mismatch_bypass == 0`、`case_only_dup_rows == 0` |
| P2 | **A9** | `deliverable-evidence.ts:168` 改为「无 `run.json` ⇒ evidence 引用不算交付」 | `stale_evidence_accepted_without_run_json == 0` |
| P3 | 原版 A11 | conductor 拒绝消费 `validate_roadmap` 非空的 roadmap | `gate_suppressed_by_invalid_roadmap == 0` |

以上均落在 spec §3 AC-006（key 身份判据）与 AC-007（决策可观测性）的判据口径内；A9 建议归入 AC-007 的「放行必须在判定不确定时留审计行」，而不是 AC-006。
