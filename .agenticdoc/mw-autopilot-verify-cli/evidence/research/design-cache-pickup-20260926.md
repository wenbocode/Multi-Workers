# design RQ-D1 证据：`cached_load` 缓存判据的修复方案选型

- key：`mw-autopilot-verify-cli`（design 期 RQ-D1）
- 日期：2026-09-26 · 执行者：worker `design-rqd1-cache-pickup`
- 性质：只读调研；唯一写面 = 本文件
- 环境：Windows NTFS · PowerShell · Python 3.14.3（CPython MSC v.1944）· 真实项目样本 FM/E2/JCodingAss
- 关联 AC：AC-003（主）、AC-007（"缓存键含机器层"措辞）、AC-011（并发写）

## 0. 结论速览

| # | 问题 | 结论 | 决定性依据 |
|---|---|---|---|
| 1 | 缓存到底省了什么 | **什么都没省，净负收益**。本机 `cached_load` 命中路径 ~85–109 µs，比"直接读文件 + parse"（~60–70 µs）**更慢**——差异全在 `path.resolve()`（67 µs）。缺文件时 167 µs vs 15 µs（11×）。缓存真正省掉的只有一次 `json.loads`（~6 µs） | §1.3 实测 |
| 2 | 调用频率 | serve `mw.py:161` 每 1 s 一次；conductor 每 tick 2–3 次（`conductor.py:2036` + `:169` + `:3975`），默认 4 s/tick ⇒ 合计 ~1.75 次/s；配置 196–356 B ⇒ <0.2 ms/s CPU | §1.1/§1.4 |
| 3 | 同尺寸 stale 复现 | 400 次同长度 `xkey_verify_cmd` 裸字节改写 → **95 次 stale（23.8%）**，与"相邻写共享 mtime_ns"次数精确相等。本机 mtime 刻度 0.364–1.25 ms，54% 的相邻写同刻度 | §1.5 |
| 4 | TS 侧 | `status-model.ts:178 readConfig` 每次都 `fs.readFileSync`，**无缓存**；monitor 每 4 s 重导出（`monitor.ts:58/234/269/696`）。**TS 读侧不踩坑**；TS 是写者（`saveConfig:234`），其写会让 Python 侧 stale | §2 |
| 5 | 既有测试约束 | `test_autopilot_config.py:113-145` / `:147-154` 锁的是"写后读到新值"，**不锁"必须命中缓存"**；改判据不会红（`test_autopilot_conductor.py:300/638` 同理） | §3 |
| 6 | 推荐方案 | **(a) 取消 stat 短路**：`cached_load` 退化为 `load_config` + 防御性拷贝。理由：缓存净负收益；内容指纹（b）成本≈全读；Windows `ctime` 不随修改变化（c/d 混合的 ctime 子案死路）；写侧推 mtime（c）治不了外部写者且违反 AC-003 的"不用 os.utime" | §4/§5 |
| 7 | AC-003 判据 | 需调整：必须按**写者类别**枚举（外部手改 / TS console / Python CLI），且测试写入必须是**裸字节写**（不经 `save_config`），否则 (c) 可借写侧 `os.utime` 作弊通过 | §6 |

## 1. 调用频率与成本

### 1.1 全部调用点（file:line）

| 位置 | 调用者 | 频率 | 用途 |
|---|---|---|---|
| `mw.py:161` | `_conductor_supervise_step` | **每 1 s**（`mw.py:344-367` serve 主循环 `time.sleep(1)`） | 读 `["enabled"]` 决定 spawn/terminate conductor |
| `conductor.py:2036` | `tick()` enabled 门 | 每 tick 1 次（默认 4 s，`poll_interval_sec` 1..5） | `enabled`/`paused` 短路 |
| `conductor.py:169` | `orchestrate()` 开头 | 每 tick 1 次（仅 enabled 且未 paused） | 传给 gate/phase 机器 |
| `conductor.py:3975` | `main()` 主循环取间隔 | 每 tick 1 次（tick 之后） | `poll_interval_sec` 热更新 |
| `conductor.py:1874` | L3 verify→done 路径 | 仅 L3 成功边界（低频） | `_record_advance_result` |
| `dispatch.py:229` | `_read_caps` | 每次派发（低频） | **走的是无缓存的 `load_config`** |

- 每 tick 调用数：enabled → 3（`:2036` + `:169` + `:3975`）；disabled/idle → 2（`:2036` + `:3975`，`orchestrate` 不执行）。
- `dispatch.py:229` 已经用**无缓存**的 `load_config`，说明"每次真读"在本仓已有先例且无性能投诉。
- `save_config`（`config.py:136-148`）的 `_CACHE.pop`（`:146`）只作用于**写进程自身**；serve/conductor 的 `_CACHE` 是各自进程的模块级变量，跨进程写不会清它。

### 1.2 配置文件的真实大小

| 文件 | 字节 |
|---|---|
| `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\config.json`（FM） | **227 B**（9 键，含 `advance_stall_ticks`） |
| `H:\git\E2Feature\.agenticdoc\_autopilot\config.json`（E2） | **200 B**（8 键，partial） |
| `H:\git\JCodingAss\.agenticdoc\_autopilot\config.json` | 196 B |
| `save_config(default_config())` 规范 12 键 | **307 B** |
| 规范 12 键 + 4 token verify 命令 | **356 B** |

即真实文件 196–356 B，全部 < 0.5 KB。

### 1.3 成本实测（同机 10 万次，Python 3.14.3）

| 操作 | µs/op | 备查 |
|---|---|---|
| `path.stat()` | 5.18 | |
| `path.read_bytes()` | 27.89 | |
| `json.loads(path.read_bytes())` | 40.06 | |
| `load_config(root)`（exists+read+parse+validate） | 60.05 | 无缓存全量读 |
| `cached_load(root)` 命中（resolve+stat+deepcopy） | **85.2 ～ 109.3** | 两次运行 |
| `path.resolve()` | **67.02** | 命中路径的实际大头 |
| `json.loads(json.dumps(cfg))`（深拷贝） | 3.70 | |
| `sha256(path.read_bytes())` | 35.81 | 方案 (b) 的内容指纹 |
| `stat+read+parse+validate+deepcopy`（(a) 无缓存探针） | **69.85** | |
| `load_config(missing root)` | **14.92** | 文件缺失 |
| `cached_load(missing root)` | **167.36** | 文件缺失（**11× 更慢**） |

**量化结论：**

1. 缓存命中路径 = `resolve()` + `stat()` + 深拷贝 ≈ 67 + 5 + 4 = 76–109 µs；
   "每次真读" = `exists()` + `read_text` + `json.loads` + `validate` ≈ 60–70 µs。
   **命中比不命中还慢**，因为 `path.resolve()`（Windows 上会做路径规范化/文件系统探测）比读一个 200 B 文件更贵。缓存唯一省下的是 `json.loads`（~6 µs，约 10%）。
2. `mw.py:161` 与 `conductor.py` 传入的 `project_dir`/`project_root` **已经是 `resolve()` 过的绝对路径**（`mw.py` serve 入口 `pathlib.Path(args.project).resolve()`），缓存键里的再次 `resolve()` 是纯重复开销。
3. 文件缺失（autopilot 从未启用，**最常见状态**）时缓存反而慢 11 倍：167 µs vs 15 µs。
4. 调用率 ~1.75 次/s：现状 0.19 ms/s、无缓存 0.12 ms/s；缺文件时 0.29 ms/s → 0.026 ms/s。两者都远低于噪声。

### 1.4 "缓存到底省了什么"的最终裁决

**什么都没省。** 它省掉一次 `json.loads`（~6 µs），却换来两次 `resolve()`/`stat()` 级系统调用与一次 `json` 往返深拷贝；在本机对 200–356 B 文件是净负收益。且它的失效判据不完备（§1.5），是 AC-003 的根因。

### 1.5 同尺寸 stale 可复现实测

`(st_mtime_ns, st_size)` 失效判据的漏洞：同字节长度 + 同一 mtime 刻度 → 判据命中 → 返回旧 dict。

**(i) mtime 刻度（600 次同长度裸字节写）**

```
相邻写共享同一 mtime_ns：326/599 = 54.4%
非零增量：n=273  min=364000ns(0.364ms)  median=519900ns(0.52ms)  max=1249400ns(1.25ms)
```

**(ii) AC-003 形状复现（400 次同长度 `xkey_verify_cmd` 裸字节改写）**

```
[cached_load 初读] ['python','-m','pytest','-q']
[改写 -q <-> -x，字节长度完全相同，不用 os.utime、不清缓存]
400 same-length xkey_verify_cmd rewrites: stale=95 (23.8%)
```

（另一次 500 次 `round_budget` 同长度改写：stale=57，11.4%。stale 次数与"相邻写同 mtime_ns"次数**精确相等**，证明唯一成因就是刻度重合。）

**(iii) Windows `ctime` 不随修改变化**（决定方案 (d) 的 ctime 子案不可行）

```
size1=9 mtime1=1790403759059188400 ctime1=1790403759059188400
size2=9 mtime2=1790403759109780400 ctime2=1790403759059188400
mtime changed = True | ctime changed = False
```

Windows 上 `st_ctime_ns` = 创建时间，内容改写后完全不变 ⇒ 不能作为二次校验键。

## 2. TS 侧行为

### 2.1 读侧：无缓存，每次读盘

- `status-model.ts:56 configPath(projectDir)` → `<root>/.agenticdoc/_autopilot/config.json`。
- `status-model.ts:178 readConfig`：**每次调用都 `fs.readFileSync(file, "utf8")`（`:182`）+ `JSON.parse` + `validateConfigData`**，函数内无任何 memo/cache。
- `monitor.ts:58 MONITOR_INTERVAL_MS = 4000`；`startMonitor`（`:696`）`setInterval(render, 4000)` → 每次 `render` → `readMonitorState`（`:186`）→ `:234 readConfig` → `:269 deriveAutopilotPanel` → `:469 readConfig`。**每 4 s 真读一次**，且文件被 `tmp + rename` 原子替换（`status-model.ts:255-256`），读到的一定是完整内容。
- `/autopilot status`（`console.ts:160-162 cmdStatus` → `deriveStatusModel` → `readConfig`）是**用户手动触发的命令**，不是周期轮询；每次执行都真读。
- `/autopilot enable|disable|pause|resume`（`console.ts:282/287`、`:334/339`）是先 `readConfig` 再 `saveConfig`，同为真读。

**结论：TS 读侧不受同尺寸改写影响——它压根没有缓存。** 因此"两侧必须一起修"的表述需要修正为：**修在 Python 读侧即可覆盖所有写者；TS 侧无需改读，但若采用写侧方案 (c) 则 TS `saveConfig` 也必须一起改**。

### 2.2 写侧：TS 是生产环境的既有唯一写者

- `status-model.ts:234 saveConfig`：`JSON.stringify` + tmp + `renameSync`；`console.ts:287/339` 是唯一生产调用点（RQ-2 §2 已证）。
- 该写发生在**另一个进程**：不会触碰 Python serve/conductor 的 `_CACHE`。所以 TS 写出的同字节长度内容（例如 `poll_interval_sec: 4 → 5`，或本 key 新增 CLI 与 console 互相覆盖 `xkey_verify_cmd` 的同长命令）同样会被 Python 侧静默忽略。
- 本 key 新增的 `mw autopilot verify set`（Python `save_config`）是**第一个 Python 生产写者**，同样是独立进程，`_CACHE.pop` 只清它自己。

→ 写者类别至少三类：**外部手改**、**TS console**、**Python CLI**。修在读者处（a/b）一次覆盖三类；修在写者处（c）要同时改 Python 与 TS，且永远漏掉外部手改。

## 3. 既有测试约束（改判据会红哪几条）

### 3.1 `packages/multi-workers/test_autopilot_config.py`

| 行 | 测试 | 锁定的语义 | 改判据后是否红 |
|---|---|---|---|
| `:113-145` | `test_mtime_cache_invalidation` | ① `save_config` 后 `cached_load` 看到新值（`:117-118`）；② 外部写（**不同长度** + `os.utime(+10s)`）被拾取（`:120-128`）；③ 返回值是防御性拷贝（`:130-133`）；④ `invalidate_cache()` 强制重读（`:135-137`）；⑤ `save_config` 后自进程缓存一致（`:139-143`） | **不红**。全部是"读到新值/拷贝隔离"断言，没有一条断言"必须命中缓存/必须避免再读"。方案 (a) 全部满足。(a) 若**去掉深拷贝**则 ③ 红——所以推荐保留深拷贝。④ 在 `invalidate_cache` 保留为 no-op 时仍通过；若删除该函数则需改测试。 |
| `:147-154` | `test_cache_absent_then_created` | 缺文件→默认（并"缓存 absent"）；`save_config` 后→新值 | **不红**。行为断言在 (a) 下天然成立；注释里"caches absent"措辞需改。 |
| `:29-36` | `test_defaults_when_file_missing` | `load_config`/`cached_load` 缺文件返回默认且**零足迹** | 不红（`load_config` 本身不建目录）。 |

**没有任何测试**断言 `cached_load` 命中时不再触发 IO（例如 `monkeypatch` `load_config` 计数）——`test_autopilot_conductor.py:300` 的名字 `test_serve_step_uses_cached_config_and_pid_file` 具有误导性，其 docstring 已自认"config 侧是 `cached_load` 自己的契约"，测试体只验 spawn/terminate 行为：

```
:303 """... mtime-cached config side is config.cached_load's own contract, covered by T-02 tests)."""
```

### 3.2 其它引用点

| 位置 | 引用 | 影响 |
|---|---|---|
| `test_autopilot_conductor.py:178` | `monkeypatch.setattr(conductor.config, "cached_load", boom)` | 只验 tick 异常转 `config` 事件；(a) 保留同名函数则不动 |
| `test_autopilot_conductor.py:638` | `config.invalidate_cache()` | 若删除 `invalidate_cache` 需删这行；保留 no-op 则不动 |
| `test_autopilot_xkey_registration.py:756` | `config.cached_load(root).get("xkey_repair", False)` | (a) 下行为不变 |
| TS `test/suite/autopilot-console.test.ts:768-801`、`autopilot-monitor.test.ts:1040-1049` | `readConfig`/`saveConfig` 直调 | TS 读侧本就不缓存，无影响 |

**小结：改成 (a) 后既有测试零红（前提：保留函数名 `cached_load`/`invalidate_cache` 与深拷贝契约）。** 需要新增的是一条 AC-003 回归测试（同长度裸字节写、连续两 tick 拾取），而不是改存量断言。

## 4. 候选方案对比

| 维度 | (a) 取消 stat 短路 | (b) 内容指纹缓存 | (c) 写侧推 mtime | (d) mtime+size 命中后再校验 |
|---|---|---|---|---|
| 改动面 | `config.py:73-74` 删 `_CACHE`；`:146` 删 pop；`:150-170` 重写；`:173-175` no-op/删；docstring `:30-31`；测试 `test_autopilot_config.py:113-145` 重写 | `config.py:73-74` 缓存值改 `{size, sha256, parsed}`；`:150-170` 命中前先 `read_bytes`+sha；同样删 pop | Python `save_config:136-148` 加 `os.utime(ns=...)`；TS `status-model.ts:234-259 saveConfig` 加 `fs.utimesSync`；判据测试改写 | `:166` 命中分支加 `st_ctime_ns` 比较（**Windows 无效**，实测）或"大小阈值内直接重读"（= (a) 多绕一层） |
| 失败面 | 无（每次真读，必然最新） | 无（内容哈希，跨进程必然正确） | **外部手改/`git checkout`/其它工具写永远 stale**；(c) 只在 `save_config`/`saveConfig` 两个写者下成立；`os.utime` 把 mtime 推到来，可能与其它以 mtime 为判据的逻辑（构建/缓存/`git` 状态显示）互相干扰；并发两写者推 mtime 需保证单调 | `ctime` 子案在 Windows **完全失效**（§1.5(iii)：内容改写后 ctime 不变）；"阈值内重读"子案 = (a)，判据更复杂 |
| 性能 | 每次 `load_config` 60 µs（缺文件 15 µs）；**比现状命中 85–109 µs 更快**，缺文件快 11× | `read_bytes`+`sha256` 33.9 µs，命中省掉 `json.loads`（6 µs）但加了 sha（6 µs）→ **与直接读+parse（40 µs）基本相等**，零收益 | 读侧不变（仍有 23.8% stale 窗口）；写侧 +2–5 µs（可忽略） | ctime 比较 ~5 µs（但无效）；重读子案 = (a) 成本 |
| 跨进程正确性 | **正确** | **正确**（sha 在读取进程计算） | **不正确**（只保证自家写者） | ctime 案不正确；重读案正确 |
| 是否也修 TS 侧 | **不需要**（TS 读侧无缓存） | 不需要 | **必须**（`saveConfig` 也要 utime，否则 TS 写仍 stale） | ctime 案不需要但无效；重读案不需要 |
| 与 AC-003 的"不用 os.utime" | 一致 | 一致 | **冲突**（把 `os.utime` 挪进生产写者，等于用被禁的手段达成判据） | 一致（但无效/等价于 a） |

### 4.1 (b) 为什么也不值得

方案 (b) 的设计目标是"省 parse 不省读"。但在 200–356 B 文件上：
`read_bytes` = 27.9 µs、`json.loads(read_bytes)` = 40.1 µs、`sha256(read_bytes)` = 35.8 µs。
命中时省下 `json.loads`（≈12 µs，40.1−27.9）却付出 sha 的 6–8 µs，**净收益 <6 µs**，而且缓存表从"存解析结果"升级为"存 size+sha+解析结果"，复杂度更高。只有当配置文件增长到几十 KB（parse 成本 >> 哈希成本，例如机器层合并出大 `xkey_verify_cmd` 矩阵）时才可能划算——当前不存在这个规模。

### 4.2 (c) 的定位

(c) 不是修复，是**缓解**：它能让"两条 CLI/console 路径"的写立即生效（实测 `os.utime(+2 ms)` 后同长度写确实被拾取），但：
1. AC-003 明确要求"不用 `os.utime`"；把 utime 藏进 `save_config` 是对判据的规避；
2. 外部手改（本 key 的核心场景之一：`config.json` 是 human-editable 的，docstring `config.py:8-9`）、`git checkout`、其它工具写全部漏掉；
3. 推 mtime 会污染其它 mtime 消费者。

若最终仍想保留某种缓存，正确姿态是 **(b) 内容指纹**（读侧自证），而不是 (c)。

## 5. 推荐方案与理由

### 5.1 推荐：(a) 取消 stat 短路

把 `cached_load` 从"mtime+size 缓存"改成**每次真读**的同义函数：

```python
# autopilot/config.py
def cached_load(project_root: pathlib.Path) -> dict:
    """Backwards-compatible name for load_config: every call re-reads and
    re-parses the file. The former (mtime_ns, size) short-circuit was both
    incomplete (same-length rewrites inside one mtime tick were ignored,
    AC-003) and slower than a plain read on Windows (path.resolve() ~67 us
    vs a 200 B read+parse ~40 us). Returns a defensive copy."""
    return json.loads(json.dumps(load_config(project_root)))
```

理由（按证据排序）：
1. **缓存净负收益**（§1.3/§1.4）：命中 85–109 µs > 无缓存 60–70 µs；缺文件 167 µs vs 15 µs。
2. **唯一能对所有写者类别成立的读侧修复**（§2）：外部手改、TS console、Python CLI 一次覆盖。
3. **不引入新失效语义**：mtime/size/ctime 在 Windows 上都不足以做内容判据（§1.5）；内容指纹（b）成本≈全读（§4.1）。
4. **无测试阻力**（§3）：存量断言都是"读到新值"，改后零红。
5. **已有先例**：`dispatch.py:229` 一直用无缓存 `load_config`。

### 5.2 分支：若 X 则改选 Y

- **若** design 期实测发现未来配置文件规模会到几十 KB（例如机器层把 `xkey_verify_cmd` 扩成大量矩阵），**且** 每 tick 读盘成为可观开销 → 改选 **(b) `{size, sha256, parsed}` 内容指纹缓存**（读侧自证，仍对所有写者正确）。当前规模（196–356 B）不成立。
- **若** 出于非性能原因必须保留 mtime 短路（例如不允许每次读盘）→ 必须选 **(b)**，**不能选 (c)**；(c) 无法覆盖外部写者。
- **(d) 的 `st_ctime_ns` 子案在 Windows 上直接排除**（§1.5(iii)）；(d) 的"阈值内重读"子案等价于 (a)，无需额外复杂度。

### 5.3 该方案要改的所有位置

**Python**
1. `autopilot/config.py:73-74` — 删除 `_CACHE`（或保留但不再使用；建议删）。
2. `autopilot/config.py:146` — 删除 `save_config` 里的 `_CACHE.pop(...)`。
3. `autopilot/config.py:150-170` — 重写 `cached_load`（每次 `load_config` + 深拷贝）。
4. `autopilot/config.py:173-175` — `invalidate_cache()` 改为 no-op（保留名字以免动测试），或在更新测试后删除。
5. `autopilot/config.py:30-31` — 更新模块 docstring 里"mtime cache lets ... poll without re-reading"的说明。
6. **本 key 新增的机器层解析器不要重新引入缓存**（AC-007 的"缓存键含机器层 (path, mtime_ns, size)"措辞随之作废，见 §6.3）。

**TS**
7. 读侧**无需改**：`status-model.ts:178 readConfig` 已是无缓存真读。
8. 写侧**无需改**（未采用 (c)）：`status-model.ts:234 saveConfig` 保持现状。

**测试**
9. `test_autopilot_config.py:113-145` — 重写 `test_mtime_cache_invalidation`：保留"外部写被拾取""防御性拷贝""写后一致"三条断言，去掉 `os.utime` 依赖，改成**同长度裸字节写 + 无 utime**；`invalidate_cache` 断言改为 no-op 语义或删除。
10. `test_autopilot_config.py:147-154` — 更新"caches absent"注释。
11. `test_autopilot_conductor.py:300` — 更新测试名/docstring（"cached config" → "config"）。
12. `test_autopilot_conductor.py:638` — 若删 `invalidate_cache` 则删该行；保留 no-op 则不动。
13. **新增 AC-003 回归测试**（`packages/multi-workers/test_autopilot_config.py` 或 `test_autopilot_conductor.py`）：同一进程连续两次 `cached_load`/`tick()`，之间**用另一个进程/裸字节写**写入同字节长度的不同内容，**不用 `os.utime`、不清缓存**，断言第二次读到新值。

### 5.4 对 `mw.py:161`（1 s 复查）的影响

| | 现状 | (a) 之后 |
|---|---|---|
| 配置存在（典型 FM/E2） | ~85–109 µs / 次 ⇒ 0.085–0.109 ms/s | ~60–70 µs / 次 ⇒ 0.06–0.07 ms/s |
| 配置缺失（autopilot 未启用，最常见） | ~167 µs / 次 ⇒ 0.167 ms/s | ~15 µs / 次 ⇒ 0.015 ms/s（**11× 快**） |
| 正确性 | 同尺寸改写 23.8% 概率漏判 | 必然拾取 |

即：**性能不变差，缺文件场景显著变快，且消除 AC-003 漏洞。** 对 conductor 每 tick 的 2–3 次调用同理（enabled 时 0.75 次/s）。

## 6. AC-003 判据裁决

### 6.1 "另一进程写入"是否足够？——不够

AC-003 现文：

> 同一 conductor 进程连续两次 `tick()`，之间由**另一进程**写入**同字节长度**的不同命令（不用 `os.utime`、不清缓存）⇒ 第二次 tick 使用新命令。

问题在于"另一进程"**没有限定写者**：

- 若该进程是 `mw autopilot verify set`（走 `save_config`），则方案 (c) 能通过；若该进程是裸字节写/外部手改，则 (c) 失败。**同一个 AC 文本对"修读者"和"修写者"给出不同判据**，设计/实现会分叉。
- 必须**显式要求写入是裸字节写**（不经 `save_config`、不 `os.utime`），否则 (c) 可以靠写侧 utime 作弊。
- "不用 `os.utime`"目前只约束了测试动作，没有约束实现——应改为"**检验的写入路径不得依赖 `os.utime`**"，把 (c) 排除在合规解之外（除非 spec 明确接受写侧方案，见 6.2）。

### 6.2 必须覆盖的写者类别

缓存 bug 在**读者**，与写者无关，所以判据应一次覆盖三类（否则每出现一个新写者就要补一条 AC）：

1. **外部手改 / 裸字节写**（`config.json` 是 human-editable，`config.py:8-9`）——最根本的一条；
2. **TS console 写**（`status-model.ts:234 saveConfig`，跨进程，既有唯一生产写者）；
3. **Python CLI 写**（本 key 新增的 `save_config`）。

其中 (1) 用裸字节写即可代表 (2)/(3)（三者对读者等价：都是"另一进程改了文件、长度相同、mtime 刻度相同"）。因此判据建议改为：

> **AC-003（拾取 ≤1 tick，含任意写者、同尺寸）**：同一 conductor 进程连续两次 `tick()`；两次之间由**另一个进程以裸字节方式**（不经 `save_config`、不用 `os.utime`、不清缓存）写入**同字节长度**的不同命令 ⇒ 第二次 tick 使用新命令。
> 附一条**对照用例**：外部手写同长度不同内容后，`serve` 的 1 s 复查（`mw.py:161`）也读到新 `enabled`/`paused`。
> 若设计选择写侧方案，则本 AC 必须**额外**声明"外部手改不在本 AC 覆盖范围内"并接受该缺口——不建议。

### 6.3 对 AC-007 的连带修正

AC-007 现文含"缓存键必须包含机器层的 `(path, mtime_ns, size)`，否则机器层改动不生效"。若采纳 (a)（无缓存），该句作废，应改为：

> 机器层与项目层**每次解析都重新 stat/read**（两层各自的改动都在下一次 tick 生效）；若设计选择缓存，缓存键必须同时覆盖两层的内容。

即"两层改动都生效"是判据，`(path, mtime_ns, size)` 是实现细节，不应写进 AC（这正是 RQ-2/P-015 记录的"实现细节当判据"错误）。

## 7. 复现命令

环境：`cd H:\git\Multi-Workers\packages\multi-workers`（Python 需 `sys.path` 加包目录）。

- 成本探针（§1.3）：`$env:TEMP\rqd1_bench.py`、`rqd1_bench2.py`
  - 核心：对同一 root 分别循环 `path.stat()` / `path.read_bytes()` / `json.loads(path.read_bytes())` / `cfg.load_config(root)` / `cfg.cached_load(root)` / `path.resolve()`，各 100 000 次取均值。
- 同尺寸 stale（§1.5）：`$env:TEMP\rqd1_xkey.py`
  - 核心：`raw1`/`raw2` 为 `xkey_verify_cmd` 从 `-q` 改 `-x` 的同字节长度 JSON（`assert len(raw1)==len(raw2)`），循环 `p.write_bytes(...)` + `cfg.cached_load(root)`，统计与期望不符的次数。
- Windows ctime（§1.5(iii)）：`$env:TEMP\rqd1_ctime.py`
  - 核心：写 9 B → `stat()` → 同长度改内容 → `stat()`，比较 `st_ctime_ns`。
- 候选 (c) 验证（§4.2）：`rqd1_xkey.py` 末尾，`os.utime(ns=(atime, mtime+2_000_000))` 后同长度写确实被拾取。
- 真实样本尺寸（§1.2）：`Get-Item <root>\.agenticdoc\_autopilot\config.json`。

（本次调查只写本文件；上面探针均为 `$env:TEMP` 下的临时脚本，未改动任何仓库文件。）