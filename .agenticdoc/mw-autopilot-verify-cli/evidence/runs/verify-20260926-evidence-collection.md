# 证据汇总：mw-autopilot-verify-cli

- key: `mw-autopilot-verify-cli`
- ac_fingerprint: `9c90fbb3e171`（spec.md 机器抽取 14 条 AC）
- 基线: `b0a30bc12`（spec 期冻结）/ `d52694cc4`（dist 重建）
- 覆盖 HEAD: `8cd472a7b`（本 key 提交 22 个：`b0a30bc12`..`8cd472a7b`）
- 生成: 2026-09-26T07:21:58Z（PM 收口时机器汇总）
- 说明：本文件由 PM 从各卡 `output.md` 的 `[VERIFY]` 行**机器提取**（提取脚本见 §F），并附 PM 独立复跑的命令与输出。引用请以原始 `workers/<card>/output.md` 为准。

---

## §A PM 独立复跑（不采信 worker 自报，全部在已提交树上重跑）

### A1 权威全量回归（HEAD `8cd472a7b`，无并发写者）

```
$ cd packages/multi-workers; python -X utf8 -m pytest -q
2 failed, 1182 passed, 10 deselected, 70 warnings in 133.78s (0:02:13)
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound
FAILED test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below

$ cd packages/multi-workers; python -X utf8 -m pytest -q -m e2e_l2
8 passed, 1186 deselected in 203.11s (0:03:23)

$ cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run \
    test/suite/autopilot-config-parity.test.ts test/suite/autopilot-config-sync.test.ts \
    test/suite/autopilot-console.test.ts test/suite/autopilot-monitor.test.ts \
    test/suite/autopilot-protocol.test.ts test/suite/autopilot-read-scope.test.ts
 Test Files  6 passed (6)
      Tests  101 passed (101)
```

**基线对照（AC-012）**：spec 期基线 `2 failed, 1007 passed, 10 deselected`（`b0a30bc12`）→ 现在 `2 failed, 1182 passed`。
- 红的**集合完全相同**（两条外部既有红，见 §E），红数未增；
- passed 增加 175 = 本 key 新增用例（`test_autopilot_config.py` +34 重写、`test_autopilot_effective_config.py` 27、`test_common_render_argv.py`、`test_doctor_autopilot.py` 4+、`test_mw_autopilot_cli.py` 23、`test_autopilot_config_parity.py` 5、`test_autopilot_xkey_cwd.py` 6、`test_mw_serve_config_partial.py` 10、`test_autopilot_verify_cwd_table.py` 37、`test_autopilot_docs.py` 4 等）。

### A2 AC-009(a)（dist 重建后产物 diff 必须为空）——**PM 亲验，exit=0**

```
$ git add <9 个 catch-up dist 产物> && git commit        # e34fb8bad
$ python -X utf8 packages/multi-workers/mw.py build --install
[mw build] built + self-check OK (activate)
[mw build] bundle: ...\packages\multi-workers\dist\extensions\agent-team-loop.js
[mw build] installed globally: C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js
[mw build] dist rebuilt: ...\packages\coding-agent\dist
=== exit: 0 ===

$ git -c core.fileMode=false diff --exit-code -- packages/multi-workers/dist packages/coding-agent/dist
exit=0        # 空
```

（判据**带 `core.fileMode=false`**，Windows 文件模式位不可信。）

### A3 A1b / A2b 锚点（PM 亲自调 `mw_common` 只读探测）

```
A1b repo_bundle_anchor: {"stale": false, "detail": "repo bundle matches source (kind 6 entries, guard markers present)"}
A2b sourcemap_drift  : {"stale": false, "detail": "sourcesContent matches for 472 source(s) across 472 map(s)"}
```

**A2b 在本 key 执行期真实转过红**：T-08 落地时 `stale=true`，`detail="4 of 472 embedded source(s) differ: ...console.ts, ...status-model.ts"`——成因是 T-04 改了 `console.ts`/`status-model.ts` 而未重建 dist（本 key 已提交源码 vs 落后 dist）。T-10 重建后转绿。**这是 A2b 判据有效性的直接证据**（不是"一直绿"的空判据），同时暴露了"改 TS 源码未重建 dist"这条真实的复发路径。

### A4 文档判据（AC-010）PM 亲跑

```
$ cd packages/multi-workers; python -X utf8 -m pytest -q -s test_autopilot_docs.py
[VERIFY] AC-010: fenced_block=byte-identical block_bytes=417 usage_line=usage: mw.py autopilot verify [-h] {set,show,clear} ... set_help_project_required=True
[VERIFY] AC-010: readme_anchors=12 missing=0
[VERIFY] AC-010: update_matrix_rows=1 layer=项目/机器
[VERIFY] AC-010: a1b=content anchor a2b=sourcemap anchor
4 passed in 0.33s
```

README/UPDATE 正文由 PM 逐段审阅（语义与实现一致：CLI 管四个 xkey 键 / 机器层仅 `xkey_verify_cmd`+`xkey_verify_cwd` / 空值即未决定 / `clear` 永不删文件 / 两侧同版本上线顺序）。

### A5 与其它 key 冻结判据的交叉验证（PM 亲自跑）

```
$ cd packages/multi-workers; python -X utf8 -m pytest -q test_autopilot_readcap_injection.py
1 failed, 15 passed        # 唯一红 = 该 key 自己留的陈旧冻结副本（§E）
$ ... test_vc008_missing_fields_byte_identical
1 passed                   # feature-l3-readcap-injection 的冻结 VC-008：D-004 撤回后转绿
```

**该文件从"2 failed"回到"1 failed"的过程即是证据**：`test_existing_regression_files_untouched` 在 T-01b 未提交时红、提交后绿（PM 复验过两次），说明它是"相对 HEAD 的未提交改动检查"，不是语义回退。

---

## §B AC → 判据 → 证据（14/14）

| AC | 判据（spec） | 证据锚点 | 结论 |
|----|-------------|---------|------|
| AC-001 | `set` 把 `--` 后 argv 逐元素写入、补全 13 键、`--project` 必填且在 `--` 前、放错位置拒绝且文件不变 | A5 CLI 亲验（PM 独立 argparse 子进程 6 项）+ T-05 `[VERIFY] VC-001: argv_tokens=6 completed_keys=13 verbatim=True` / `misplaced_project=rejected file_unchanged=True` | ✅ |
| AC-002 | 规范化写入幂等（同参数第二次写字节相同） | T-05 `[VERIFY] VC-002: idempotent_bytes=True size=381` + T-07/T-07b `P3 py_to_ts_idempotent=31 ts_to_py_idempotent=31` | ✅ |
| AC-003 | 免重启拾取：同长度裸字节改写必须被读到；非 ASCII 原样字节 | T-01 `[VERIFY] VC-003: same_length_rewrite=9 cache_cleared=false`、`non_ascii_bytes=367 verbatim=true` | ✅ |
| AC-004 | `show` 打印有效值 + 逐字段 origin（`project`/`machine`/`default`） | T-05 `[VERIFY] VC-004: origins=['default','machine','project'] diagnostics=1`、`read_only=True mw_dir_created=False` | ✅ |
| AC-005 | `clear` 永不删除文件、只移除自身键、无键时零写 | T-05 `[VERIFY] VC-005: file_kept=True xkey_keys_removed=4 other_keys_intact=True` / `nothing_configured=no write mtime_unchanged=True` | ✅ |
| AC-006 | 两侧差分结论一致（同 payload 两侧同判） | T-07b `[VERIFY] P1: crosslang_verdict_match=53/53`（Python 侧 + TS 侧各跑一次，均 53/53） | ✅ |
| AC-007 | 机器层只覆盖 `xkey_verify_cmd`+`xkey_verify_cwd`，空值即未决定 | T-02b `[VERIFY] 空值即未决定 真值表: case=1..6`（6 例）、`越域越界告警: out_of_domain=2`、`材料化场景仍取机器层: project_keys=13 cmd_origin=machine`；T-02c 复验同一结论 | ✅ |
| AC-008 | doctor 段把"两层皆无命令"判为 issue 并给修复串；机器层满足时不告警 | T-03b `[VERIFY] 机器层满足命令 ⇒ 不告警`、`两层皆空 ⇒ issue + 修复串（文本含 mw autopilot verify set）`、`只读零足迹` | ✅ |
| AC-009 | dist 同步与防复发（四子判据 a/b/c/d） | **(a)** §A2 PM 亲验 `diff --exit-code` = 0；**(b)** T-08 `[VERIFY] A1b: fresh=ok stale=stale(auto=True) comment_only=stale unjudgeable=info`；**(c)** T-08 `[VERIFY] S1: order=['build','deploy'] build_fail deploy_called=False`；**(d)** T-08 `[VERIFY] dirty-guard: ... rc=1 built=False installed=False; --allow-dirty rc=0` | ✅ |
| AC-010 | 文档：UPDATE 指令矩阵加行 + README 两层对照 + 可机器判定部分逐字节 | §A4（PM 亲跑 4 用例：fenced block 417B 逐字节 + 12 语义锚点 + 矩阵行 + A1b/A2b 行）；人工评审项已 PM 逐段审阅 | ✅ |
| AC-011 | CLI 的 RMW 进锁；锁不可得 ⇒ 错误 + `return 1` 且目标字节不变 | T-05 `[VERIFY] VC-011: lock_busy=return 1 file_unchanged=True`；T-04 TS 侧锁用例（`autopilot-console.test.ts`，vitest 套件全绿） | ✅ |
| AC-012 | 默认零扰动：既有行为逐字不变、零新增失败 | §A1（`2 failed` 集合与基线完全相同；`e2e_l2 8 passed`；vitest 101 passed）；T-02b `[VERIFY] 只读零足迹`；T-03b 只读零足迹 4 用例；T-05 `read_only=True mw_dir_created=False` | ✅ |
| AC-013 | verify 根锚定：cwd 枚举 + 真值表含 `control≠partition≠parent` + 同族 5 锚点 + E2 形状 | T-09 `[VERIFY] VC-013/014: table_rows=30`（30 行参数化，三模式 × 四互异根 × 8 选择子 × 5 argv 形态）、`e2_shape=partition roots_distinct=true`、`e2_live cwd=H:\git\E2Feature parent=E:\UEMigrator`；T-06 `[VERIFY] VC-013: cwd真值=partition根(shard) / 非法选择子=invalid-config 且 verify 未执行` + 同族 5 锚点重锚 + 协调根仍为 control | ✅ |
| AC-014 | 占位符 list argv 逐元素展开、未定义 fail-closed、写入侧与消费侧一致、不照抄静默透传 | T-09 `[VERIFY] VC-014: control_token_verify_argv=accepted control_token_toolchain=missing-field`、`toolchain_unknown_passthrough=verbatim verify_argv_unknown=missing-field`、`toolchain_parity_cases=44 render_toolchain_unchanged=true`；T-03 的 `render_argv` 用例；T-05 `[VERIFY] VC-014: placeholder={bogus}/a{b}/{control}/tests refused=True` | ✅ |

---

## §C VC → 证据（16/16）

| VC | 判据摘要 | 证据 | 结论 |
|----|---------|------|------|
| VC-001 | CLI argv 逐元素、`--project` 位置约束 | T-05 `VC-001: argv_tokens=6 ... verbatim=True` + `misplaced_project=rejected file_unchanged=True`；PM 子进程 6 项亲验 | ✅ |
| VC-002 | 两侧同一 payload 同判 | T-07b `P1: crosslang_verdict_match=53/53`（两侧各 53） | ✅ |
| VC-003 | 免缓存拾取（同长度裸字节改写） | T-01 `VC-003: same_length_rewrite=9 cache_cleared=false` | ✅ |
| VC-004 | `show` origin 三态 | T-05 `VC-004: origins=['default','machine','project'] diagnostics=1` | ✅ |
| VC-005 | `clear` 保文件、只删自身键 | T-05 `VC-005: file_kept=True xkey_keys_removed=4 other_keys_intact=True` | ✅ |
| VC-006 | 13 键完整表 + 镜像 | T-01 `VC-016: default_config_keys=13 xkey_verify_cwd_default=''`；T-07b `P5: key_order_match=true defaults_match=true bool=3 list=1 str=1 int=8`（两侧） | ✅ |
| VC-007 | 空值即未决定（含材料化场景） | T-02b 6 例真值表 + `材料化场景仍取机器层`；T-02c 复验 | ✅ |
| VC-008 | doctor 判 issue + 修复串 | T-03b 三条 | ✅ |
| VC-009 | dist 重建后 diff 空 + A1b/A2b | §A2（PM `diff --exit-code`=0）+ §A3 | ✅ |
| VC-010 | 文档 fenced block 逐字节 | §A4 | ✅ |
| VC-011 | 锁不可得 ⇒ return 1 + 字节不变 | T-05 `VC-011: lock_busy=return 1 file_unchanged=True`；T-04 console 锁用例 | ✅ |
| VC-012 | 默认零扰动（既有输出语义不变） | §A1 全量 + T-11 `键存在时行为未变: enabled_true/enabled_false/paused_present` | ✅ |
| VC-013 | cwd 真值表（30 行）+ 非法选择子 fail-closed + E2 | T-09 30 行 + T-06 partition/非法选择子 | ✅ |
| VC-014 | 占位符展开/负例 + toolchain 未变 | T-09 `VC-014: ...` 4 行（含 44 个 parity case） | ✅ |
| VC-015 | 补默认键（F16）——**D-004 撤回后语义改写** | T-01b `VC-016: partial_keys=1 default_keys=13 effective_keys=13`、`VC-008: byte_identical=true`；T-02c `原始加载器 vs 完整视图: load_config_keys=1 effective_keys=13` | ✅（按撤回后判据） |
| VC-016 | 新键镜像（两侧逐字段） | T-07b `P5`（真跑两侧 registry 比对）；T-04 TS 侧 13 键镜像用例 | ✅ |

---

## §D Coverage Matrix F1–F17 → 证据

| F | 路径 | 证据 | 结论 |
|---|---|---|---|
| F1 | CLI set 写入 | AC-001/§B 行 | ✅ |
| F2 | 规范化幂等 | T-05 `idempotent_bytes` + P3 双向幂等 | ✅ |
| F3 | 免重启拾取 | T-01 `same_length_rewrite` | ✅ |
| F4 | show | T-05 `VC-004` | ✅ |
| F5 | clear | T-05 `VC-005` | ✅ |
| F6 | 两侧差分 | `P1 53/53` | ✅ |
| F7 | 机器层 | T-02b/T-02c/T-03b | ✅ |
| F8 | doctor | T-03b + T-03 `_doctor_issues` issue 注册 | ✅ |
| F9 | dist + 脏树护栏 | §A2/A3 + T-08 dirty-guard | ✅ |
| F10 | 文档 | §A4 | ✅ |
| F11 | 锁 | T-05 `VC-011` + T-04 | ✅ |
| F12 | 零扰动 | §A1 + 零足迹用例 | ✅ |
| F13 | cwd | T-09 30 行 + T-06 | ✅ |
| F14 | 占位符 | T-09 `VC-014` 行 | ✅ |
| F15 | 缓存判据 | T-01 `VC-003`（D-001 取消 stat 短路的净负收益结论） | ✅ |
| F16 | 补默认键（**已撤回**） | 见 VC-015 行：改为双视图（原始/解析） | ✅ |
| F17 | 新键镜像 | T-07b `P5` | ✅ |

---

## §E 既有红（不属本 key，未修）

| 红 | 成因（已核实） | 证据 |
|---|---|---|
| `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` | 该 key 自留的 `dispatch.py` **冻结副本**与其 git HEAD blob 的 sha256 不等（`219ed809…` vs `4e3e8876…` 后为 `06d84b52…`）——即该冻结副本已陈旧，任何后续 commit 都会让它红。基线 `b0a30bc12` 即红。 | PM 跑：`1 failed, 15 passed`；T-06 报告亦以 pristine HEAD 副本独立复现 |
| `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` | 读 live 外部项目 `H:\git\E2Feature` 的 fixture 漂移（`_mirror_recompute_reverse_key`）。 | 全量运行失败栈；基线即红 |

**另附本 key 曾出现、已消除的"伪红"**：`test_existing_regression_files_untouched`（相对 HEAD 的未提交改动检查，T-01b 提交后绿——PM 复验两次）。该文件当前 `1 failed`，仅上述第一条。

---

## §F 非空洞对照（每卡一条反证，证明新用例真咬住东西）

| 卡 | 反证手法 | 变红证据 |
|---|---|---|
| T-01 | 还原 `cached_load` 的 stat 短路 / 去掉 `ensure_ascii=False` | `assert 2 == 9`、`verbatim=false` |
| T-01b | `return {**default_config(), **data}` 复原 | `test_vc008_missing_fields_byte_identical` 红：`assert (8, 65536) == (None, None)` |
| T-02b | 忽略机器层 / 去掉空值即未决定 | PM 独立脚本 tt1/tt8 红；T-02b `out_of_domain` 用例红 |
| T-02c | 去掉 `values = {**defaults, **validated_raw}` | 4 条红（含 `KeyError: 'xkey_verify_timeout_s'`） |
| T-03 | doctor issue 降级为 suggestion | 3 failed |
| T-03b | 忽略机器层 | 2 failed |
| T-04 | 去掉 `readConfig` reviver | `4.0` 用例红 |
| T-05 | 去掉 dry-run 占位符拒绝 | 3 条占位拒绝红 |
| T-06 | verify cwd 改回 `project_root` | partition 用例 `verify_failed`（`assert 'verify_failed' == 'closed'`） |
| T-07 / T-07b | 断言原始加载器 13 键 / 用原始视图比对解析视图 | 两侧各 1 条红（`assert 1 == 13`；`expected [...] to deeply equal ['poll_interval_sec']`） |
| T-08 | S1 改回先 deploy 后 build / 去掉 A1b 判据 | 3 failed（`assert ['deploy'] == ['build']`）、2 failed（`assert 'ok' == 'stale'`） |
| T-09 | `workspace_root` 钉成 control 根 | 7 failed（partition/dual auto 行 + E2 两例） |
| T-10 | README 语义句改字 / help 块改字 | 各 1 failed（`['project flag required before separator']` / `fenced_block` 失配） |
| T-11 | `.get` 改回 `["enabled"]` | 5 failed，`KeyError: 'enabled' (mw.py:166)` |

提取本文件 §B–§E 的 `[VERIFY]` 行（机器提取，非手抄）：

```python
import pathlib
for p in sorted(pathlib.Path('workers').glob('*/output.md')):
    for l in p.read_text(encoding='utf-8', errors='replace').splitlines():
        if '[VERIFY]' in l:
            print(p.parent.name, '|', l.strip())
```
