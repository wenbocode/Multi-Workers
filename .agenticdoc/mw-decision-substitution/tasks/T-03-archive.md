# T-03 决策档案写入器 + fold

- key: mw-decision-substitution · type: coding · phase TASKS
- timeout: 40
- 依据: spec.md rev3（AC-006/007）+ design.md D-005..D-008、D-013、D-018 + plan.md §1

## 上下文

- 档案路径 `.agenticdoc/_autopilot/decisions.jsonl`；4 类行；append-only + `prev_sha` 链 + 单写者。
- 设计（函数签名、seq 语义、半行尾策略、幂等、fold、对账）见 `evidence/research/design-decision-archive-20261019.md` Q1..Q6，按该设计实现。
- 锁协议：`packages/multi-workers/mw_common.py:acquire_lock:2369-2390`；用法先例 `mw.py:772-792`。

## 要求

1. 新建 `packages/multi-workers/decide_archive.py`：`state_digest`、`iter_rows`、`fold`、`append_decide`、`append_override`、`append_settle`、`append_authority_change`（签名照 D2 Q1.2）。
2. `append_*` 校验失败或 IO 失败一律抛 `DecisionArchiveError`（子类 `DecisionArchiveDuplicate`）；不得静默丢弃。
3. 锁内完成"读尾 → 算 prev_sha → 追加"并做文件尺寸复核；半行尾保留不 truncate。
4. `fold(rows)`：按 `decision_id` 分组、按 seq 排序、outcome 取最后 settle、override 存在即 true、坏行计数。
5. 新建 `packages/multi-workers/test_decide_archive.py`：链完整性、半行尾恢复、重复 decide 拒绝、4 类行字段校验、fold 合并、并发两写者不产生重复 seq。

## 交付格式

- 实现按上列写入允许面落地；报告四段：结论 / 证据（命令 + 输出摘要）/ 残留与未验证 / 改动文件清单。
- 每处关键实现附 `path:line`；关闭态未证明前不得声称完成。
- 遇到契约不足：停手并在报告"残留"里写明，禁止自行改契约。

## 种子

- goal 锚点: `.agenticdoc/goal.md`（文件驱动的去中心化协调 / 项目级目标对齐）
- 代码锚点: `packages/multi-workers/mw_common.py:2369-2390`
- 代码锚点: `packages/multi-workers/decision.py:945-961`

## 写入允许面

- `packages/multi-workers/decide_archive.py`（新建）
- `packages/multi-workers/test_decide_archive.py`（新建）

## 写入禁止面

- 除上列文件外的一切文件（含其它包的源码、其它 key 目录、`_pitfalls.md`、`_project_log.md`）
- 禁止 `git add` / `git commit` / `git checkout` / `git stash` / `git clean`
- 禁止修改 `packages/ai/src/models.generated.ts`、禁止跑 `npm run build`、禁止跑完整 vitest 套件（用 `./test.sh` 或指定测试文件）

## 验收命令

```bash
cd packages/multi-workers && python -m pytest test_decide_archive.py -q
```

## 改动历史

- 2026-10-20 创建
