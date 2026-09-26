# Design RQ-D6 证据：两侧配置一致性的可判定判据与跨语言测试落点

- key：`mw-autopilot-verify-cli`（design 期）
- 日期：2026-09-26
- 性质：只读调研；唯一写面 = 本文件。未修改仓库任何源码/配置（探针脚本全部落在 `%TEMP%\mw-rqd6\`）
- 对齐：spec AC-006（差分真值表 + 跨侧字节一致）、U-4（Python 改 `ensure_ascii=False`；整值 float 方向以 RQ 实测为准）、P-015/P-016/P-017

## 0. 结论（TL;DR）

| # | 问题 | 结论 |
|---|------|------|
| 1 | `4.0` 在 TS 侧可判吗 | `JSON.parse` 单独**不可判**（`4.0` 归一为 `4`）。但 Node ≥ 22.0.0 的 `JSON.parse` reviver 第三参 `context.source` **可精确判定**（本机 node 22.0.0 / 22.19.0 / 24.19.0 实测均可用）。**推荐 Direction B：TS 侧拒绝"原始字面量非纯整数"的 int 字段值**，零 Python 改动，实测 12 种字面量与 Python 结论逐条一致。Direction A（Python 接受整值 float + 归一化）也成立，但改的是 schema owner 的语义，不推荐。 |
| 2 | D2 partial 读取是否纳入本 key | **纳入**。实测：省略 12 个键中任意一个，Python `load_config` 返回 11 键且 `cfg[K]` 直接 KeyError（`conductor.py:266/941/2037/3975`、`mw.py:161` 都是硬下标）；TS `readConfig` 12 键全在。修法 1 行：`load_config` 返回 `{**default_config(), **data}`（校验仍作用于原始文件）。对本 key 新增字段尤其关键：不加合并，**任何**新增键都会让旧 config 文件重启后的 conductor 直接 KeyError。现有测试全部以 `default_config()` 构造全量文件，实测不受影响。 |
| 3 | 能否逐字节相同 | **在配置值域内可以**。`ensure_ascii=False` + 两侧 canonical 键序 + int 值域内，实测 Python `save_config` 与 TS `saveConfig` 的产物 sha256 完全相同（含中文/emoji/反斜杠/`</script>`/`/`/tab）。残差只在 schema 值域外：lone surrogate（Python 写盘 UnicodeEncodeError）、>2^53 整数（值漂移）、float 字面量、JS 整数形 key 重排、`1e400`→`Infinity` vs `null`。 |
| 4 | 跨语言测试落点 | **主判据放 TS 侧 vitest（CI 覆盖）**，用 `spawnSync` 调 `python3` 做**差分**断言，语料 = 共享 JSON 文件；Python 侧放镜像半表供离线 dev。三条路都有本仓先例，证据见 §4。 |
| 5 | 新键同步机器判据 | **可做**：TS vitest 起一个 python 子进程 dump `DEFAULT_CONFIG/_BOOL_FIELDS/_LIST_FIELDS/_INT_RANGES`，与 TS 镜像表逐字比较（键集/默认值/JSON 类型/顺序/范围）。须先把 3 个私有常量 `export`（`status-model.ts:112/115/118`）。 |
| 6 | 判据集合 | 6 条，见 §6；全部 fail-closed（对端解释器缺失 ⇒ 硬失败，不 `skipIf`），并冻结语料 sha256 + 用例数防空洞测试（P-016）。 |

---

## 1. `4.0` 在 TS 侧是否可判

### 1.1 读路径实测

`status-model.ts:178 readConfig` → `:189 data = JSON.parse(raw)`。`status-model.ts:160` 的 int 规则是 `typeof value !== "number" || !Number.isInteger(value)`。

实测（`node probe1.mjs`，v24.19.0；`node@22.0.0`/`node@22.19.0` 经 npx 复测一致）：

```
4.0    value=4    isInteger=true   stringify=4
4      value=4    isInteger=true   stringify=4
4.00   value=4    isInteger=true   stringify=4
1e2    value=100  isInteger=true   stringify=100
1E2    value=100  isInteger=true   stringify=100
2e1    value=20   isInteger=true   stringify=20
-0.0   value=0    isInteger=true   stringify=0
0.0    value=0    isInteger=true   stringify=0
1800.0 value=1800 isInteger=true   stringify=1800
4.5    value=4.5  isInteger=false  stringify=4.5
```

用真实模块验证（node 直接加载 `status-model.ts`，见 §4.1）：

```
validate(4.0) errors: []
validate(4.5) errors: ["poll_interval_sec: expected integer, got 4.5"]
```

⇒ 只用 `JSON.parse` + `Number.isInteger`，**TS 无法区分整值 float 与 int**；`4.0` 被静默接受，而 Python `config.py:111` 因 `not isinstance(4.0, int)` 拒绝。RQ-2 的 D1 复现确认。

### 1.2 关键新事实：`JSON.parse` reviver 的源文本访问可用，TS 侧其实可判

Node 的 `JSON.parse` 已实现 JSON parse source text access：reviver 第三参 `context.source` 给出**原始字面量**。实测：

```
node v24.19.0  reviver: [["a","4.0"],["b","4"],["c","1e2"],["","undefined"]]
node v22.0.0   reviver: [["a","4.0"],["b","4"],["c","1e2"],[":undefined"]]
node v22.19.0  reviver: [["a","4.0"],["b","4"],["c","1e2"],[":undefined"]]
（root 与容器值的 context.source 为 undefined；primitive 才有）
```

本仓 `engines.node` = `>=22.19.0`，CI `ci.yml:23` pin `node-version: 22` ⇒ 该 API **有保证**。

唯一成本：TS 5.9 的 lib **没有**第三参重载（`node_modules/typescript/lib/lib.es5.d.ts:1163` 只有 `reviver?: (key, value) => any`），需要用**局部窄类型 + 一次 cast**（不引入 `any`）：

```ts
type JsonSourceContext = { source?: string };
JSON.parse(raw, ((key: string, value: unknown, ctx?: JsonSourceContext) => {
    if (INT_FIELDS.has(key) && typeof value === "number"
        && typeof ctx?.source === "string" && !/^-?(?:0|[1-9]\d*)$/.test(ctx.source)) {
        // 记一条 "expected integer literal, got <literal>"
    }
    return value;
}) as (this: unknown, key: string, value: unknown) => unknown);
```

完全规避第三参也可以：先按 JSON 语法剥掉字符串再正则扫 `"field"\s*:\s*<number-literal>`（约 25 行）；但 reviver 更短且精确，推荐 reviver。

### 1.3 两条路的实现成本、误拒面、推荐

**Direction B（TS 侧拒绝非纯整数字面量）— 推荐**

- 改动面：仅 `status-model.ts readConfig`（+1 局部类型，约 12 行）；Python 零改动。
- 语义等价性（最强论据）：Python 的 `json` 解析器**按字面量语法**决定 int/float（无 `.`/`e`/`E` ⇒ int），而 `config.py:111` 恰好拒绝一切 float。因此"原始字面量非纯整数" ⇔ "Python 解析为 float" ⇔ "Python 拒绝"，**逐字面量精确等价**，不需要任何新规则。
- 误拒面实测（把候选实现挂到真实 `validateConfigData` 上跑 `round_budget`）：

| 字面量 | TS 现状 | TS + 候选检查 | Python | 一致 |
|---|---|---|---|---|
| `4` | accept | accept | accept | 是 |
| `4.0` | accept | **reject** | reject | 是 |
| `1e2` | accept | **reject** | reject | 是 |
| `1800.0` | accept | **reject** | reject | 是 |
| `4.00` | accept | **reject** | reject | 是 |
| `2E1` | accept | **reject** | reject | 是 |
| `4.5` | reject | reject | reject | 是 |
| `1e400` | reject | reject | reject | 是 |
| `-0.0` / `0.0` | reject(范围) | reject | reject | 是 |
| `9007199254740993` | accept | accept | accept | 是（D6，值漂移见 §3.3） |
| `1000000000000000000000` | accept | accept | accept | 是（同上） |

  12/12 一致。误拒面 = **0 个 Python 接受的合法 payload**：`1800.0`/`1e2`/`2E1` 在 Python 侧本来就被拒；写侧（TS console 与将要加的 Python CLI）都只写 `JSON.stringify`/`json.dumps` 的纯整数字面量，不会产生这些形态。
- 运行期风险：依赖 reviver 源文本访问（Stage 3 提案、V8 已实现，见 §1.2）。生产代码**不要**做"读不到 source 就静默放行"的 fail-open 回退：要么直接依赖（engines 已保证），要么退化为 §1.2 的 strip-strings+regex 扫描。

**Direction A（Python 接受整值 float 并对齐 TS）**

- 改动面：`config.py validate_config` 放宽为"int 或整值有限 float"（约 4 行）+ `load_config`/`save_config` **都**要归一化回 int（否则 Python 写 `4.0`、TS 写 `4`，§3 字节判据立刻红）。TS 零改动。
- 优点：不依赖新 JS 能力；`4.0` 的手改文件不再让 autopilot 整条链死掉（操作员体验更好）。
- 缺点：改的是 schema owner 的语义（`config.py` docstring 明确"a wrong config must fail loudly"），把"类型越界"降级为"自动修复"；且新增一条隐式归一化规则，未来每个新 int 字段都要走同一条路。
- 结论：**不推荐**。AC-006 要的是"结论一致"，Direction B 用更小的 blast radius（单侧、单函数、无写盘语义变化）拿到**精确**一致；Direction A 需要用 2 个 Python 函数的行为变化换取同一目标。

若用户坚持"不改 TS 校验"，则 AC-006 退化为"差异登记在案 + 只对合法 payload 断言一致"（U-4 的备选），此时 `4.0`/`1e2` 必须进"已知差异"清单并由 corpus 显式标注 `expect: "divergent"`——不推荐，等于把 D1 永久制度化。

---

## 2. D2：两侧读取语义要不要一致

### 2.1 实测矩阵（省略 12 键中的任意一个）

`config.py:122 load_config` 直接 `return data`（不合并默认）；`status-model.ts:213 merged` 逐字段回落 `DEFAULT_CONFIG`。

省略键 K 后写入文件，再读：

```
omit <K>   Python: loadkeys=11  loaded[K]=KeyError     TS: loadkeys=12  config[K]=<default>
（12 个键全部如此，12/12 对称）
```

直接复现调用点：

```
partial file = {"enabled": true}
partial load_config keys: 1 -> {"enabled": true}
loaded['poll_interval_sec'] -> KeyError 'poll_interval_sec'
cached_load(...)['poll_interval_sec'] -> KeyError 'poll_interval_sec'
```

硬下标消费点（partial 文件会炸的位置）：`mw.py:161`（`["enabled"]`）、`autopilot/conductor.py:266`（`["max_parallel_keys"]`）、`:941/:1063/:1570/:1712`（`["round_budget"]`）、`:2037`（`["enabled"]`/`["paused"]`）、`:3975`（`["poll_interval_sec"]`）。`autopilot/dispatch.py:229` 用 `.get()`，不受影响；`test_autopilot_xkey_registration.py:756` 用 `.get("xkey_repair", False)`，是既有绕坑写法。

现实触发场景（不只是手改文件）：**本 key 新增 `xkey_verify_cwd` 之类字段后，所有在此之前写下的、只含 12 键的 config.json 都会缺新键** ⇒ 未合并默认的实现会让重启后的 conductor/`mw serve` 直接 KeyError，直到 console 重新写一次文件。

### 2.2 推荐

**纳入本 key，改 `load_config`（1 行 + docstring）**：

```python
validate_config(data)                      # 仍校验原始文件（unknown key 照样 fail-closed）
return {**default_config(), **data}        # 缺失键回落默认
```

- 语义统一：文件缺失 ⇒ 全默认（现状）；文件存在但 partial ⇒ 默认叠加已写字段（新增）；两者返回**同一形状**（12 键、DEFAULT_CONFIG 键序）。TS `readConfig` 已经是这个语义，D2 归零。
- 校验语义**不变**：`validate_config` 仍作用于原始 `data`，`{"enabled": true, "poll_interval_sec": 99}` 依旧 `ConfigError`（`test_autopilot_config.py:79`）；unknown key 依旧报错。
- 键序：`{**default_config(), **data}` 的键序 = 默认字典全量键序（12 键全在 default 中），因此 Python 写盘键序 == TS `ordered` 键序（`status-model.ts:237`）== AC-006 字节判据所需。
- 受影响测试（逐项核对）：`test_autopilot_config.py` 的 8 个 config 用例全部用 `default_config()` 构造全量 dict（`test_roundtrip_and_atomic_write:91-103` 断言的 `modified` 也是全量）⇒ 断言不变；`test_invalid_values_rejected:62` / `test_invalid_never_falls_back_to_defaults:79` / `test_malformed_json_rejected:71` 走校验路径，不受合并影响；`test_defaults_when_file_missing:29` 不受影响。`test_autopilot_*.py` 全部以 `config.default_config()` 为基底 `save_config`（`test_autopilot_conductor.py:39/88/107/330`、`test_autopilot_conductor_exec.py:40/288/...`、`test_autopilot_stall.py:171+`、`test_autopilot_xkey_registration.py:745+`、`test_autopilot_e2e.py:146/1243`），合并不改变任何既有断言。
- 副作用（正面）：`save_config` 拿到 `load_config` 的返回值再写，就等于"全字段物化"，与 AC-001 的 `{**default_config(), **existing}` 自然一致。

**备选（不推荐）**"只让 CLI 写全量"：能让新 CLI 自己不产生 partial 文件，但对已存在的 partial / 旧版本文件无能为力，D2 的 KeyError 面保留。

---

## 3. 字节一致的精确目标

### 3.1 逐字节实测（真实函数，非模拟）

- Python：`config.save_config`（临时改口径为 `json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"`，即 U-4 定稿后的形状）
- TS：真实 `status-model.ts::saveConfig`（node 直接加载 `.ts`，见 §4.1）

配置：`enabled=true` + `xkey_verify_cmd=["python","-m","pytest","用例/中文","emoji-😀","back\slash","</script>","a/b","tab\tchar"]`

```
py ensure_ascii=False sha256: d63530028ba92557de434f91d94be537aa4a9a179af5bd64dfeafd2c70212e0b len: 449
ts saveConfig        sha256: d63530028ba92557de434f91d94be537aa4a9a179af5bd64dfeafd2c70212e0b len: 449
py len 449 ts len 449 equal True
```

同一配置在**现状** `ensure_ascii=True` 下：`6e469320f09172cc0478bd0562976162f3e0db8fe16617575a86775c89e62d04`，len 469 ⇒ 与 TS 不等（RQ-2 D4 复现）。U-4 的 `config.py:144` 改 `ensure_ascii=False` 是必要且充分的一处改动。

### 3.2 语料级逐字节比对（15 个 payload）

对每个 payload：Python `json.loads` → `dumps(ensure_ascii=False, indent=2)+"\n"`；TS `JSON.parse` → `JSON.stringify(x,null,2)+"\n"`（UTF-8 字节 sha256）。

| id | 内容要点 | py==ts | py len / ts len | 备注 |
|---|---|---|---|---|
| `empty` | `{}` | 是 | 3 / 3 | 空对象两侧都是 `{}`（非 `{\n}`） |
| `defaults` | 全 12 键 int/bool | 是 | 307 / 307 | sha `ae173243…` |
| `zh` | 中文 + emoji + `back\slash` + `</script>` + `a/b` + tab | 是 | 190 / 190 | `ensure_ascii=True` ⇒ 332a6a85…（不等，D4） |
| `u2028_u2029` | U+2028/U+2029/U+00A0/U+FEFF/U+007F | 是 | 24 / 24 | Node **不**转义 U+2028/2029，Python 也不 ⇒ 相等 |
| `control_chars` | `\u0000\u0001\u001f\b\f\n\r\t\"` | 是 | 44 / 44 | 控制字符转义表一致 |
| `empty_containers` | `[] {} [[]] {"e":{}}` | 是 | 72 / 72 | 嵌套空容器格式一致 |
| `escaped_unicode` | 文件里写 `\u4e2d\u6587` | 是 | 20 / 20 | 两侧都重写为**原样 UTF-8** |
| `escaped_slash` | 文件里写 `a\/b` | 是 | 17 / 17 | 两侧都重写为 `a/b`（`/` 不转义） |
| `deep_nest` | 3 层嵌套 + 数组 | 是 | 104 / 104 | |
| `lone_surrogate` | `"\ud800"` | 否 | — / — | Python `dumps` 得 str 后 `.encode("utf-8")` → `UnicodeEncodeError: surrogates not allowed`（`save_config` 实写会抛）；TS 写 `"\ud800"` 正常 |
| `floats` | `4 / 4.0 / 1e2 / 1800.0 / 0.1` | 否 | 66 / 60 | `4.0`→`4.0` vs `4`；`1e2`/`1800.0`→`100.0`/`1800.0` vs `100`/`1800` |
| `bigint` | `9007199254740993` | 否 | 28 / 28 | 值漂移：py `…740993` vs ts `…740992` |
| `numeric_keys` | `{"2","1","x","10"}` | 否 | 52 / 52 | JS 把整数形 key 提前并排序（`1,2,10,x`），Python 保插入序 |
| `huge_float` | `1e400` | 否 | 20 / 16 | py `Infinity`（非合法 JSON）vs ts `null` |

### 3.3 结论：能否达成逐字节相同

**能，但只在配置 schema 的值域内**：

1. 键序：`DEFAULT_CONFIG` 两侧同序（`config.py:44` vs `status-model.ts:90`），且两侧写盘都经 canonical 顺序（Python 侧由 `{**default_config(), **existing}` 保证，`save_config` 自身不重排；TS 侧 `saveConfig` 构造 `ordered`，`status-model.ts:237`）。
2. 非 ASCII：`ensure_ascii=False`（U-4）后逐字节相同（§3.1/3.2）；`/`、`</script>`、U+2028/U+2029、控制字符、嵌套空容器均**无**差异。
3. 值域必须排除 §3.2 的 5 个"否"情形。它们在 schema 下的实际可达性：
   - `floats`：int 字段的 float 字面量 ⇒ §1 的 Direction B 在**读取侧**就拒绝（`4.0`/`1e2`/`1800.0`），因此不会进入写盘路径。`4.5` 两侧本来就拒。
   - `huge_float`：`1e400` ⇒ Python 得 `inf`（非 int）拒、TS `Number.isInteger(Infinity)=false` 拒 ⇒ 不可达。
   - `bigint`（D6）：`9007199254740993` 两侧**都接受**，但 TS 存 `…992`、Python 存 `…993` ⇒ 校验结论一致而**值**不一致，跨侧字节必然不同。**建议**给所有 int 字段加 `<= 2**53-1` 上界（Python `_INT_RANGES` 的 `hi` 兜底，TS `INT_RANGES` 同理，各 1-2 行），把 D6 从"静默漂移"变成"两侧一致拒绝"；若不加，必须在 corpus 里登记为已知差异并在 AC-006 里排除（不推荐，属于新的静默漂移面）。
   - `lone_surrogate`：只有手写异常用途才会出现（`xkey_verify_cmd` 里塞独代理）；两侧都不会自己产生。建议在 corpus 里登记为已知差异（TS 写成功 / Python 写抛异常），或让 Python 侧在 UTF-8 编码失败时转 `ConfigError`（把崩溃变成 fail-closed 报错），二选一即可，不必强求字节相同。
   - `numeric_keys`：配置键是固定 12 个标识符，不可能出现整数形 key；`xkey_verify_cmd` 是字符串数组，无对象。不可达。

4. **可判定的替代（若未来出现不可消除的格式差异）**："两侧互相读写后语义等价 + 各自规范化幂等"，即 (i) A 侧写 → B 侧读 → B 侧再写，字节不变；(ii) 反向同理。它不依赖具体缩进/转义决策，且比"各自格式自洽"强。**建议**：作为 AC-006 的第二条判据同时保留（成本低，且能捕获未来的格式回归），但**主判据仍是 §3.1 的逐字节 sha256**——因为对配置值域它确实可达，放弃它等于放弃最强的跨侧锁。

---

## 4. 跨语言测试落点

### 4.1 环境事实（都是本机实测/仓库证据）

- 本机：`node v24.19.0`、`Python 3.14.3`（`python` 在 PATH）；`npx node@22.0.0` / `node@22.19.0` 可复现 CI 的 node 行为。
- `status-model.ts` 依赖只有 node 内建 + `shared/index-store.ts`（→ `shared/file-lock.ts`，同样只有内建）⇒ **node 可直接加载 `.ts` 源码**（22.19/24 的 type stripping 默认开启），实测：
  ```
  v24.19.0  src ts import ok: function keys: 12
  v22.19.0  src ts import ok: function keys: 12
  dist import ok: function keys: 12
  ```
  ⇒ Python 侧要调 TS 校验，既可用源码 `.ts`（node ≥22.19，本仓 engines 已保证），也可用 tracked 产物 `packages/coding-agent/dist/.../status-model.js`（等价，但可能落后源码；AC-009 已把 dist 同步纳入，二选一即可，推荐源码）。
- CI（`.github/workflows/ci.yml`）：`runs-on: ubuntu-latest`，`node-version: 22`（`:23`），步骤只有 `npm ci` / `npm run build` / `npm run check` / `npm test`（`:42`）；**全仓 workflow 无 `python`/`pytest`/`setup-python`**（对 `.github` 递归检索 0 命中）。
- `ubuntu-latest` 镜像自带 Python：`actions/runner-images` 的 `Ubuntu2404-Readme.md`（`ubuntu-latest` 当前指向 24.04）列出 `Python 3.12.3` 与 `Node.js 22.23.2`。⇒ CI 里 node 与 python3 都可用，但 python 不是 workflow 显式声明的依赖（建议补 `actions/setup-python` 把它钉住）。
- `packages/multi-workers` **不在 CI**：无 `package.json`（`Test-Path` = False），`npm test` = `npm run test:scripts && npm run test --workspaces --if-present`（`package.json:34`）⇒ 该 workspace 被 `--if-present` 跳过；其测试靠 `python -m pytest -q`（`README.md:352`，`pytest.ini` 默认 deselect e2e）。
- `packages/coding-agent` 的 vitest 在 CI 内（`"test": "vitest --run"`），`test/suite/*.test.ts` 会被执行（本机 `node node_modules/vitest/dist/cli.js --run test/suite/rag-parity.test.ts` 实测 9 passed）。

### 4.2 三条路的可行性证据

**(a) Python pytest → node（真值表放 Python 侧）**

- **有先例**：`test_autopilot_l0.py:296-310` 在 pytest 里 `subprocess.run(["node", <vitest cli>, "--run", "test/suite/autopilot-protocol.test.ts"], cwd=packages/coding-agent, encoding="utf-8", errors="replace", timeout=300)`，Windows 上可用；缺工具链时退化为静态源码断言（这正是要被 P-016 批判的软 skip）。
- node 可用性：`mw.py:3530` 已经 `shutil.which("node")` 并在 `:3538` 用 `subprocess.run([node, "-e", script])` 跑 esbuild 自检 ⇒ mw 本身就把 node 当运行期依赖。
- 缺 node 时 fail-closed：`shutil.which("node") is None` ⇒ `pytest.fail("...")`（不要 `pytest.skip`）。
- 缺点：**CI 不跑 pytest**，所以这条路放不出 CI 强制力（只能作为 dev 侧镜像）。

**(b) TS vitest → python（真值表放 TS 侧）**

- **有先例且已在本机通过**：`test/suite/rag-parity.test.ts:147-169` 用 `spawnSync(resolveRagPython(), ["-c", script, MULTI_WORKERS_DIR, root])` 跑真实 Python `mw_common.load_rag_config/rag_fingerprint`，逐字段与 TS 比对；本机 `rag-parity.test.ts` 9 passed，其中 `VC-305` 用例打印 `ts==py`（说明 python 子进程真的跑了，不是 skip）。
- python 解析：复用 `resolveRagPython()`（`rag/cli-bridge.ts`，`rag-transport.test.ts:314-317` 锁定 fallback = win32 `python` / 其他 `python3`），Windows 上实测可用。
- CI 可用性：见 §4.1（镜像自带 Python 3.12.3；建议 ci.yml 加 `actions/setup-python` 显式钉住）。
- 缺点：需要在 TS 测试里维护 sys.path/argv 传参（有 rag-parity 现成骨架可抄）；对端缺失时必须硬失败而不是 `skipIf`（现有 rag 系列是 `it.skipIf(!pythonAvailable)`，`rag-parity.test.ts:134/369`，这正是 P-016 要避免的空洞形态）。

**(c) 两侧各放半张表 + 共享语料 JSON**

- **有先例**：`test/fixtures/active-mode-table.json`（112 用例，含 `expect`）由 `test_active_mode.py:15-38`（Python，`assert len(CASES)==112`）与 `test/extensions/agent-team-loop-active-mode.test.ts:26-33`（TS，读同一文件）双跑，JSON 即 parity contract；同类还有 `test/fixtures/target-config-cases/*/case.json`（`test_common_target_config.py:31` 与 `test/extensions/agent-team-loop-target-config.test.ts:326` 共读）与 `test/fixtures/rag/*`（`rag-parity.test.ts:43-47` 跨目录共读 + `FIXTURE_SHA256` 钉死，`rag-parity.test.ts:39-41`）。
- 优点：无跨语言进程调用，Windows/离线全兼容；两侧各自在 CI/本地可跑；传递性上也能保证一致（两个 runner 都断言 == corpus ⇒ 两侧相等）。
- 缺点：期望值是**手写**的，只能靠"两侧都跑"来防漂移；而 CI 只跑 TS 侧 ⇒ Python 侧的漂移在 CI 里不可见。故它适合做**语料载体**，不适合做唯一判据。

### 4.3 推荐

**共享语料 + TS 侧差分测试为主，Python 侧镜像半表为辅**：

1. 语料文件（唯一 payload 真源，两侧共读）：`packages/multi-workers/test/fixtures/autopilot-config/cases.json`
   - 每个 case：`{id, categories:["D1"…"D6"], payload_text(原始 JSON 文本), expect: {verdict:"accept"|"reject", error_fields:[...]}, canonical_sha256}`。
   - 文件头记 `cases_count` + 自 sha256（照 `rag-parity.test.ts:39-41` 的 `FIXTURE_SHA256` 形状）。
2. **主判据（CI 覆盖）**：`packages/coding-agent/test/suite/autopilot-config-parity.test.ts`
   - 起一次 `python3` 子进程 dump 每个 payload 的 Python 结论（accept/reject + 违规字段名）与 `save_config` 字节 sha256；
   - 逐条断言 Python 结论 == TS 结论（差分，不依赖手写期望），且两侧 canonical 字节 sha256 相等；
   - 对端缺失 ⇒ `expect.fail(...)` 硬失败；语料 sha256/用例数/`categories` 覆盖集先断言，防空洞用例（P-016）。
3. **辅判据（dev 侧、无 CI 也要能跑）**：`packages/multi-workers/test_autopilot_config_parity.py`
   - 逐条断言 Python 结论 == corpus 的 `expect` 与 `canonical_sha256`（半表，不需要 node）；
   - 额外用 `node` 子进程跑 TS 校验做反向差分（照 `test_autopilot_l0.py:296-310` 形状，`shutil.which("node")` 缺失即 `pytest.fail`）。
   - 这样两侧都有"真差分"，且任何一侧缺工具链都是硬失败，不产生空洞用例。

不推荐把真值表只放 Python 侧（CI 不可见）；也不推荐只用半表（漂移在 CI 不可见）。

---

## 5. 新键的同步机器判据

现状：新增字段靠人工"逐字镜像"（前一 key 的 T-04b）——两份表 6 处（`config.py:11-28/44-57/60-71`、`status-model.ts:18/67-88/90-103/112-127/198-226/237-250`），漏一处即"含新键的 config 被该侧整体 fail-closed"，且新键会让旧文件在 Python 侧 KeyError（§2）。

**推荐实现（TS vitest + python 子进程，一次比较四张表）**：

- 前置：把 TS 侧三个私有常量 `export`（`status-model.ts:112 BOOL_FIELDS` / `:115 LIST_FIELDS` / `:118 INT_RANGES`，各加 1 个关键字；`DEFAULT_CONFIG` 已 export）。断言面因此是"表 ↔ 表"直接比较，而不是行为反推。
- Python dump 脚本（一次子进程返回 JSON）：
  ```python
  {"defaults": DEFAULT_CONFIG,
   "order": list(DEFAULT_CONFIG),
   "bools": list(_BOOL_FIELDS),
   "lists": list(_LIST_FIELDS),
   "int_ranges": {k: [lo, hi] for k, (lo, hi) in _INT_RANGES.items()}}
  ```
- 断言（逐字，不是"包含"）：
  1. 键**集合**相等；
  2. 键**顺序**相等（`DEFAULT_CONFIG` 顺序 == `ordered`/`merged` 字面量顺序；否则 §3 字节判据会红，这是顺序必须进判据的理由）；
  3. 每个键的默认值 `JSON.stringify` 相等（`false`/`4`/`[]`/`65536`…），顺带覆盖类型（bool 与 int 在 JSON 里可区分，`[]` 与 `false` 也可区分）；
  4. `bools`/`lists` 归属相同（类型分类）；
  5. `int_ranges` 的 `[lo, hi]` 逐字段相同（`hi=null` ↔ Python `None`）。
- 成本：TS 测试约 60-80 行（与 §4.3 的 python 子进程 helper 共用），Python 侧仅需（除导向性 `export` 外）零改动。
- 备选（无 node 依赖，但脆）：Python 侧用**文本解析 TS 源码**比对（先例：`test_autopilot_l0.py:215-230 _parse_ts_allowlists` 正则解析 `TOOL_ALLOWLISTS`、`test_mwpp_collection_parity.py` 冻结快照）。缺点：`DEFAULT_CONFIG`/`INT_RANGES` 是嵌套结构，正则易碎且会给出假绿；建议只在 Python dev 镜像里作为"TS 文件不再可解析即报错"的兜底。
- 不推荐：共享 schema JSON 由两侧 runtime 加载（会把"两侧各一份实现"变成"两份实现 + 第三个真源"，并给 Python 模块引入文件 IO 依赖，超出本 key 范围）。

---

## 6. 判据集合与 AC-006 的对应（含 fail-closed）

语料用 §4.3 的 `cases.json`；`categories` 须覆盖 D1–D6（`D1` 整值 float、`D2` partial、`D3` 规范化写盘、`D4` 非 ASCII、`D5` 错误文案、`D6` 大整数）。

| ID | 断言什么 | 在哪跑 | 跑不起来时 |
|---|---|---|---|
| **P1** 差分结论一致 | 逐 payload：Python `validate_config` 接受 ⇔ TS `validateConfigData` 无错；被拒时**违规字段名集合**相等 | TS vitest（`spawnSync(python3)`）+ Python pytest 镜像（`subprocess.run(["node",…])`） | 对端解释器缺失 ⇒ `expect.fail`/`pytest.fail`，**不 skip**；语料 `categories` 集合与 `cases_count` 先断言 |
| **P2** 跨侧字节一致 | 逐 payload：Python `save_config` 字节 sha256 == TS `saveConfig` 字节 sha256 == corpus `canonical_sha256`（含非 ASCII 组合） | 同上（TS 侧 spawn python 写盘后比字节；Python 侧 spawn node 写盘后比字节） | 同上；python `UnicodeEncodeError`（lone surrogate case）按 corpus 登记的 `expect_write_error` 断言，不许静默 |
| **P3** 语义等价兜底 | 互读幂等：A 写 → B 读 → B 写，字节不变；反向同理 | TS vitest + Python pytest | 同上 |
| **P4** 语料完整性 | `cases.json` 的 sha256 == 冻结值；`cases_count` 相等；`categories ⊇ {D1..D6}` | 两侧各跑（防任一侧裁剪 payload 造绿） | 语料读不到即失败 |
| **P5** 新键镜像 | §5 的四表比较（键集/顺序/默认值/分类/范围） | TS vitest（python 子进程） | `export` 缺失或 python 缺失 ⇒ 硬失败 |
| **P6** 读取语义 | 省略 12 键中任意一个 ⇒ Python `load_config` 与 TS `readConfig` 都返回 12 键且值等于默认（§2 矩阵 12/12） | Python pytest（`tmp_path` 造 partial 文件）；TS 侧同形断言 | 无外部依赖，天然 fail-closed |

与 AC-006 的映射：

- AC-006 前半"逐 payload 断言两侧结论一致" = **P1**（差分层，主）+ **P6**（D2 语义）。
- AC-006 后半"同一配置两侧写盘字节相同（含非 ASCII）" = **P2**（主）+ **P3**（兜底）；D4 由 `config.py:144` 加 `ensure_ascii=False` 满足（U-4）。
- D1/D6 的处置：D1 由 §1 的 Direction B 在读取侧消除（P1 覆盖 `4.0`/`1e2`/`2E1` 等字面量）；D6 由 §3.3 的 `2**53-1` 上界消除（P1/P2 覆盖 `9007199254740993`），若不加上界则必须在 corpus 里显式标 `divergent` 并写进 spec 的已知差异清单。
- D5 错误文案：**不要**断言整串相等（Python 用 `repr` 渲染值，如 `got 'yes'`；TS 用 `JSON.stringify`，如 `got "yes"`；bool 值 `True` vs `true`），实测"字段名 + 类别"完全一致，前缀也一致（Python `config.py:118` 的 `invalid _autopilot/config.json: ` vs TS `status-model.ts:209` 的同一前缀 + `; ` 连接）。**P1 只断言违规字段名集合与 accept/reject**；若要求文案也一致，那是本 key 之外的独立工作（会牵动 `config.py:96-116` 的值渲染）。

P-016 的具体防线（避免空洞用例）：

- P1 对每个 D 类断言"至少 N 条 payload 命中"，并断言实际执行条数 == 语料条数（不漏跑）；
- 两侧 runner 的 P1/P2 都在**对端缺失时硬失败**——CI 有 python3（§4.1），dev 机有 node（`mw.py:3530` 已依赖）；
- 建议 `ci.yml` 增加 `actions/setup-python`（`python-version: "3.12"`）使 P1/P2/P5 的依赖显式化，避免依赖 runner 镜像的隐式预装；
- 所有断言必须产出可见证据行（照 `[VERIFY] VC-027: …` 形状），便于人工 audit 而不是"绿=没跑"。
