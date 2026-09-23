# 调研：mw-rag-window-parity（design 阶段）

日期: 2026-09-23 · 方案比较与选型依据

## 1. `skill.dir`：三种修法比较

| 方案 | 做法 | 后果 |
|---|---|---|
| A（选中） | TS 解析层放宽为 `null`（`optionalString`），调用点 `resolveCliDir(root, dir ?? root)` | 两侧解析值同义（`None`↔`null`）；fingerprint payload 不变 → parity 不破；可单测 |
| B | TS 把缺省/`null` 归一化成 `"."` | fingerprint canonical JSON 里 `dir: "."` vs Python `None` → **不相等** → `<!-- mw-rag: v1 -->` 里的 fingerprint 与 launcher 的 `config tear (rag)` 判定不一致，可能拒绝 spawn（D-009/VC-022 的直接破坏） |
| C | 只改 Python 让它也要求非空 | 与「`null` 删除字段」的层间合并语义冲突（合并用 `null` 删除，删除后不应非法）；且手册与既有 Python 行为要同时改，破坏面更大 |

选 A。补充：`dir: ""` 在 A 下仍非法，与 Python 错误文本语义一致（case 差异不影响验收，因为两侧不比对文本）。

## 2. `cliCall` 调用点（不 spawn 也能测）

`rag/tools.ts:735` 现状 `path.resolve(runtime.controlRoot, skill.dir)`；`path.resolve(p, null)` 会抛
`TypeError`（Node 要求 string）。抽出纯函数 `resolveCliDir` 后可单测「缺省 = 控制工作区根」，且 `cliCall` 只做透传。
另一种做法是在 `parseSkill` 里注入默认值，但那会污染 fingerprint（见 §1 方案 B），故不采用。

## 3. `/mw rag` 的退出码与输出体积

- `runMwCli`（`shared/mw-runner.ts:425+`）把非 0 一律折成 `{ok:false,error}`，**丢掉 0/1/2 区分**；而 `mw rag audit`
  的 exit 1 是"有 findings"（预期内的 warning），exit 2 才是用法/配置错误。因此新增内部 `runMwCliRaw` 暴露 `code`，
  既有 `runMwCli` 保持原语义（零行为变化），`ragMw` 用 raw。
- 输出体积：`rag list` 在双服务场景约 40~60 行、`rag audit` 随引用数增长。通知通道不适合长文本 →
  `formatRagOutput` 截断到 30 行并附完整命令（用户可复制到终端）。截断阈值与提示文本由测试钉住。

## 4. doctor RAG 行的跨语言一致性

Python 已有 `_format_rag_doctor_line`（`mw.py:2297`），形如：

```
rag: not enabled (skill missing)
rag: ERROR - rag server 'x': adapter must be 'overcode-v1'
rag: enabled=A, B; probe=A=reachable, B=unreachable; fingerprint=436b6a35ff60; skill=installed; required_missing=2
```

TS 侧照抄同一格式（`formatRagDoctorLine`），并用「同一项目 JSON vs 文本」的比对测试（VC-309）钉住逐字一致。
这样 `/mw doctor` 与终端 `mw doctor` 不会出现两套说法（P-008 家族：文档/界面静默漂移）。

## 5. 测试落点与反例设计

- 新增 `test/suite/rag-window.test.ts`：VC-301~304（纯函数/解析）、VC-306~308（纯函数）、VC-309/310（格式化 + 子进程取 Python 文本行）、VC-311（常量比对）。
- 扩展现有 `rag-parity.test.ts` 覆盖 VC-305（`dir` 三种变体，Python 由 subprocess 实跑 `rag_fingerprint`）。
- 反例（留给独立验证任务）：
  - 把 `parseSkill` 的 `optionalString` 改回 `requireString` → VC-301/302 必须红；
  - 把 `runMwCliRaw` 里追加的 `--project=<dir>` 换成 `--project=.`（或去掉）→ VC-308/309 之一必须红（因为取到的是错的配置）；
  - 注释掉 `formatDoctorReport` 里的 RAG 行 → VC-310 必须红。
- 取得 Python 侧的两种可靠方式（沿用既有 parity 测试的写法）：`python -c "import mw_common; …"` 打印 JSON/串；
  Windows 下子进程显式 `encoding: "utf8"`（D-211）。

## 6. 未决/风险

- `probe` 在测试里若指向可达端口会引入网络与 5s 延迟 → VC-309 的 enabled 用例统一用 `127.0.0.1:9xxx`（不可达、失败快）。
- `/mw rag init` 会写文件（与 `/mw target set` 一致，不做二次确认）；文档需写明这一点。
- 若未来 `mw.py rag` 新增子命令，白名单需同步（设计上把白名单放在一个常量里，测试断言它与 `mw.py` 的
  `_RAG_ACTIONS` 集合一致 —— 该断言需要读 Python 源或跑 `mw.py rag --help`，作为可选加分项，若实现成本高则记为遗留）。
