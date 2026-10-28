# T-05 Python 解析器下沉 + 跨语言平价锁（coding）

- Key: claim-driven-review-orchestration
- 里程碑：M1（只读规划器）
- type: coding
- 依赖：T-01（`shared/review-split.ts`）、T-02（`mw review-split`）均 done

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（PM 管多 worker 并行、文件驱动协调；开关是这套东西的第一道可逆扳手）。

PM 亲测发现两处问题：

1. **诊断不对称**：`.mw/review-split.json` 是坏 JSON 时，
   TS 侧 `resolveReviewSplit` 回 `invalid: "config-invalid-json"`，而 `mw review-split status` 静默返回
   `off/default`——用户看不出"配置写坏了"。实测：
   `Set-Content .mw/review-split.json '{ broken json'` → `{"mode":"off","source":"default","invalid_env":null}`。
2. **解析器位置错**：实现落在 `mw.py` 里，而 conductor（服务进程）不会加载 CLI 模块，
   无法读取同一开关。设计（`design.md` §2.1）要求 Python 侧落在 `autopilot/` 下可被 import。

TS 侧的权威语义与诊断字符串以
`packages/coding-agent/src/extensions/agent-team-loop/shared/review-split.ts:138` 为准——
**逐字读取该文件，照抄字符串，不要自造**（例如 `review-split.ts:111` 的 `config-invalid-json`）。
Python 现实现见 `packages/multi-workers/mw.py:11087`（`_review_split_resolve`）。

## 要求

1. 新增 `packages/multi-workers/autopilot/review_split.py`：
   - `REVIEW_SPLIT_MODES/DEFAULT/ENV/CONFIG`（与 TS 同名同义）；
   - `resolve_review_split(project_dir, env=None) -> dict`，键固定为
     `{"mode","source","config_path","invalid"}`，语义与 TS 一一对应（含
     `config-invalid-json` / `config-invalid-shape` / `config-invalid-v:<v>` / 非法 mode 的诊断串，
     以及 env 非法时的原文）；
   - `set_review_split(project_dir, mode) -> dict`（原子写，非法值抛 `ValueError`，由 CLI 转 exit 2）；
   - 永不抛异常（除非 `set` 的非法入参），纯读。
2. `mw.py` 改为**委托**该模块：`_review_split_resolve` / `_review_split_set` 保留为薄封装，
   CLI 文本与 `--json` 输出**保持现有形态**（`mode/source/config_path/invalid_env`），
   只把 config 坏文件的诊断补进 `invalid_env` 之外的字段：
   `--json` 增加 `"invalid"`（值取自 `resolve_review_split()["invalid"]`），文本输出在有值时追加 ` invalid=<v>`。
   `test_review_split_cli.py` 的 7 条必须仍然全绿（如断言 `--json` 键集合则同步更新该测试）。
3. **共享用例表**：新增 `packages/coding-agent/test/suite/fixtures/review-split-cases.json`，形如
   ```json
   [{"name":"env-on","env":{"MW_REVIEW_SPLIT":"on"},"config":null,"expect":{"mode":"on","source":"env","invalid":null}}, ...]
   ```
   覆盖至少 9 例：默认、env=on、env=`PLAN`（大写）、env 非法、config=plan、env 覆盖 config、
   config 坏 JSON、config `v=2`、config mode 非法。
4. TS 侧：`test/suite/review-split-mode.test.ts` 增加一组"表驱动"用例读该 JSON，
   断言 `mode/source` 与 `invalid` 与表一致（保留原有 8 条）。
5. Python 侧：新增 `packages/multi-workers/test_review_split_parity.py`，读**同一份**表格，
   断言 `resolve_review_split` 输出与 `expect` 一致。
   跨语言平价因此由"同一张表"保证，不靠人工对照。

## 交付格式

- 报告 `report.md` 四段：`## 结论` `## 证据`（每例一行）`## 未覆盖面声明` `## 上下文来源`。
- 证据里必须贴两条命令的输出版本：pytest 与 vitest 的实际行数。

## 写入允许面

- `packages/multi-workers/autopilot/review_split.py`（新）
- `packages/multi-workers/mw.py`
- `packages/multi-workers/test_review_split_parity.py`（新）
- `packages/multi-workers/test_review_split_cli.py`（仅在 `--json` 键集合变化时同步）
- `packages/coding-agent/test/suite/fixtures/review-split-cases.json`（新）
- `packages/coding-agent/test/suite/review-split-mode.test.ts`（只增用例）

## 写入禁止面

- `shared/review-split.ts`（TS 语义是权威，不得为迁就 Python 改动）
- 其他任何 `packages/**`、`.mw/**`、`.agenticdoc/**`、`dist/**`

## 验收命令

```
cd packages/multi-workers && python -X utf8 -m pytest test_review_split_parity.py test_review_split_cli.py -q
cd packages/coding-agent   && node ../../node_modules/vitest/dist/cli.js --run test/suite/review-split-mode.test.ts
```

两条都必须全绿；另在临时目录手工验一次坏 JSON 的 `status --json` 出现 `config-invalid-json`。

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡：PM 实测发现诊断不对称 + 解析器位置错 | T-02 终态 + design.md §2.1 |
