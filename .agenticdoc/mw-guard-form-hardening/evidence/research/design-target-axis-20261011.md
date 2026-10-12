# DRQ-2 报告 — PM 侧「目标集轴 + 路径判定」定稿设计（`pm/ui-bridge.ts`）

- 任务：`.agenticdoc/mw-guard-form-hardening/workers/mwgf-drq2-target-axis-design/task.md`
- phase：DESIGN（只读研究）。**未修改任何源码/测试**；仓库内唯一写入 = 本 `report.md`。
- 输入：`evidence/research/spec-path-resolution-20261011.md`（RQ-3，43,156 B）；`spec.md` §3 AC-003/AC-004 + §7/§8；`pm-state.md` D-009/D-011；`packages/coding-agent/test/suite/mwds-t02-write-intent.test.ts`。
- 本轮新增实测：只读 Node 探针（stdin，无仓库临时文件）复现 RQ-3 的 CURRENT/HYP 轴、并**新增两个「前向扫描」变体的度量**（§0.3、§8）。未运行 vitest / npm run check / build；未调 `mw` 写面命令。
- 所有结论给 `文件:行号`（锚定当前工作树）。未验证项集中列在附录 B。

---

## §0 结论摘要

1. **判定顺序定稿**（§1）：`collectWriteIntentHits` 只做「verb → gap ≤32 → **锚定的宽字符类** token」发现（删掉 `WRITE_INTENT_PATH_RE` 的扩展名枚举与 `pm.index !== 0`），`judgeWriteTarget` 按 **形状识别 → deny 前缀 → 允许面 realpath → 无目录成分的 basename 白名单 → 形状拒判 → 非候选放行** 求值；`isWhitelistedWriteTarget` 退化为 `judgeWriteTarget(...).allowed`（布尔 API 不变，新增判定携带 `rule` 的导出函数供 AC-008 分支测试）。
2. **A3/A4 两处漏放均可修且方向正确**：定稿在一个只读原型上实测 `config.toml/Makefile/.env/x.html/x.rs` **leak_caught = 5/5**（现实现 0/5，PM 已用已安装 bundle 复现），26 本真实 writeless 语料 `hits 2→13 / violations=1 / FP=0`（§0.3）。
3. **对 RQ-3 的两处裁决修正（本轮实测证据）**：
   - **(a) 「向前扫描第一个形状 token」被否决**。最保守的 ASCII-only 前扫变体在 26 本语料上仍引入 1 条新假阳性（`mw-rag-integration-design-critique` 的 `url/`），更宽松的变体引入 11 条 ⇒ 会击穿测试的 `false_positives == []` 硬断言。定稿 = **只取 verb 后紧邻的第一个 token**，`hits=13` 的口径正来自此（与 PM 锚定的期望值一致）。
   - **(b) RQ-3 §0.1 称 `:1406` 的 `pm.index !== 0` 会让「整条 clause 被放弃」**——代码级不成立：`:1406` 位于 `for (const verb of WRITE_INTENT_VERBS)` 内，`continue` 只跳过**当前 verb**，不是整条 clause。真正的机制是「该 clause 内没有其它 verb 命中」。定稿改为锚定 RE（`^`），`pm.index !== 0` 自然消失（永远为 0 或直接不匹配）。行为结论不变（`Output: write your report to <path>` 类仍在 fail-open 侧，见 §1.4 残余 R-2）。
4. **残余 fail-open（必须登记）**：verb 后第一个 token 是散文词时，同一 clause 内更靠后的路径不被判（`write your report to <path>` 型）。语料里该形态的 2 个实例都良性（① `fmr-review-spec-design/task.md:21` 的目标在自身 taskDir 内；② `msc-qg-quality-gate/task.md:37` 是 PM 归因，由新增的英文 PM 归因词表覆盖）。见 §1.4 R-2、§2.6。
5. **允许面复用 `worker/read-scope.ts`**（§3）：跨目录 import 已在本文件成立（`pm/ui-bridge.ts:31-32` 已从 `../worker/*` 引入），`read-scope.ts` 只依赖 `node:fs`/`node:path`/`minimatch`（`:20-24`），无环、无 pi 依赖 ⇒ **直接 import `normalizeForCompare`/`isSameOrUnder`，不写副本**。
6. **deny 表 = `worker-mode.ts:923-937` 逐条同表同优先级**（§4），PM 侧以 `keyDir`/`trueRoot` 为参数、`pmWriteDenyReason` 同形实现；`Makefile` 类无扩展名目标 = **deny-name 表（11 名）+ `existsSync` 兜底**，残余是「新建的、名字不在表里、且当前不存在」的裸文件名（§2.5 R-3）。
7. **Windows 9 项全部落在拒绝侧**（§5，本机 Node v24.19.0 独立复核 RQ-3 附录 C）：`realpath` **不做大小写归一**（`PACKAGE.JSON` 原样返回，`stat=4268`）⇒ 必须复用 `isSameOrUnder` 的 win32 小写比较；尾点/尾空格/`C:foo`/UNC/`\\?\`/ADS 全部 `ENOENT|EISDIR|UNKNOWN` ⇒ 只会假阳性、不产生漏放。
8. **回归改造点（§6）**：语料回放的两条硬断言（`false_positives == []` ∧ 唯一真阳）**不动**；`[VERIFY]` 行 `hits` 由 2 变 13。**必须动的一条断言是 `test/suite/mwds-t02-write-intent.test.ts:445`**——它把 `.agenticdoc/k/workers/t02/report.md`（有目录成分、且不在 taskDir 内）断言为 `true`，这正是 A4 目录盲判被写进测试的形态，新轴下应为 `false`。这是「只改断言、不加宽判据」的唯一必改项。
9. **`ui-bridge.ts` 归属的 QG-B 未覆盖分支 = 3 条**（§7）：`:250`（A5）、`:82`（A7）、`:1345-1346`/`:1402-1406`（A3）；另登记 A4（`:1423-1431`，AC-003，不在 QG-B 的 14 条内但同文件同函数族）。
10. **不做什么**（§8）：无界前扫（实测 11 FP）、ASCII-only 前扫（实测 1 FP）、裸 token fail-closed（RQ-3 35% FP）、把 `<key>/evidence` 并入允许面（P-05）、反引号纳入 quotation 对（会杀掉唯一真阳）、在 `ui-bridge.ts` 重写归一（第三份副本）。

### §0.1 现状坐标（锚定当前工作树）

| 项 | 坐标 |
|---|---|
| 写意图动词表（16） | `pm/ui-bridge.ts:1266-1281` |
| guard 名表（5） | `:1287-1293` |
| gap 窗口 32 | `:1299` |
| 框架 basename 白名单 | `:1303` |
| negation / read-marker / PM 归因 / 引号对 | `:1305-1316` / `:1317-1337` / `:1338` / `:1339-1343` |
| 英文动词集合 | `:1344` |
| **扩展名枚举 RE（A3 根因）** | `:1345-1346` |
| `collectWriteIntentHits` | `:1392-1421`（gap `:1404`；`pm.index !== 0` `:1405-1406`） |
| **`isWhitelistedWriteTarget`（A4 根因）** | `:1423-1431`（basename `:1426`/`:1427` **先于** `path.resolve` `:1428-1430`） |
| `judgeWriteIntent` | `:1444-1461` |
| 生产调用点 | `:1744-1749`（`dispatch_worker`，作用域内有 `agenticdocRoot`/`ownerKey`）、`:2200-2205`（`/worker`） |
| deny 表（运行期，同表来源） | `worker/worker-mode.ts:923-937`（`keyDir`/`trueRoot` 定义 `:632-646`，构造 `:1467-1474`） |
| 允许面归一（复用目标） | `worker/read-scope.ts:84`（`IS_WIN32`）/`:89-93`（`isSameOrUnder`）/`:100-114`（`normalizeForCompare`） |
| 第二份归一（副本先例，勿再增） | `shared/target-config.ts:155-175`（`normalizeRoot`，用 `realpathSync.native`） |
| `WORKER_FILE_NAME_RE` | `worker/worker-file-tool.ts:41` |

### §0.2 定稿判定链（一图）

```
verb 命中（:1266-1281 + findWriteIntentVerb :1363-1372，窗口 32 :1299）
  └─ 锚定 token：^[A-Za-z0-9_.\/~:-]+   （替换 :1345-1346，删除 :1406 的 index 锚定）
       └─ 5 guard（negation / read-marker / PM 归因（含英文）/ quotation / fenced-code 在 :1393）
            └─ hit{verb,path,clause}                        ← 语料 hits=13
judgeWriteIntent（:1444-1461，仅 writeless∧¬shell）
  └─ judgeWriteTarget(token, ctx)：
       形状识别 → deny 前缀 → 允许面 realpath（先目录） → 无目录成分的 basename 白名单
         → 形状 ⇒ 拒(scope) → 非候选 ⇒ 放行              ← 语料 violations=1，FP=0
```

### §0.3 本轮只读实测（新证据，锚定当前工作树）

方法：`node --input-type=module -`（stdin，无临时文件），逐字复刻 `collectWriteIntentHits` 的 verb/gap/guard 语义（guard 词表从源码 UTF-8 文本读取，避免 shell 编码损坏），语料 = 仓库真实 `.agenticdoc/**/workers/*/task.md` 中 `isWritelessRole(type) && !isShellRole(type)` 的 26 本。

| 变体 | 定义 | `hits` | `violations` | QG-B 5 样例 |
|---|---|---|---|---|
| **CURRENT** | 现实现（`:1345-1346` 扩展名枚举 + `:1406` index 锚定） | 2 | 1 | 0/5 |
| **定稿 V1** | 锚定宽字符类 token（**第一个** token）+ 形状分类 + 允许面 + deny | **13** | **1** | **5/5** |
| V2 | V1 之后「无界前扫」到第一个形状 token（自定义分词） | 48 | 12（+11 FP） | 5/5 |
| V3 | V1 之后「ASCII-only 有界前扫」（跳过纯 ASCII 单词、遇 CJK 或 gap>24 停止） | 13 | 3（+2 FP） | 5/5 |
| V3 + 英文 PM 归因 guard | 同上 | 12 | 2（+1 FP） | 5/5 |

V1 的 13 条命中（逐条，形状/判定）：`your`、`side`、`-pattern`、`design`、`surface`、`mcp`×2、`message_update`、`design` = **BARE 非候选 ⇒ 放行**；`output.md` = **无目录成分 + 框架名 ⇒ 放行**；`/` = **PUNCT 非候选 ⇒ 放行**；`.agenticdoc/mw-gate-verdict-hardening/evidence/quality-gate-report-review-20261010.md` = **SEP + 允许面外 ⇒ 违规（唯一真阳，与现实现逐字相同）**。
V3 的残余 FP：`mw-rag-integration-design-critique/task.md:32`「指纹是否覆盖 mcp url/端点？」→ 前扫跳过 `mcp` 后取到 `url/`（SEP）。V2 的 11 条 FP 同族（`覆盖 spec.md`/`覆盖完整性`、`url/端点` 等）。

> 结论：**「verb 后紧邻 token」是唯一同时满足 `hits=13 / violations=1 / FP=0` 与 5/5 覆盖的抽取口径**。前扫（RQ-3 §2.2 的推荐）必须否决。

---

## §1 判定顺序定稿（交付物 1）

### 1.1 类型与常量增补（`pm/ui-bridge.ts`）

```ts
// 替换 :1345-1346：不再枚举扩展名
const WRITE_INTENT_TOKEN_RE = /^[A-Za-z0-9_.\\/~:-]+/;

// 新增：非候选形态的显式 carve-out（每项都能在真实语料里指到实例）
const WRITE_INTENT_ABBREVIATIONS = new Set(["e.g", "i.e", "etc", "vs", "cf"]);

// 新增：无扩展名目标的 deny-name 表（RQ-3 §2.4；Makefile 类）
const WRITE_INTENT_DENY_NAMES = new Set([
  "Makefile", "makefile", "GNUmakefile", "Dockerfile", "Containerfile",
  "Rakefile", "Gemfile", "Procfile", "Vagrantfile", "Justfile", "Brewfile",
]);

// 扩展 :1338（同一 guard 族内加英文形态，不改 WRITE_INTENT_GUARDS 的 5 项计数）
const WRITE_INTENT_PM_ATTRIBUTIONS: readonly string[] = [
  ...现有 6 条中文..., "pm will write", "pm would write", "pm can write",
  "pm may write", "pm should write", "pm must write", "the pm will write",
];

export type WriteTargetShape =
  | "punct" | "version" | "abbrev" | "bare"                       // 非候选
  | "sep" | "dot-lead" | "drive-relative" | "ads" | "colon" | "ext" | "deny-name" | "exists"; // 路径形状

export type WriteTargetJudge = {
  allowed: boolean;
  shape: WriteTargetShape;
  /** 仅 allowed=false 时存在：与 AC-005b 同族规则名。 */
  rule?: "shape" | "scope" | "deny";
  detail?: string;
};
```

### 1.2 形状判定（新增导出，纯函数，只读 fs）

```ts
export function classifyWriteTargetShape(
  pathToken: string,
  ctx: { projectRoot: string },
): WriteTargetShape {
  const t = pathToken.replace(/[.\s]+$/, "");      // Win32 尾点/尾空格语义（§5-6）
  if (t === "" || !/[A-Za-z0-9]/.test(t)) return "punct";        // `/`、``、`——`
  if (/^\d+(\.\d+)+$/.test(t)) return "version";                 // 1.2.3
  if (WRITE_INTENT_ABBREVIATIONS.has(t.toLowerCase())) return "abbrev"; // e.g. / i.e.
  if (/[\\/]/.test(t)) return "sep";                             // 有目录成分
  if (/^\.[A-Za-z0-9_]/.test(t)) return "dot-lead";              // .env / .gitignore
  if (/::/.test(t)) return "ads";                                // x.md::$DATA
  if (/^[A-Za-z]:(?![\\/])/.test(t)) return "drive-relative";    // C:foo
  if (t.includes(":")) return "colon";                           // 其余冒号，可疑面
  if (/\.[A-Za-z0-9]{1,8}$/.test(t)) return "ext";               // 扩展形状，不枚举
  if (WRITE_INTENT_DENY_NAMES.has(t)) return "deny-name";        // Makefile 类
  if (fs.existsSync(path.resolve(ctx.projectRoot, t))) return "exists"; // README 类
  return "bare";                                                 // 裸词 ⇒ 非候选
}

const WRITE_TARGET_PATH_SHAPES: ReadonlySet<WriteTargetShape> = new Set([
  "sep", "dot-lead", "drive-relative", "ads", "colon", "ext", "deny-name", "exists",
]);
```

**求值顺序已在形状函数内固化**：`punct → version → abbrev → sep → dot-lead → ads → drive-relative → colon → ext → deny-name → exists → bare`。把 `drive-relative`/`ads` 放在 `ext` **之前**，是为了让 `C:foo.md`（`§5-5`）与 `x.md::$DATA`（`§5-4`）拿到准确规则名，而不是被 `.md` 吞成 `ext`（判定结果相同，仅规则名不同）。

### 1.3 三个定稿函数（伪代码 = 可直接落地的形状）

```ts
// ── collectWriteIntentHits（重写 :1392-1421 的 3 行核心） ──────────────────
export function collectWriteIntentHits(text: string): WriteIntentHit[] {
  const body = text.replace(/```[\s\S]*?```/g, "");                    // fenced-code guard（保持 :1393）
  const hits: WriteIntentHit[] = [];
  for (const line of body.split(/\r?\n/)) {
    for (const clause of line.split(/[。；！？;]/)) {                   // 分隔符不变
      const low = clause.toLowerCase();
      for (const verb of WRITE_INTENT_VERBS) {                         // 顺序不变（最长优先）
        const pos = findWriteIntentVerb(clause, verb);
        if (pos < 0) continue;
        const after = clause.slice(pos + verb.length);
        const gapLen = (/^\s*[`"']?\s*/.exec(after)?.[0].length) ?? 0;
        if (gapLen > WRITE_INTENT_PATH_WINDOW) continue;               // ≤32 不变
        const m = WRITE_INTENT_TOKEN_RE.exec(after.slice(gapLen));     // ← 锚定；替换扩展名枚举
        if (m === null) continue;                                      // ← 删除 `pm.index !== 0`
        const token = m[0].replace(/[.]+$/, "");
        if (token === "") continue;
        const before = low.slice(Math.max(0, pos - 20), pos);
        if (WRITE_INTENT_NEGATIONS.some((n) => before.includes(n))) continue;
        if (WRITE_INTENT_READ_MARKERS.some((r) => low.includes(r))) continue;
        if (WRITE_INTENT_PM_ATTRIBUTIONS.some((a) => low.includes(a))) continue; // 含新增英文形态
        if (pathInsideQuotation(clause, token)) continue;              // `"` `'` `「」`（不加反引号，§8-5）
        hits.push({ verb, path: token, clause: clause.trim() });
        break;                                                         // 每 clause 一个 hit（不变）
      }
    }
  }
  return hits;
}

// ── judgeWriteTarget（新增：带 rule 的判定，承载 AC-008 分支测试） ─────────
export function judgeWriteTarget(
  pathToken: string,
  ctx: { taskDir: string; projectRoot: string; keyDir?: string; trueRoot?: string },
): WriteTargetJudge {
  const shape = classifyWriteTargetShape(pathToken, ctx);
  const target = normalizeForCompare(ctx.projectRoot, pathToken);      // 复用 read-scope.ts:100
  const task = normalizeForCompare(ctx.projectRoot, ctx.taskDir);      // 复用 read-scope.ts:100

  // 步 1：deny 前缀（绝对优先；与 worker-mode.ts:923-937 同表）
  const denied = pmWriteDenyReason(ctx, target);
  if (denied !== null) return { allowed: false, shape, rule: "deny", detail: `denied:${denied}` };

  // 步 2：允许面 realpath + 段边界（复用 read-scope.ts:89 isSameOrUnder，win32 小写）
  if (isSameOrUnder(task, target)) return { allowed: true, shape };

  // 步 3：basename 白名单 —— **仅对无目录成分的 token 生效**（A4 的代码级修复点）
  const hasDirComponent = /[\\/]/.test(pathToken);
  if (!hasDirComponent && (WORKER_FILE_NAME_RE.test(pathToken) || FRAMEWORK_TASK_BASENAMES.includes(pathToken))) {
    return { allowed: true, shape };
  }

  // 步 4：形状像路径 ⇒ 拒（A3 的代码级修复点：不枚举扩展名）
  if (WRITE_TARGET_PATH_SHAPES.has(shape)) {
    return { allowed: false, shape, rule: "scope", detail: "outside-write-surface" };
  }

  // 步 5：非候选（punct/version/abbrev/bare 散文词）⇒ 不判（不是写目标）
  return { allowed: true, shape };
}

// ── isWhitelistedWriteTarget（布尔 API 保持，:1423-1431 变一行） ───────────
export function isWhitelistedWriteTarget(
  pathToken: string,
  ctx: { taskDir: string; projectRoot: string; keyDir?: string; trueRoot?: string },
): boolean {
  return judgeWriteTarget(pathToken, ctx).allowed;
}

// ── judgeWriteIntent（:1444-1461 只改 ctx 透传） ───────────────────────────
export function judgeWriteIntent(input: {
  type: string; description: string; taskDir: string; projectRoot: string;
  allowForeignWrite?: boolean;
  /** 新增，可选：提供时激活 deny 表（生产两个调用点均可用，见 §4.4）。 */
  keyDir?: string; trueRoot?: string;
}): WriteIntentVerdict {
  if (!isWritelessRole(input.type) || isShellRole(input.type)) return { ok: true, hits: [], violations: [] };
  const hits = collectWriteIntentHits(input.description);
  const ctx = { taskDir: input.taskDir, projectRoot: input.projectRoot, keyDir: input.keyDir, trueRoot: input.trueRoot };
  const violations = input.allowForeignWrite ? [] : hits.filter((h) => !isWhitelistedWriteTarget(h.path, ctx));
  return { ok: violations.length === 0, hits, violations };
}
```

### 1.4 「先目录后 basename」的代码级顺序证明点

**现状（反证）**：`:1423-1431` 的函数体按语句序为 ①`normalized`/`base`（:1424-1425）→ ②`WORKER_FILE_NAME_RE.test(base)` **return true**（:1426）→ ③`FRAMEWORK_TASK_BASENAMES.includes(base)` **return true**（:1427）→ ④`path.resolve` 目录比较（:1428-1430）。PM 已给出偏移证据：basename 判定 239/289 < 目录比较 361（`pm-state.md` D-011）。⇒ 任何 `…/output.md`、`…/report.md`、`…/task.md`、`…/trace.log`、`…/run.json`、`…/worker.log` 都无条件放行（含 `../other-key/workers/other-task/output.md`、`.agenticdoc/other-key/workers/other-task/output.md`，RQ-3 实测 `= true`）。

**定稿（顺序证明的 3 个可断言点）**：

| # | 证明点 | 断言方式（AC-008/AC-011 口径） |
|---|---|---|
| P1（源码序） | `judgeWriteTarget` 函数体内 `indexOf("isSameOrUnder")` < `indexOf("WORKER_FILE_NAME_RE")` 且 `indexOf("WORKER_FILE_NAME_RE")` < `indexOf("WRITE_TARGET_PATH_SHAPES")` | 读源码文本的 grep 断言（与 `mwds-t01` VC-011「文案=调用点」同法，可真实证伪） |
| P2（行为序） | `../other-key/workers/other-task/output.md` ⇒ false；`.agenticdoc/other-key/workers/other-task/output.md` ⇒ false；`..\\o\\pm-state.md` ⇒ false；`C:\\elsewhere\\trace.log` ⇒ false | 目录盲判反例集（AC-003 `dir_blind_bypass == 0`） |
| P3（等价性序） | 步 3 的前置条件显式含 `!hasDirComponent`；把该前置去掉（构造变体）时 P2 立即变红 | 反向控制组（红→恢复→绿），与 `evidence/scripts/mwds-controls.ps1` 同纪律 |

**为什么步 3 必须放在步 2 之后**：`output.md` 是 `ext` 形状（有扩展），它既要走框架通道（`FRAMEWORK_TASK_BASENAMES`），又必须在「有目录成分」时失效。用 `shape === "bare"` 做前置是**错的**（会把 `output.md`/`report.md` 从框架通道踢出去、让它们落进步 4 被拒），正确前置是 `!hasDirComponent`。这一点是 RQ-3 §6 第 3 步「token 无目录成分」的精确落地。

### 1.5 残余（定稿后仍存在，必须登记）

| # | 残余 | 方向 | 实测/依据 | 裁定 |
|---|---|---|---|---|
| R-1 | 形状像路径的散文：`foo.bar`、`and/or`、`12:30`、`write_scope:`、`.5` | **假阳性**（fail-closed，安全方向） | 26 本语料 0 实例（V1 violations=1） | 接受；追加语料即由 `FP==0` 硬断言暴露 |
| R-2 | verb 后第一个 token 是散文词时，同一 clause 内更靠后的真实路径不判（`write your report to <path>`） | **漏放**（fail-open） | 语料 2 实例均良性：`fmr-review-spec-design/task.md:21`（目标在自身 taskDir 内，放行正确）、`msc-qg-quality-gate/task.md:37`（PM 归因，由新增英文 PM 归因词表覆盖） | 接受 + 登记；**不得**用前扫修（§0.3、§8-1/2） |
| R-3 | 新建的、名字不在 deny-name 表、且当前不存在的无扩展名裸文件（`Taskfile` 变体） | 漏放 | RQ-3 §2.4 | 接受；deny-name 表可随审计增长（表是有限集合，不是扩展名枚举） |
| R-4 | 非 ASCII（中文）文件名：`写入 报告.md` 的 token 起点是 CJK，锚定 RE 直接不匹配 | 漏放 | RQ-3 附录 F-1（未验证） | 单列缺口，建议本 key 之外立卡；`报告.md` 若前面有空隙可由同一 RE 的 `^` 失败暴露（当前是「0 候选」而非「判为安全」） |
| R-5 | PM 派发期 realpath 与运行期 realpath 之间 TOCTOU（symlink/junction 被改） | 双侧 | RQ-3 §4（当前语料 0 reparse point） | 由 AC-005b 运行期守卫在写入时再判兜底 |

---

## §2 形状判定定稿表（交付物 2）

### 2.1 token 提取规则（替换 `:1345-1346`）

| 步骤 | 规则 | 依据 |
|---|---|---|
| T1 | verb 命中后，`gap = /^\s*[`"']?\s*/`，`gapLen > 32` 即放弃（不变，`:1299`/`:1404`） | 现状保留 |
| T2 | 从 `after.slice(gapLen)` **行首锚定**取 `/^[A-Za-z0-9_.\\/~:-]+/`；不匹配 = **本 verb 无候选**（不是「整条 clause 放弃」，`:1406` 的 `pm.index !== 0` 删除） | §0.3 V1 |
| T3 | 剥尾点 `/[.]+$/`（Win32 尾点语义） | §5-6 |
| T4 | 分词天然止于 `,` `;` `)` `「」` 空格 与所有 CJK ⇒ 不需要额外剥标点 | RE 字符类已排除 |
| T5 | token 内的**形状**由 `classifyWriteTargetShape` 判定（§1.2），不在提取期判 | AC-004 |

**不变量**：T2 的字符类**不含扩展名信息**，新增语言/新配置文件类型不会重新 fail-open（这正是 A3 的修复语义）。

### 2.2 形状分类表（规则 × 2 正例 × 2 负例）

判定顺序 = 表中自上而下（`§1.2` 固化）。「正例」= 规则命中 ⇒ 若不在允许面则 **拒**；「负例」= **不得**被判为外部写（无假阳性）。所有负例的现实现判定与定稿判定均已在本轮 V1 原型上复算（除标注「未验证」者）。

| # | 形状 | 规则 | 正例（⇒ 拒） | 负例（⇒ 放行/不判） |
|---|---|---|---|---|
| S0 | `punct` | `t===""` ∨ `!/[A-Za-z0-9]/` | `——`（破折号）、`「」` 单独出现 | **`/`**（来自 `` `process.stdout.write`/`print` ``，RQ-3 语料实命中 1 例）、`.` / `...` |
| S1 | `version` | `^\d+(\.\d+)+$` | `1.2.3`（语义上是版本号，**这条是 carve-out 而不是正例**） | `1.2.3`、`0.12.2` |
| S2 | `abbrev` | 停用表（大小写不敏感）`e.g i.e etc vs cf` | `e.g.`（若不自证则被 S3 当扩展）**carve-out** | `e.g.`、`i.e.` |
| S3 | `sep` | 含 `/` 或 `\` | `.agenticdoc/other-key/evidence/x.md`、`..\o\pm-state.md`、`C:\elsewhere\trace.log` | `/`（S0 拦）、`//`（S0 拦）；**残余**：`and/or`、`mcp url/端点`（S3 会拒 ⇒ 假阳性，语料 0 实例） |
| S4 | `dot-lead` | `^\.[A-Za-z0-9_]` | `.env`、`.gitignore`、`.npmrc`、`.agenticdoc/_index.parallel`（同时是 sep） | `.`（S0 拦）、`...`（S0 拦） |
| S5 | `ads` | 含 `::` | `package.json::$DATA`（本机 `existsSync=true`、`stat=4268` ⇒ 指向同一文件） | `:`（S0 拦）、`::`（S0 拦） |
| S6 | `drive-relative` | `^[A-Za-z]:(?![\\/])` | `C:package.json`（本机 resolve=`C:\package.json`、`realpath=ENOENT`）、`C:foo.md` | `C:\…`（S3 拦，是真绝对路径）、`D:/…`（S3 拦） |
| S7 | `colon` | 其余含 `:` | `write_scope:`（若被 verb 捕到 ⇒ 拒；语料未命中）、`12:30` | `:`（S0 拦）；**残余**：时间/键值对散文（假阳性） |
| S8 | `ext` | `\.[A-Za-z0-9]{1,8}$`（**不枚举具体扩展**） | `config.toml`、`x.html`、`x.rs`、`x.yaml`、`a.ts` | `1.2.3`（S1 拦）、`e.g.`（S2 拦）；**残余**：`foo.bar`（与真文件词法不可分 ⇒ 拒；可用 `existsSync` 或 `allow_foreign_write: true` 豁免） |
| S9 | `deny-name` | 11 名表（§1.1） | `Makefile`、`Dockerfile`、`Justfile`（本机均 `existsSync=false` ⇒ 只能靠表） | `README`（不在表内、本机不存在 ⇒ `bare` 放行，**残余漏放 R-3**）、`LICENSE`（本机存在 ⇒ 走 S10 拒，见下） |
| S10 | `exists` | `fs.existsSync(path.resolve(projectRoot, t))` | `LICENSE`（本机存在、无扩展）、`README`（若真实存在）、`docs`/`scripts`/`packages`（目录存在） | `README`（本机不存在 ⇒ `bare` 放行）、`Makefile`（不存在 ⇒ S9 拦）；**残余**：既存裸目录名出现在散文（如「输出到 docs」）会误拒（语料 0） |
| S11 | `bare` | 以上全不命中 ⇒ **非候选** | —（本形状恒放行，不存在正例） | **`your`**（`msc-qg-quality-gate`/`fmr-review-spec-design`）、**`design`**（`mwg-qg-review-20261010`/`mwg-qg2b-code-adversarial`）、**`mcp`**（`mw-rag-integration-design-critique`/`-design-review`）、**`side`**（`code-review-1`）、**`surface`**（`mwg-qg2b-code-adversarial`）、**`message_update`**（`mw-rag-integration-ref-verify`）、**`-pattern`**（`mds-qg-b-code-adversarial`）、**`README`**（不存在时） |

**验收口径**：S11 的 7 个散文词 + `-pattern` 在真实语料 26 本里共 10 条命中，V1 下 `violations` 增量 = **0**（RQ-3 §5 HYP-B 的 9/26 = 35% 假阳性正是「把这些也拒」的代价，已被 AC-004 明文禁止）。

### 2.3 `existsSync` 的调用面与代价

- 调用点唯一：`classifyWriteTargetTargetShape` 的 S10 分支（每个 hit ≤1 次，语料 13 次/26 本）。
- 只读 `existsSync`（不 stat 大目录），无写、无 mkdir ⇒ 保持 `judgeWriteIntent` 的零副作用验收（`mwds-t02`「refusal is zero-side-effect」用例：`:resolveSnapshot` 前后树哈希不变）。
- **必须传 `projectRoot`**：裸 token 的相对基准是 worker/PM cwd = project root（`worker-mode.ts:1470` 同语义）。

### 2.4 guard 族的两处补强（不新增 guard 计数）

| 补强 | 位置 | 理由 | 反例 |
|---|---|---|---|
| 英文 PM 归因（`pm will write` 等 7 形态）并入 `WRITE_INTENT_PM_ATTRIBUTIONS`（`:1338`） | 同一 `pm-attribution` guard 族 ⇒ `WRITE_INTENT_GUARDS` 仍 5 项，`:1287` 的枚举契约与测试 `:1180`/`cases` 不变 | 语料 `msc-qg-quality-gate/task.md:37`「PM will write your output verbatim to `.agenticdoc/…/evidence/quality-gate-report-<timestamp>.md`」是 **PM 归因**，不是 worker 写指令 | `PM will write your report to <path>` ⇒ 必须放行 |
| **不加** inline-code（反引号 span）guard | — | `/` 已是 S0 非候选，`process.stdout.write` 在 `:1404` 的 gap 与字符类下产出 `/` 或 `print`，都不进 S3+；新增 guard 会改 `WRITE_INTENT_GUARDS` 计数并触发未要求的测试改写 | — |

### 2.5 `Makefile` 类的三条覆盖路径与残余

```
写入 Makefile            → S9 deny-name（表） ⇒ 拒
写入 Makefile（目标仓库根真有该文件）→ S9 先命中，规则名仍是 deny-name
写入 LICENSE（存在、无扩展）→ S10 exists ⇒ 拒
写入 Taskfile（新建、不在表、当前不存在）→ S11 bare ⇒ 放行（残余 R-3）
```

- **为什么必须同时有表与 `existsSync`**：表覆盖「当前不存在的标准构建文件名」，`existsSync` 覆盖「任意已存在的无扩展名文件」。二者交集为空也无妨（S9 先于 S10）。
- **为什么不把 deny-name 表换成「无扩展名一律拒」**：那等于裸 token fail-closed（RQ-3 实测 35% 假阳性，AC-004 明文禁止）。

### 2.6 与 RQ-3 §2.3 反例清单的逐条对账

| RQ-3 反例 | 新轴判定 | 依据 |
|---|---|---|
| `1.2.3` | 非候选（S1） | `^\d+(\.\d+)+$` |
| `e.g.` / `i.e.` | 非候选（S2） | 停用表（剥尾点后为 `e.g`） |
| `foo.bar` | **拒（S8）** | 与真文件不可分；0 语料；`allow_foreign_write: true` 是唯一豁免 |
| `your`/`design`/`mcp`/`side`/`surface`/`message_update` | 非候选（S11） | 裸词 |
| `-pattern` | 非候选（S11） | 裸词（含 `-`，无点/无分隔符） |
| `/` | 非候选（S0） | 无字母数字 |
| `README` | 存在 ⇒ 拒（S10）；不存在 ⇒ 非候选（S11） | 残余漏放已登记 R-3 |

---

## §3 允许面实现方案（交付物 3）

### 3.1 定稿选择：**直接复用 `worker/read-scope.ts` 的导出，不写副本**

```ts
// pm/ui-bridge.ts 顶部（顶层 import，无内联 import —— 仓库纪律）
import { isSameOrUnder, normalizeForCompare } from "../worker/read-scope.ts";
```

`judgeWriteTarget` 的步 1/步 2 全部走这两个函数（§1.3 伪代码）。`worker-mode.ts` 的运行期写面守卫（`checkBashWriteScopeTarget`）用的是**同一对函数**，因此派发期与执行期的 allow 面在同一套语义上求值（AC-004「与 AC-005b 同一 deny 表」的前置）。

### 3.2 跨目录 import 的可行性（已核实，非推测）

| 检查项 | 结论 | 证据 |
|---|---|---|
| 同包内跨目录 import 是否已有先例 | **是** | `pm/ui-bridge.ts:31` `from "../worker/worker-file-tool.ts"`、`:32` `from "../worker/worker-mode.ts"`；`:37` `from "../shared/paths.ts"` 等 |
| 是否引入模块环 | **否** | `worker/read-scope.ts` 只 import `node:fs`（`:14`）、`node:path`（`:15`）、`minimatch`（`:16`）；无 pi 依赖、无 `pm/*` 依赖 ⇒ 加入 `ui-bridge` 的依赖图不产生回边 |
| 是否违反「纯决策逻辑、只读 fs、无写」契约 | **否** | `read-scope.ts:20-24` 模块头明写「pure decision logic (read-only fs, no pi dependency, no writes)」——正是 PM 侧需要的性质 |
| 可擦除 TS 语法约束 | **满足** | 只是普通 `import`；无 `enum`/`namespace`/参数属性/`import =` |
| 依赖方向是否是「pm 依赖 worker」 | 是（已有） | 与 `:32` 的 `isWritelessRole/isShellRole` 同一方向；`read-scope` 比 `worker-mode` 更底层，反向依赖不会出现 |

### 3.3 为什么**不**在 `ui-bridge.ts` 内写同语义副本

1. **会造出第三份归一实现**，仓库已有两份：`worker/read-scope.ts:100-114`（`realpathSync`）与 `shared/target-config.ts:155-175`（`normalizeRoot`，注释自称「junctions/case fold like the read-scope normalizer」，用的是 `realpathSync.native`）。第三份必然漂移（RG-B 的 seam 清单风格：同概念多实现 = drift 源）。
2. **win32 大小写归一只有一处实现**：`read-scope.ts:89-93` 的 `isSameOrUnder` 做 `toLowerCase()` 两侧比较，`IS_WIN32` 在 `:84` 冻结。现实现 `ui-bridge.ts:1428-1430` 的裸字符串 `startsWith` 是**大小写敏感**的（§5-1 实测 `PACKAGE.JSON` 原样返回）⇒ 复写等于把已知 bug 再抄一遍。
3. **「最深存在祖先回接」的语义**（`read-scope.ts:100-114` 的 `for(;;)` 回退）在 A3/A4 的裁决里是必需的：`report.md` 这种尚不存在的目标必须与已存在的 `taskDir` 可比（否则 realpath 抛 ENOENT 就退化为 `path.resolve` 字面量比较，junction 场景下两侧基准不一致）。复写这段循环是新增未测试代码。

### 3.4 单一语义保证（一致性测试）

新增 `test/suite/mwgf-drq2-target-axis.test.ts`（或并入 `mwds-t02`）的 **parity 用例**：

```ts
// 语义锚：same-normalizer parity（与 mwds-t05 的 oracle↔读侧 parity 同法）
import { isSameOrUnder, normalizeForCompare } from "../../src/extensions/agent-team-loop/worker/read-scope.ts";
import { judgeWriteTarget } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";

it("AC-004: PM write-target containment == read-scope containment (one semantics)", () => {
  const matrix = [
    { task: join(ROOT, ".agenticdoc/k/workers/t"), p: join(ROOT, ".agenticdoc/k/workers/t/report.md"), want: true },
    { task: join(ROOT, ".agenticdoc/k/workers/t"), p: join(ROOT, ".agenticdoc/k/workers/t2/report.md"), want: false },
    { task: join(ROOT, ".agenticdoc/k/workers/t"), p: join(ROOT, ".agenticdoc/k/workers/t/../t2/x.md"), want: false },
    { task: join(ROOT, ".agenticdoc/k/workers/t"), p: join(ROOT, ".agenticdoc/kk/evidence/x.md"), want: false }, // 段边界：kk ≠ k
  ];
  for (const c of matrix) {
    expect(isSameOrUnder(normalizeForCompare(ROOT, c.task), normalizeForCompare(ROOT, c.p)), c.p).toBe(c.want);
    expect(judgeWriteTarget(c.p, { taskDir: c.task, projectRoot: ROOT, trueRoot: join(ROOT, ".agenticdoc"), keyDir: join(ROOT, ".agenticdoc/k") }).allowed, c.p).toBe(c.want);
  }
});
```

要点：第三条 `t/../t2/x.md` 锁 `path.resolve` 的 `..` 折叠（`§5-1`），第四条锁**段边界**（`read-scope.ts:89` 的 `prefix + path.sep` 语义，`goal-autopilot-evil` 不匹配 `goal-autopilot`）、同时是 deny 表 `other-key` 的触发点。测试用 `os.tmpdir()` 造真实目录树（与 `mwds-t02` 的 `mkdtemp()` 同法），symlink/junction 分支用 `fs.symlinkSync`（Windows 下 junction type）构造；无权限时该分支 `skip` 并打 `[VERIFY]` 标记（不得静默）。

### 3.5 允许面参数（ctx）定稿

```ts
export type PmWriteSurfaceCtx = {
  /** 本任务目录（绝对或 project-root 相对） */
  taskDir: string;
  /** worker/PM cwd 基准 —— 裸 token 与相对 token 的解析根（= worker-mode.ts:1470 的语义） */
  projectRoot: string;
  /** 本 key 目录（`.agenticdoc/<key>`）；提供时激活 deny 表 */
  keyDir?: string;
  /** 真正的 `.agenticdoc` 根；提供时激活 deny 表 */
  trueRoot?: string;
};
```

- **生产调用点**（两处都可无成本提供，已核实作用域）：`ui-bridge.ts:1744-1749`（`agenticdocRoot`/`ownerKey` 在 `:1676`/`:1690` 作用域内）与 `:2200-2205`（`:2202` 的 `taskDir = workerTaskDir(agenticdocRoot, ownerKey, taskKey)` 同作用域）传 `keyDir: path.join(agenticdocRoot, ownerKey)`、`trueRoot: agenticdocRoot`。
- **缺省语义**：`keyDir`/`trueRoot` 缺失 ⇒ deny 表不激活（只有步 2/3/4/5 生效）。这不是放宽：当前允许面 = taskDir，而 deny 表里没有任何条目落在任一 taskDir 内部 ⇒ **deny 在当前允许面下被步 2/4 完全吸收**（判定结果不变），它存在的作用是（a）规则名（AC-007/AC-008 可观测）、（b）将来允许面放宽（AC-005b 的 `<key>/evidence`）时防止 `pm-state.md`/`_workers*` 被顺带放行。⇒ 这套缺省规则让 `judgeWriteIntent` 的既有签名保持可选扩展，不逼测试改传参。
- **`paths.ts:32-34` 的 `workerTaskDir` 逆函数**（keyDir/trueRoot 反推）已存在：`shared/paths.ts:38-44 controlRootFromTaskPath`。定稿不自动反推（避免 `PER` 场景下的退化误判，见 §4.4），只在生产显式传。

---

## §4 deny 表定稿（交付物 4）

### 4.1 表（逐条镜像 `worker/worker-mode.ts:923-937`）

```ts
/** PM 侧 deny 表：与 worker-mode.ts:923-937 `bashWriteDenyReason` 同表同序。
 * 返回值 = 机器可读规则名（写进 detail），null = 不 deny。
 * target 必须已经过 normalizeForCompare（realpath + win32 小写）。 */
function pmWriteDenyReason(
  ctx: PmWriteSurfaceCtx,
  target: string,
): string | null {
  const keyDir = ctx.keyDir;
  const trueRoot = ctx.trueRoot;
  if (keyDir !== undefined) {
    if (samePath(target, path.join(keyDir, "pm-state.md"))) return "pm-state.md";
    const workersDir = path.join(keyDir, "workers");
    if (isSameOrUnder(workersDir, target)) {
      const first = path.relative(workersDir, target).split(/[\\/]/)[0] ?? "";
      if (first.startsWith("_workers")) return "workers/_workers*";
    }
  }
  if (trueRoot !== undefined && samePath(target, path.join(trueRoot, "_index.parallel"))) return "_index.parallel";
  if (trueRoot !== undefined && keyDir !== undefined &&
      isSameOrUnder(trueRoot, target) && !isSameOrUnder(keyDir, target)) return "other key dir / .agenticdoc root";
  if (isSameOrUnder(path.join(ctx.projectRoot, "packages"), target)) return "packages/**";
  if (isSameOrUnder(path.join(ctx.projectRoot, ".git"), target)) return ".git/**";
  return null;
}

/** 双向相等（worker-mode.ts:918-920 samePath 的 PM 侧同名实现语义） */
function samePath(a: string, b: string): boolean {
  return isSameOrUnder(a, b) && isSameOrUnder(b, a);
}
```

| # | deny 条目 | 判定函数 | 语料取证（RQ-3 §2.1） | 新轴规则名 |
|---|---|---|---|---|
| D1 | `<key>/pm-state.md` | `samePath` | 55 key 中 45 有 `pm-state.md` | `denied:pm-state.md` |
| D2 | `<key>/workers/_workers*`（首段前缀） | `isSameOrUnder` + 首段 `startsWith("_workers")` | `.agenticdoc/_workers.parallel`、`_workers.acked`、`_workers.stale.parallel`、`mw-dispatch-flow-fixes/_workers.parallel` | `denied:workers/_workers*` |
| D3 | `<trueRoot>/_index.parallel` | `samePath` | 根目录有 `_index.parallel`/`_index.md` | `denied:_index.parallel` |
| D4 | `.agenticdoc` 下非本 key | `under(trueRoot) ∧ ¬under(keyDir)` | 55 key、305 本 task.md | `denied:other key dir / .agenticdoc root` |
| D5 | `packages/**` | `isSameOrUnder` | `packages/` 下 11 包 | `denied:packages/**` |
| D6 | `.git/**` | `isSameOrUnder` | `.git/` | `denied:.git/**` |

**顺序**：D1→D6 **先于**其它一切（`judgeWriteTarget` 步 1）；`write_scope:`/`allow_foreign_write` 只能放宽**允许面**，永不能放宽 deny（`worker-mode.ts:923` 头注 + `:959-986` 的实现序；AC-005b 同语义）。

### 4.2 `Makefile` 这类无扩展名目标的判定方式（→ deny **表**之外的第二张表）

`Makefile` 不属于 D1–D6 任何一条（它是 `projectRoot` 下的散落文件，不是 `.agenticdoc` 内）。它的判定**不在 deny 表**，而在**形状层的 deny-name 表**（§1.1 / §2.2 S9）：

- `写入 Makefile` → token `Makefile` → `classifyWriteTargetShape` S9 命中 `deny-name` → 步 3（无目录成分，但 basename 不在框架白名单）不生效 → 步 4 ⇒ **拒（rule=scope, detail=outside-write-surface）**。
- 之所以不放进 D1–D6：deny 表是「解析后的绝对路径面」（`worker-mode.ts` 用 `keyDir`/`trueRoot` 参数化），而 `Makefile` 是**裸文件名**，没有可依赖的目录锚；同时 `worker-mode.ts` 侧根本没有这条规则 ⇒ 放进 deny 表会破坏「同表」不变式。
- 它与 `existsSync`（S10）的关系：`Makefile` 在当前仓库根不存在（本机实测 `existsSync=false`）⇒ 只能靠表；若目标仓库根真有 `Makefile`，S9 先命中（表名），规则名仍稳定为 `deny-name`；`LICENSE` 这类「已存在、无扩展、不在表内」的裸文件由 S10 兜住。
- 残余：**新建的、不在 11 名表内、且当前不存在**的裸文件名（`Taskfile` 变体）仍漏（§1.5 R-3）；代价是可量化的（表是有限集合，替代方案是 35% 假阳性）。

### 4.3 与 AC-005b 的差异（必须写明，否则「同表」会被读成「同代码」）

| 维度 | AC-005b（`worker-mode.ts`） | 本 DRQ（PM 侧） |
|---|---|---|
| 允许面 | `taskDir` **+ `<key>/evidence`**（`:961-968`） | **仅 `taskDir`**（不并入 `<key>/evidence` —— AC-004/P-05 明文禁止，并入会让唯一真阳消失） |
| `write_scope:` 收窄 | 有（`:987-997`） | 无（writeless 角色没有 `write_scope:` header；`renderDefaultWriteScope` 只给 shell 角色，`ui-bridge.ts:1483-1485`） |
| token 来源 | bash 命令 tokenizer（`extractBashWriteCandidates`） | task.md 散文（`collectWriteIntentHits`） |
| deny 表 | D1–D6 | **D1–D6 逐条相同**（本节的「同表」仅指这张表） |

⇒ 文案口径建议：`design.md` §4 写「**同一张 deny 表 + 同一套允许面归一函数 + 不同的允许面内容**」，不要写「同一判定」。

### 4.4 为什么不从 `taskDir` 自动反推 `keyDir`/`trueRoot`

- 反推函数存在（`shared/paths.ts:38-44 controlRootFromTaskPath`），但在测试/临时布局（如 `mwds-t02` 的 `TASK_DIR = <tmp>/k/workers/t02`，`projectRoot = <tmp>`，没有 `.agenticdoc` 段）会退化：`trueRoot` 反推成 `<tmp>`，于是 D4「`.agenticdoc` 下非本 key」会把 `<tmp>` 下**一切**非 `<tmp>/k` 的目标判 deny —— 包括裸 `report.md`（resolve 到 `<tmp>/report.md`）⇒ **打爆 `mwds-t02` 的既有正例断言**。
- 定稿：**显式传参 + 缺省不激活**（§3.5）。生产两个调用点都显式传（成本 2 行）；测试里既有 `verdict()` 助手与语料回放不传 ⇒ deny 不激活、行为等价于「只判允许面」。

### 4.5 deny 的当前效力（诚实说明）

当前允许面 = `taskDir`，D1–D6 的六条**没有一条**落在任一 `taskDir` 内部（`_workers*` 是 taskDir 的**兄弟**，`pm-state.md` 是 key 根）⇒ **deny 在当前配置下被步 2/步 4 完全吸收，判定结果不变**。它的价值在：
1. 规则名（`denied:pm-state.md` 等）⇒ `judgeWriteTarget` 的 `rule`/`detail` 可被 AC-008 分支测试逐条钉住；
2. 防将来放宽：若后续给 shell 角色把 `<key>/evidence` 并入允许面（AC-005b 的做法），D1/D2/D3/D4 必须继续赢；
3. 双端一致性的可审计性（改 `worker-mode.ts:923-937` 时 PM 侧必须同步，或反之）。

---

## §5 Windows 9 项边界逐条裁定（交付物 5）

环境：Node **v24.19.0** / Windows（`process.platform === "win32"`，`path.sep === "\\"`）。下表「本机实测」为本轮独立复跑（`node --input-type=module -`，stdin）的原始值；`REPO = H:\git\Multi-Workers`。定稿的处理手段全部落在 §1.2/§1.3/§3.1 已给出的代码里，**不新增 Windows 专用分支**。

| # | 边界 | 本机实测（独立复跑） | 可判定性 | 建议处理（定稿） | 残余风险 |
|---|---|---|---|---|---|
| W1 | `..` / `.` / 混合分隔符 / 重复分隔符 | `packages/../package.json` → `H:\git\…\package.json`（realpath 同）；`.//package.json` → 同上 | **可**（纯词法） | `normalizeForCompare(projectRoot, token)` 第一步就是 `path.resolve`（`read-scope.ts:101`），win32 同时接受 `\` 与 `/` | 无 |
| W2 | 大小写不归一 | `PACKAGE.JSON` → realpath **原样返回**、`stat=4268`；`H:/GIT/MULTI-WORKERS/package.json` → `H:\GIT\MULTI-WORKERS\package.json`（不折） | **可**（比较层） | 比较必须走 `isSameOrUnder`（`read-scope.ts:89-93` 两侧 `toLowerCase`）；**禁止** `path.resolve` 后的裸 `startsWith`（现实现 `ui-bridge.ts:1428-1430` 的 bug） | 无（比较层已解决）。注意 deny 方向若用字典串前缀也会被大小写绕过 ⇒ 一律走同函数 |
| W3 | 盘符相对 `C:foo` | `C:package.json` → resolve `C:\package.json`、realpath/`stat` = `ENOENT`（按 Node 的 per-drive cwd） | **可判「不在允许面 ⇒ 拒」** | S6 `^[A-Za-z]:(?![\\/])` ⇒ `drive-relative` ⇒ 步 4 拒，reason 标 `win32-drive-relative`；**不要**用「不存在」当拒的理由 | 真实指向由 worker 进程同盘 cwd 决定，PM 无法静态得知 ⇒ 只会假阳性（安全方向）。反例形态 `C:foo.md` 也走 S6（在 S8 之前） |
| W4 | UNC `\\server\share\x.md` / `//server/share/x.md` | 两种写法 resolve 都归一为 `\\server\share\x.md`；realpath/`stat` = `UNKNOWN`（无可用共享） | **可**（词法可判「不在允许面」） | S3（含 `\` 或 `/`）⇒ 步 4 拒。段边界比较对 UNC 依然有效（`isSameOrUnder` 是串前缀 + `path.sep`） | 共享映射到允许面内（如 `\\localhost\C$\…<taskDir>`）会被词法比较放行**仅当**路径段与 `normalizeForCompare` 结果逐段一致；允许面外一律拒 ⇒ 只可能假阳性 |
| W5 | `\\?\` 长路径前缀 | `\\?\H:\…\package.json` 与 `//?/H:/…`：`realpathSync` = **EISDIR**，`statSync` = 4268 | **可（fail-closed）** | 不特判：`normalizeForCompare` 的「最深存在祖先回接」在 EISDIR 下退化为词法串（`read-scope.ts:100-114` 的 catch 分支），结果不在允许面 ⇒ 步 4 拒 | 合法 `\\?\` 引用被误拒（假阳性，安全方向）。**不要**为它加白名单（会开一条绕过 realpath 的通道） |
| W6 | 尾点 / 尾空格 | `package.json.`、`package.json `（尾空格）→ realpath/`stat` 均 **ENOENT**（本 Node/Windows 不剥） | **可**（形态层） | 提取期 T2 的字符类不含空格 ⇒ 尾空格天然截断；尾点在 T3 用 `/[.]+$/` 剥除（`classifyWriteTargetShape` 同样剥），与 Win32 `CreateFile` 语义一致 | 无漏放：无论 OS 剥不剥，`…/report.md.` 都落在 taskDir 内 ⇒ 允许；`Makefile.` 剥成 `Makefile` ⇒ deny-name 仍拦。仅假阳性 |
| W7 | ADS（`::$DATA`） | `package.json::$DATA` → realpath 原样返回，`stat=4268`（= 基文件大小）；本机 `existsSync=true` | **可**（形态层） | S5 `::` ⇒ `ads` ⇒ 步 4 拒，reason 标 `win32-ads`（必须先于 S8 `ext` 与 S10 `exists`，否则 `.md` 或 `existsSync` 会吞掉规则名） | 无漏放（同文件）；Win32 文件名本身不允许 `:` ⇒ 误拒面极小 |
| W8 | junction / symlink + 最深存在祖先 | `read-scope.ts:100-114` 已有实现；RQ-3 实测 `.agenticdoc`/`packages`/`.mw`/`.agents`/`docs`/`scripts`（深度 3，跳过 `node_modules`/`.git`）**0 个 reparse point** ⇒ 当前 realpath 是空操作 | **可（fs 调用）** | 一律 `normalizeForCompare`；所有失败模式（`ENOENT`/`EACCES`/`EISDIR`）都退回「最深存在祖先 realpath + 词法尾段」或纯词法 ⇒ 允许方向 fail-closed | TOCTOU（派发后 symlink 被改）+ 只 realpath 一次；由 AC-005b 运行期守卫在写入时再判兜底（§1.5 R-5） |
| W9 | 非 ASCII 文件名 | 本轮**未构造样本**（RQ-3 附录 F-1 同结论）；T2 的字符类 `[A-Za-z0-9_.\\/~:-]` 不含 CJK ⇒ `写入 报告.md` 的锚定匹配直接失败 = **0 候选** | **不可**（当前提取器） | 定稿**不**在本 key 扩展字符集（改字符集需重跑 26 本语料，且 `报告` 这类裸中文名仍不可判）；登记为独立缺口（§1.5 R-4） | 中文名写入漏放（fail-open）。若要修，方向是「按空白/引号/CJK 标点切词 → 剥标点 → 形状判定」，且必须带反例（`报告`/`结论` 等中文裸词不得进拒判） |

### 5.1 收敛结论

判定边界 = **`path.resolve`（W1/W3/W4）→ realpath + 最深存在祖先（W5/W8）→ win32 两侧小写（W2）→ 段边界前缀（W2/W4）→ 形态层剥尾点（W6）与 ADS/盘符相对标签（W3/W7）**。四步与 `worker/read-scope.ts:84-114` 的既有实现逐字一致；W3/W6/W7 只贡献**规则名**，不改变拒/放的方向。**全部 9 项都落在「拒绝」侧**（要么拒绝，要么不改变判定）⇒ 只可能假阳性、不产生新的漏放。

### 5.2 关于「派发期要不要 fs」

**要**（只读 `realpathSync` + `existsSync`）：
- 不给 fs 的纯词法变体在当前语料代价为 0（0 reparse point），但会**让派发期与运行期的允许面语义分叉**（AC-004 要求同语义），且 S10（`existsSync`，`Makefile`/`LICENSE` 类）本来就需要 fs；
- fs 调用都是只读，`judgeWriteIntent` 的零副作用验收（`mwds-t02`「refusal is zero-side-effect」）不受影响；
- 失败模式全部 fail-closed（§5 W5/W8）。

---

## §6 回归改造点：`mwds-t02-write-intent.test.ts`（交付物 6）

### 6.1 期望数值（PM 锚定 + 本轮复算一致）

| 指标 | 现状 | 定稿（V1） | 断言位置 |
|---|---|---|---|
| `corpus`（扫描到的 task.md 总数） | 305（增长量） | 随语料增长 | `:256` 的 `console.log` |
| `read_only_books` | 26 | 26（本轮复算 26） | `:258`；断言 `:259` `>= 24`（保持） |
| `hit_files` | 2 | 10 | `console.log` |
| **`hits`** | **2** | **13** | `console.log`（无断言） |
| `violations` | 1 | 1 | `console.log` + `:237` 过滤 |
| **`false_positives`** | **0** | **0** | **`:262` `expect(falsePositives).toEqual([])`（必须保持）** |
| **唯一真阳** | `mwg-qg-review-20261010` | 同一本 | **`:263` `expect(truePositive).toHaveLength(1)`（必须保持）** |

### 6.2 必须保持的断言（不动）

1. `:259` `expect(books.length).toBeGreaterThanOrEqual(24)`（RQ-3/P-08 口径：不用计数上限）。
2. `:262` `expect(falsePositives).toEqual([])` —— 定稿下 V1 实测 FP=0（§0.3）。
3. `:263` `expect(truePositive).toHaveLength(1)` —— **前提是允许面仍只有 taskDir**；把 `<key>/evidence` 并入允许面会让这条立刻变红（P-05）。
4. `:435-444`、`:446-448` 的白名单正例（`report.md`/`report-<slug>.md`/`progress.md`/`output.md`/`trace.log`/taskDir 内绝对路径/`.agenticdoc/k/evidence/x.md ⇒ false`）。
5. 全部拒绝/零副作用/契约/escape hatch 用例（`:394-433`、`:450-521`）。

### 6.3 **唯一必改的断言**：`test/suite/mwds-t02-write-intent.test.ts:445`

现状（把 A4 目录盲判写成了正例）：

```ts
		expect(
			isWhitelistedWriteTarget(".agenticdoc/k/workers/t02/report.md", { taskDir: TASK_DIR, projectRoot: PROJECT }),
		).toBe(true);
```

该 token **有目录成分**（`.agenticdoc/k/...`），在 `PROJECT = <tmp>/mwds-t02-project`、`TASK_DIR = PROJECT/k/workers/t02` 的合成布局下解析为 `PROJECT/.agenticdoc/k/workers/t02/report.md`，**不在 taskDir 内**；现状之所以为 `true`，正是 `:1426` 的 basename 白名单无条件 `return true`（= A4 本身）。定稿要求：

```ts
		// A4 fix (AC-003): a whitelisted basename does NOT whitelist a foreign directory.
		// The own-taskDir case is covered by the absolute-path assertion above (notes.md).
		expect(
			isWhitelistedWriteTarget(".agenticdoc/k/workers/t02/report.md", { taskDir: TASK_DIR, projectRoot: PROJECT }),
		).toBe(false);
```

**这是「只改断言、不加宽判据」**：改的是测试对旧语义的编码，不是把判据放宽（放宽方向恰好相反——旧断言为了绿而要求目录盲判）。

### 6.4 文字级 diff 建议（除上条外）

```diff
--- a/packages/coding-agent/test/suite/mwds-t02-write-intent.test.ts
+++ b/packages/coding-agent/test/suite/mwds-t02-write-intent.test.ts
@@ (头注 :11-14)
-  * corpus replay below is the hard acceptance: on every `.agenticdoc/<key>/workers/<taskKey>/task.md` in the
-  * repo, the writeless-without-shell set must yield at most two hits and zero false
-  * positives — the one true positive is the R22 incident card the rule exists
-  * for.
+  * corpus replay below is the hard acceptance: on every `.agenticdoc/<key>/workers/<taskKey>/task.md` in the
+  * repo, the writeless-without-shell set must yield zero false positives — the hit
+  * COUNT is a growth quantity (RQ-3: 2 → 13 after the shape axis, AC-004) and is
+  * logged, not asserted; the assertion is that the violation set is the one known
+  * R22 incident card (the rule exists for it).
@@ (:445)
-		).toBe(true);
+		).toBe(false);
@@ (:244-245 头注)
- * The judgement is the rule set from the card: write verb + a path that starts
- * right after it, five allow-guards (...), then the whitelist (worker_file basenames,
- * framework-owned names, own task dir).
+ * The judgement is the rule set from the card: write verb + the token right after
+ * it (gap ≤ 32, anchored character class — no extension enumeration), five
+ * allow-guards (...), then the whitelist in ORDER: deny prefixes → own task dir
+ * (realpath + segment boundary) → no-dir-component basename channel (worker_file /
+ * framework names) → path-shape refusal.
```

**`[VERIFY]` 行**（`:256-258`）不改代码，只改期望阅读值：`hits=13 false_positives=0 violations=1 unique_true_positive=true`。

### 6.5 **不要**为了让它绿而做的事（P-05 / P-08）

| 诱惑 | 后果 | 裁定 |
|---|---|---|
| 把 `<key>/evidence` 并入允许面 | 唯一真阳消失 ⇒ `:263` 变红（`truePositive=0`） | **禁止**（AC-004 明文） |
| 加 `hits <= N` 上限断言 | 语料增长即红（P-08） | **禁止** |
| 把 13 里的散文词也判违规再放宽 | `falsePositives` 变 10 ⇒ `:262` 红 | **禁止**（= HYP-B，AC-004 明文） |
| 用「前扫」把 `write your report to <path>` 也抓进来 | V3 实测引入 1 条新 FP ⇒ `:262` 红 | **禁止**（§0.3） |

### 6.6 新增用例（补充覆盖，不属于「改断言」）

| VC（`design.md` §6） | 用例（建议名） | 输入 → 期望 |
|---|---|---|
| VC-011 | `AC-003: basename whitelist does not bypass the directory check` | `../other-key/workers/other-task/output.md`、`.agenticdoc/other-key/workers/other-task/output.md`、`..\\o\\pm-state.md` → 全部 false（`dir_blind_bypass == 0`） |
| VC-012 | `AC-004: containment uses one normalizer (read-scope parity)` | §3.4 的 4×2 矩阵（含 `t/../t2` 与段边界 `k` vs `kk`） |
| VC-013 | `AC-004: own taskDir / framework names still pass` | `notes.md`（taskDir 内绝对）、`report.md`、`report-<slug>.md` → true |
| VC-014 | `AC-004: corpus hits=13 / violations=1 / FP=0` | 已由 `:222-263` 承载（只改 `[VERIFY]` 阅读值） |
| VC-015 | `AC-004: the five QG-B leak samples are refused (leak_caught=5)` | `config.toml`/`Makefile`/`.env`/`x.html`/`x.rs` → 每条 `verdict("写入 <t>").ok === false`；对照组 `report.md`/`a.ts` |
| VC-016 | `AC-004: no-extension and non-enumerated extensions are discovered` | `.agenticdoc/_index.parallel`、`.git/config`、`packages/x.rs` → 非空 hits |
| VC-017 | `AC-004: deny prefix outranks the shape branch` | 传 `keyDir`/`trueRoot` 时 `<key>/pm-state.md`、`<key>/workers/_workers.parallel`、`<trueRoot>/_index.parallel` → `judgeWriteTarget(...).rule === "deny"` |
| VC-018 | `AC-004: bare tokens introduce no false positives (bare_token_fp=0)` | `your`/`design`/`mcp`/`side`/`surface`/`message_update`/`-pattern` → `violations` 不含它们 |
| VC-019 | `AC-004: Windows 9 boundary rulings` | §5 的 W1–W9 各 1 组（W9 标 `skip` + `[VERIFY]`） |

---

## §7 本文件归属的未覆盖分支清单（交付物 7）

来源：`evidence/quality-gate-code-adversarial-20261011.md` §⑤「未覆盖分支（文件:行号 + 形态）」共 14 条。**属于 `pm/ui-bridge.ts` 的 = 3 条**（另附 1 条同文件同函数族的 AC-003 分支，它不在那 14 条内但必须一起销账）。

| QG-B 条目 | 坐标（当前工作树） | 形态（QG-B 原文） | 建议用例名 | 归属 |
|---|---|---|---|---|
| ⑤-7 | `pm/ui-bridge.ts:250`（`if (trimmed.startsWith("_") \|\| trimmed.startsWith(".")) return null;`） | `_`/`.` 前缀 **live 外键**（A5）；相邻 `paths.ts:32-34` 的 key/taskKey 形态零校验（`../` 穿越） | `mwgf-drq3 key-identity: a live key named _tmp is refused (exempt_live_key=0)` + `..\/` 穿越具名用例 | **DRQ-3**（角色/ key），非本 DRQ |
| ⑤-8 | `pm/ui-bridge.ts:82`（`const owner = active?.key ?? readIndexMdActive(agenticdocRoot) ?? SCRATCH_WORKERS_KEY;`） | `readIndexMdActive` 隐式兜底**不经守卫**（A7） | `mwgf-drq3 key-identity: the _index.md active fallback never reaches a foreign live key` | **DRQ-3** |
| ⑤-14 | `pm/ui-bridge.ts:1345-1346`（`WRITE_INTENT_PATH_RE` 扩展名枚举）+ `:1402-1406`（`after`/`gap`/`window`/`pm.index !== 0`） | 扩展名集外路径、>32 字符间隔的漏放（A3）；「t02 语料回放测的是仓库里已存在的任务书，不含这些构造」 | `AC-004: the five QG-B leak samples are refused (leak_caught=5)`（VC-015）+ `AC-004: shape discovery is not extension-enumerated`（VC-016） | **本 DRQ（DRQ-2）** |
| （不在 14 条内） | `pm/ui-bridge.ts:1423-1431`（basename `:1426`/`:1427` 先于目录比较 `:1428-1430`） | 框架 basename 白名单的**目录盲判**（A4，AC-003） | `AC-003: basename whitelist does not bypass the directory check (dir_blind_bypass=0)`（VC-011） | **本 DRQ（DRQ-2）** |
| ⑤-13（相邻，非本文件） | `shared/index-store.ts:159-161`（`findByKey` 精确匹配） | 大小写变体 key（A6，Windows） | `mwgf-drq3 key-identity: MW-KEY vs on-disk mw-key (case_mismatch_bypass=0)` | **DRQ-3** |

**销账口径**：⑤-14 与 A4 由本 DRQ 的 §1/§2/§6.6 覆盖（VC-011/012/014/015/016/017/018）；⑤-7/⑤-8/⑤-13 归 DRQ-3，本报告只登记坐标与用例名，不重复设计。AC-008 的 `branches_total=14` 里 `ui-bridge.ts` 部分因此有 3 条（⑤-7、⑤-8、⑤-14），加 A4 共 4 个必须落测试的 `文件:行号` 锚点。

### 7.1 本轮顺带确认（供 AC-011 重锚）

- QG-B 引用的行号在**当前工作树**仍然有效：`:250`、`:82`、`:1345-1346`、`:1402-1406`、`:1423-1431` 逐条复核一致（§0.1、§1.4）。
- QG-B 报告尾部的自我更正（「11 项攻击 = 10 项成立 + 1 项部分成立」）与本 DRQ 无关，但它对 A3/A4 的判定与本 DRQ 的实测一致（A3 读码成立 + A4 读码成立，本轮用真实模块/原型复算确认）。

---

## §8 不做什么（被否决的实现路径 + 理由）

| # | 被否决路径 | 否决理由（量化） | 来源 |
|---|---|---|---|
| 1 | **无界前扫**：verb 后扫描到第一个形状 token（RQ-3 §2.2 的推荐） | 本轮 V2 实测：26 本语料 `violations=12`（**+11 假阳性**）⇒ `false_positives == []` 硬断言必红。FP 集中在 `覆盖` 这个中文多义词（`覆盖完整性`/`覆盖 spec.md`）与 `url/端点` | §0.3 V2 |
| 2 | **ASCII-only 有界前扫**（跳过纯 ASCII 单词、遇 CJK/gap>24 停） | 本轮 V3 实测：`violations=3`（+2 FP）；即使补上英文 PM 归因 guard 仍有 `violations=2`（+1 FP：`mw-rag-integration-design-critique/task.md:32` 的 `url/`） | §0.3 V3 |
| 3 | **裸 token 一律 fail-closed**（`Makefile`/`your` 无差别拒） | RQ-3 实测 9/26 本 = **35% 假阳性**（`your`/`design`/`mcp`/`side`/`surface`/`message_update`/`-pattern`）；AC-004/P-02 明文禁止 | RQ-3 §5 HYP-B |
| 4 | **把 `<key>/evidence` 并入允许面** | 唯一真阳（`mwg-qg-review-20261010` → `<key>/evidence/quality-gate-report-*.md`）消失 ⇒ `violations 1→0`、`:263` 必红；AC-004/P-05 明文禁止 | RQ-3 §2.1/§6 |
| 5 | **把反引号加入 `WRITE_INTENT_QUOTE_PAIRS`**（当作 inline-code guard） | 语料唯一真阳本身就在反引号里（`mwg-qg-review-20261010/task.md:63`「写入 \`.agenticdoc/…md\`」）⇒ 该 guard 会把真阳一起跳过，`:263` 必红 | 本轮读源码 + §0.3 V1 命中明细 |
| 6 | **在 `ui-bridge.ts` 重写一份归一/段边界** | 仓库已有 2 份（`read-scope.ts:100`、`target-config.ts:155`），第 3 份必然漂移；且需重抄「最深存在祖先回接」循环（`read-scope.ts:100-114`）——新增未测试代码 | §3.3 |
| 7 | **保留扩展名枚举、只往里加 `toml|rs|html|env`** | 仍是枚举 ⇒ 下一次新语言/新配置类型重新 fail-open；AC-004 要求的是「形状」而非「清单」 | RQ-3 §2.2 / AC-004 |
| 8 | **用 `path.resolve` 后的裸字符串 `startsWith` 做允许面** | 本机实测 `realpath` **不折大小写**（`PACKAGE.JSON` 原样）⇒ 大小写敏感比较在 Windows 上 allow 方向误拒、deny 方向可被绕过；必须用 `isSameOrUnder`（win32 小写） | §5 W2 |
| 9 | **从 `taskDir` 自动反推 `keyDir`/`trueRoot`** | 在合成/临时布局下 `trueRoot` 退化成 `projectRoot`，D4「`.agenticdoc` 下非本 key」会把裸 `report.md` 判 deny ⇒ 打爆 `mwds-t02` 既有正例 | §4.4 |
| 10 | **用 `realpathSync.native` 另建一套**（`target-config.ts:155-175` 的路子） | 与运行期写面守卫（`read-scope.ts` 的 `realpathSync`）语义分叉 ⇒ 派发期/执行期允许面不一致；AC-004 要求同语义 | §3.3/§3.4 |
| 11 | **为 `\\?\` / UNC / ADS 特判白名单** | 这些形态全部落在拒绝侧已是安全方向；加白名单会开一条绕过 realpath 的通道 | §5 W4/W5/W7 |
| 12 | **本 key 内扩展 token 字符集到 CJK** | 需要重跑 26 本语料并给中文裸词反例（`报告`/`结论` 不可判）；RQ-3 附录 F-1 未验证；属独立缺口 | §5 W9 / §1.5 R-4 |

---

## 附录 A：本轮只读探针（可复跑）

全部以 `node --input-type=module -` 从 stdin 执行（无仓库临时文件残留）；guard 词表从 `pm/ui-bridge.ts` 源码按 UTF-8 文本读取，避免 PowerShell→node 的编码损坏。

1. **CURRENT / V1 复算**：逐字复刻 `collectWriteIntentHits`（verb 表 `:1266-1281`、gap `:1404`、扩展名 RE `:1345-1346`、5 guard），并自检 26 本书上与真实模块 `collectWriteIntentHits` 的命中序列一致（本报告 §0.3 的 CURRENT=2 与 RQ-3 一致）。
2. **V1（定稿轴）**：锚定 `^[A-Za-z0-9_.\\/~:-]+` + `classifyWriteTargetShape` + `normalizeForCompare`/`isSameOrUnder` + deny 表 ⇒ `books=26 hits=13 violations=1`；QG-B 5 样例 `5/5`。
3. **V2/V3（被否决变体）**：见 §0.3 表。
4. **Windows 探针**：`realpathSync`/`statSync`/`existsSync` 对 `package.json{., ::$DATA}`、`PACKAGE.JSON`、`packages/../package.json`、`.//package.json`、`\\?\…`、`//?/…`、`C:package.json`、`//server/share/x.md`、`README`/`Makefile`/`LICENSE`/`docs`/`Makefile` 的返回值，全部写入 §5。

**关键锚定值**（供 PM 复跑比对）：`books=26`、`hits_current=2`、`hits_V1=13`、`violations_V1=1`、`samples_caught=5/5`、`V3 violations=3`、`V3+EN-PM-guard violations=2`、`V2 violations=12`。

## 附录 B：未验证项（诚实清单）

1. **V1/V2/V3 是本报告的只读原型**，不是最终实现；`hits=13/violations=1/FP=0` 是原型复算值。落地后必须由 PM 复跑 `mwds-t02` 实测（RQ-3 附录 F-4 同口径）。
2. **非 ASCII（中文）文件名**（§5 W9）：本轮未构造样本，未验证。
3. **尾点/尾空格的写入侧行为**（CreateFile 是否剥除）：只读环境下无法验证；只测了 read 侧（`realpath`/`stat` 均 `ENOENT`）。
4. **UNC / `\\?\` 目标是否真实可达**（无远端共享可测）：只测了 `resolve`/`realpath` 的失败模式。
5. **`allow_foreign_write` 与（若将来有的）`write_scope:` 放宽后 deny 前缀是否仍绝对优先**：本报告只给设计建议（对齐 AC-005b 的 deny-first），未实现、未测。
6. **junction/symlink 分支的测试可写性**（Windows 无权限建 symlink 时）：建议 `skip` + `[VERIFY]`，本轮未试。
7. **`isSameOrUnder` 对 UNC 段的比较语义**（`path.sep` 前缀对 `\\server\share` 是否给出期望结果）：本报告未构造样本，未验证。

## 勘误

- §2.3 第一行写作 `classifyWriteTargetTargetShape`，正确符号名为 **`classifyWriteTargetShape`**（§1.2）。

## 勘误 2：引用行号重锚（PM 写 `design.md` §4 时以本表为准）

前文若干引用的**行号**与当前工作树不符（结论不受影响），正确值如下：

| 前文位置 | 前文写的 | 正确坐标 |
|---|---|---|
| §0.1 / §3.2 | `pm/ui-bridge.ts:31-32`（`../worker/*` import 先例） | **`:44`**（`WORKER_FILE_NAME_RE`）、**`:45`**（`isShellRole, isWritelessRole`）；`../shared/paths.ts` import = **`:39`** |
| §0.1 / §3.5 | 调用点作用域 `:1676`/`:1690` | `dispatch_worker`：`ownerKey = resolveOwnerKeyWithSync(...)` = **`:1669`**、`taskDir = workerTaskDir(...)` = **`:1720`**；`judgeWriteIntent` 调用 = `:1744-1749`（**这一处原本正确**） |
| §3.5 | `/worker` 的 `taskDir` = `:2202` | **`:2198`**（`ownerKey` = `:2180`；`judgeWriteIntent` 调用 = `:2200-2205`，**原本正确**） |
| §3.5 / §4.4 | `paths.ts:38-44 controlRootFromTaskPath` | **`shared/paths.ts:47`** |
| §2.4 | 测试 `:1180`（guard 枚举断言） | **`test/suite/mwds-t02-write-intent.test.ts:329`**（`expect(WRITE_INTENT_GUARDS).toHaveLength(5)`）；cases 数组 = **`:313-323`** |
| §6.2 第 4 条 | `:435-444`、`:446-448` | 白名单 describe = **`:433-452`**（断言 `:435-448`） |
| §6.2 第 5 条 | `:394-433`、`:450-521` | 拒绝零副作用 = **`:400-431`**、research = **`:454-470`**、escape hatch = **`:471-505`**、refusal text = **`:506-521`** |
| §1.3 注释 | `renderDefaultWriteScope`「`:1483-1485`」 | 定义 = **`:1476`**；调用 = **`:1794`**、**`:2251`** |

**已复核无误的引用**（无需改）：`:82`、`:250`、`:1266-1281`、`:1287-1293`、`:1299`、`:1303`、`:1305-1343`、`:1344`、`:1345-1346`、`:1355`（`WriteIntentHit`）、`:1363`（`findWriteIntentVerb`）、`:1375`（`pathInsideQuotation`）、`:1392-1421`、`:1404`、`:1421`（`return hits` 前的 `}`）、`:1423-1431`、`:1426`、`:1427`、`:1428-1430`、`:1433`（`WriteIntentVerdict`）、`:1444-1461`、`:1463-1473`（`writeIntentRefusal`）、`:1744-1749`、`:2200-2205`；`worker/worker-mode.ts:632-646`、`:923-937`、`:939-957`、`:959-998`、`:1467-1474`、`:126`/`:133`；`worker/read-scope.ts:14-16`、`:20-24`、`:84`、`:89-93`、`:100-114`；`shared/target-config.ts:155-175`；`worker/worker-file-tool.ts:41`；`shared/paths.ts:32-34`、`:39`。

## 勘误 3（两处行号，补充上表）

- `collectWriteIntentHits` 的收尾：`return hits;` = **`:1418`**、函数闭括号 = **`:1419`**（前文 §1.3 与勘误 2 写作 `:1421`，为误）。
- `writeIntentRefusal` = **`:1463-1474`**（前文写作 `:1463-1473`，区间下界差 1 行，不影响语义）。
