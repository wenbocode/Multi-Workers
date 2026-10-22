# mini-spec — 签收决策点按 key 通用 + 进授权表

## 目标（用户裁定，2026-10-21）

`dp25-signoff-conclusion` 不是本 key 专属，而是**任意 AgenticTask key 收尾时的通用签收点**；并且它必须作为一行真实条目落进 `.mw/decide-points.json`（唯一授权源），而不是只以注册表默认值隐身存在。

## 现状（实测）

- 代码已经按 key 通用：`decide_signoff.collect(project_dir, key)`、`auto_conclusion(..., key=...)` 都接收 key；`mw decide sign --key <key>` 可从仓库根直接对任意 key 运行；`REQUIRED_STATE_FIELDS["dp25-signoff-conclusion"] = (key, rows_total, rows_available, chain_ok, p0_open)` 里 `key` 是调用方传入。
- 缺的是三处：
  1. 文案（`decision_points.py:830` "替代人签"、`decide_registry.json` 的 `wiring_note`、`docs/decision-points.md`）读起来像"本 key 的签收"，没有说明"任意 key 通用 / 怎么指定 key"。
  2. `.mw/decide-points.json` 只有 24 行（`dp25` 靠注册表默认值生效，`source=default`），授权表不是唯一可审计源。
  3. 把行补进授权表的唯一合规手段 `mw decide dp refresh`（注册表→表单向合并，**只补缺失行、永不改已有 `enabled`/`mode`**）被 `xkey-gate-guard` 的 `TABLE_WRITE_CLI_RE` 当成"机器写授权表"拦死。

## 改动

1. `decision_points.py`：dp25 的 `description` 与 question `instructions` 首句改为"任意 AgenticTask key 的收尾签收结论（按 key 计算）"；`questions_version` 只 hash `id/type/choices/dynamic_choices`，不受影响。
2. `decide_registry.json`：dp25 的 `wiring_note` 补"任意 key：`mw decide sign --key <key>`"，随后 `dp export --write` 重渲染（wiring 段落是手工维护、`--write` 保留）。
3. `shared/xkey-gate-guard.ts`：`TABLE_WRITE_CLI_RE` 去掉 `refresh`（保留 `on|off|set|apply`），说明文字补一句"`refresh` 是注册表→表单向同步，只补缺行、不改已有开关，因此放行"。
4. 跑 `mw decide dp refresh --project .` → `.mw/decide-points.json` 出现 `dp25-signoff-conclusion` 行（P2 默认 `enabled: true`、`mode: auto`、`source=L0`）。
5. 测试：guard 测试更新（`refresh` 放行、`on/off/set/apply` 仍拦）；Python 新增"任意 key 可签收"用例（临时 key + 档案行 → `auto_conclusion`/`signoff_state` 用该 key）。
6. 文档：`docs/decision-points.md` dp25 行与 §9 说明、`flowcharts.md` §2.7 标注"任意 key"、两包 CHANGELOG。

## 非目标

- 不放开 `mw decide dp on|off|set|apply`（仍需人签/人操作）。
- 不改 `signoff` 的 auto/disable 语义、不改 dp25 判据、不改 P2 默认开启的注册表铁律。
- 不重建 `dist/**`（运行期生效需 rebuild + `/reload`，由用户放话）。

## 验收

```
cd packages/multi-workers
python -m pytest -q test_decide_sign_auto.py test_decide_signoff.py test_decision_points.py test_decide_registry_contract.py test_decide_registry_export.py test_decide_dp_cli.py
python mw.py decide dp check --project .            # rc=0
python mw.py decide dp show --project . dp25-signoff-conclusion   # source=L0, enabled=true
python -c "json 断言 .mw/decide-points.json 有 25 行且 dp25 enabled=true"
python scripts/gen_decide_registry_ts.py --check    # rc=0
cd packages/coding-agent && npx vitest --run test/suite/xkey-guard-coverage*   # rc=0
```
