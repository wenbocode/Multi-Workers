# Evidence Run: 006-dispatch-injection

- Date: 2026-09-11T19:40:00+08:00
- Task: 006-dispatch-injection（S3）
- Deliverables:
  - `autopilot/dispatch.py`: `render_task_md` 增 `deny_globs` 参数（单引号渲染——前导 `*` 是 YAML alias 标记，单引号风格无转义序列，与 worker-mode.ts 剥引号解析严格对齐）；`_expand_read_scope`（dual：相对条目锚 game 根展开 + 控制根附加去重；single/空 scope：原样透传）；`_resolve_deny_globs`（默认 target.yml ignore.deny_globs，显式参数含空表胜出）；`dispatch()` 增 `deny_globs: Sequence[str] | None`，target.yml 不可用 → reject（`target-config-unusable`，事件类型 `target-config-rejected`）
  - `autopilot/timeline.py`: EVENT_TYPES 登记 `target-config-rejected`（14→15）
  - `test_autopilot_dispatch.py`: +7 用例；`test_autopilot_timeline.py`: 枚举锁 14→15

## 测试命令与结果

```
python -m pytest test_autopilot_dispatch.py -q -s
  17 passed（10 既有 + 7 新增）

python -m pytest -q                # 全量
  401 passed, 8 deselected（394 基线 + 7 新增，零回归）

npm run check → exit 0
```

## [VERIFY] 行

```
[VERIFY] VC-013: single_no_yml_snapshot=true
[VERIFY] VC-013: deny_globs_line=true control_scope=true
[VERIFY] VC-009: game_abs=true engine_abs=true
[VERIFY] VC-013: scopeless_deny_injected=true no_scope_forced=true
[VERIFY] VC-013: broken_yml_rows=0 fail_closed=true
```

## 关键语义（执行期确定，design D-005/D-007 落地细化）

- **控制根附加仅作用于非空 scope**：对空 scope 追加会凭空制造 containment（scopeless 类型 phase-writer/repair 需全树访问，AC-012 红线）——首跑测试抓出（scopeless 用例 read_scope 意外出现），`not scope` 守卫修正
- **deny_globs 注入不分模式**：single + target.yml ignore.deny_globs 也注入（单根 UE 项目同样需要 DDC 防火墙）；single 无 target.yml → 零注入，快照逐字节一致
- **single 模式 scope 原样透传**：相对条目本就锚 cwd=控制根，展开只会扰动输出
- deny globs 无控制根豁免：`**/*.uasset` 对控制树同样生效——deny 优先于 allow（VC-012），设计如此（防火墙意图：二进制资产在哪都不该读）
- 显式 `deny_globs=[]`（非 None）= 明确压制注入；None = 走 yml 默认

## 快照回归保护

`test_dispatch_single_mode_no_yml_snapshot`：无 target.yml 时 dispatch 产出与注入前逐字节一致（含既有尾部空行格式）
