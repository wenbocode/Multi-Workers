# verify-closure（T-16 收口全量回归 + 基线对照）

- key: `mw-gate-verdict-hardening` · card: `tasks/T-16-docs-dist.md`（PM 改写为 docs-closure，不重建 dist）
- worker: `mwg-t16-docs-closure`
- 代码基线：HEAD `776b82d7fa3af2a36a5a46717be6d5feac8ba0a0`（`chore: ignore the local .tmp scratch dir`）
- 对照基线：`evidence/runs/verify-baseline.md`
- 取数时刻：2026-10-10 19:07–19:11（本机时钟）
- 口径：**运行时是旧副本（全局 bundle / 常驻 launcher 为旧代码），本文件只以本卡自己跑出的输出为准**

---

## 1. `npm run check`（全量，非 tail）— exit 0

命令（仓根）：

```
npm run check
```

原始输出：

```
> pi-monorepo@0.0.3 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1110 files in 589ms. No fixes applied.

> pi-monorepo@0.0.3 check:pinned-deps
> node scripts/check-pinned-deps.mjs


> pi-monorepo@0.0.3 check:ts-imports
> node scripts/check-ts-relative-imports.mjs


> pi-monorepo@0.0.3 check:shrinkwrap
> node scripts/generate-coding-agent-shrinkwrap.mjs --check

packages/coding-agent/npm-shrinkwrap.json is up to date.

> pi-monorepo@0.0.3 check:install-lock:coding-agent
> node scripts/generate-coding-agent-install-lock.mjs --check

packages/coding-agent/install-lock is up to date.

> pi-monorepo@0.0.3 check:browser-smoke
> node scripts/check-browser-smoke.mjs

EXITCODE=0
```

要点：
- biome：`Checked 1110 files in 589ms. No fixes applied.` ⇒ 未改写任何文件（含其他会话的在飞改动）。
- `tsgo --noEmit` 静默通过（无输出）。
- `check:browser-smoke` 静默通过。
- `npm run check` 退出码 **0**。

---

## 2. Python 全量：`python -X utf8 -m pytest -q -p no:randomly`

命令（`packages/multi-workers`）：

```
python -X utf8 -m pytest -q -p no:randomly
```

末 7 行（原文）：

```
  See https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings for more info.
    warnings.warn(pytest.PytestUnhandledThreadExceptionWarning(msg))

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound - As...
FAILED test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below
2 failed, 1523 passed, 10 deselected, 162 warnings in 192.74s (0:03:12)
```

两条红的原始断言（`=== FAILURES ===` 摘录）：

```
________________________ test_baseline_left_end_bound _________________________
>       assert frozen == git_blob
E       AssertionError: assert '219ed8090210...e9bd66bc8610a' == '6be60fe5ae42...0769643c91469'
E         - 6be60fe5ae42646732a1ace23a704e95f9b588339c05fec51e70769643c91469
E         + 219ed8090210630f5f2136b0f544900bc955309c60936ac351de9bd66bc8610a
test_autopilot_readcap_injection.py:907: AssertionError

_________________ test_true_below_without_resume_stays_below __________________
>       live_persisted, live_last, live_stale = _mirror_recompute_reverse_key(root)
...
root = WindowsPath('H:/git/E2Feature')
test_autopilot_verdict_freshness.py:329
```

> 注：`test_true_below_without_resume_stays_below` 依赖仓库真实 `.agenticdoc` 语料 fixture（`H:/git/E2Feature`），与基线记录同因；完整 traceback 尾部是 `assert last_round in report_matches` → `3 in [2]`（基线表同款）。`UnicodeDecodeError` 行是 Windows cp936 采集噪声，不是失败。

---

## 3. TS suite 全集（本 key 触达面，一次跑完）

命令（`packages/coding-agent`）：

```
node ../../node_modules/vitest/dist/cli.js --run \
  test/suite/worker-store.test.ts test/suite/run-store.test.ts \
  test/suite/worker-dispatch-guard.test.ts test/suite/worker-run-identity.test.ts \
  test/suite/worker-crosskey-readonly.test.ts test/suite/autopilot-monitor.test.ts \
  test/suite/autopilot-console.test.ts test/suite/autopilot-gate-presentation.test.ts \
  test/suite/autopilot-event-parity.test.ts test/suite/autopilot-config-sync.test.ts \
  test/suite/autopilot-config-parity.test.ts test/extensions/agent-team-loop.test.ts \
  test/extensions/agent-team-loop-pm-state-sync.test.ts
```

末 5 行（原文）：

```
[VERIFY] VC-023: rearmed=true panel_present=true
...........

 Test Files  13 passed (13)
      Tests  340 passed (340)
   Start at  19:07:13
   Duration  7.00s (transform 3.10s, setup 0ms, import 6.31s, tests 11.80s, environment 1ms)
```

关键 `[VERIFY]` 行（原文摘录，证明各面真在跑）：`P1: crosslang_verdict_match=73/73`、`P2: canonical_sha_match=38 sha256_equal=true`、`P3: py_to_ts_idempotent=38 ts_to_py_idempotent=38`、`P4: corpus_sha256=1e27f593… cases=73`、`P5: key_order_match=true defaults_match=true … int=14`、`P6: partial_single_key=35 raw_view_partial=true effective_view_20=true fields_covered=20`、`VC-010/VC-011/VC-012/VC-020/VC-021/VC-022/VC-023` 全绿。

---

## 4. 基线对照表（逐项，新增红 = 0）

| # | 基线 `verify-baseline.md` 红集合 | 收口实测 | 判定 |
|---|---|---|---|
| 1 | `test_autopilot_readcap_injection.py::test_baseline_left_end_bound`（`assert frozen == git_blob` → `219ed809…` vs `6be60fe5…`，冻结锚点漂移） | 同名同断言，同 hash 对（`219ed809…` vs `6be60fe5…`） | 既有红，未扩散 |
| 2 | `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`（`assert last_round in report_matches` → `3 in [2]`，真实语料 fixture） | 同名，同真实语料 fixture（`H:/git/E2Feature`） | 既有红，未扩散 |

**新增红 = 0**（收口红集合 ⊂ 基线红集合，且逐项同名）。

口径差异（非回归）：
- 基线只跑了 `34 × test_autopilot_*.py + test_doctor_gates.py`（`2 failed, 655 passed, 8 deselected, 64 warnings in 76.45s`）；本卡按卡要求跑**全量** `pytest -q -p no:randomly`（`2 failed, 1523 passed, 10 deselected, 162 warnings`）。**failed 集合逐字一致，passed/deselected/warnings 因选择面扩大而变大，不是新增红。**
- TS 基线只跑了 `worker-store.test.ts`（1 file / 6 tests）；本卡跑本 key 触达的 13 file / 340 tests 全绿。

---

## 5. `./test.sh` 环境限制（如实记录）

`./test.sh` **本机不可运行**：

```
where.exe bash
→ C:\Windows\System32\bash.exe
→ C:\Users\wenbozhou\AppData\Local\Microsoft\WindowsApps\bash.exe

bash -c "echo hello-from-bash"
→ 适用于 Linux 的 Windows 子系统没有已安装的分发版。
  可通过运行 “wsl.exe --list --online” 和 “wsl.exe --install <Distro>” 进行安装。
  错误代码: Wsl/Service/... 
→ exit=1

wsl -l -v
→ 同样报 “没有已安装的分发版”，rc=0xFFFFFFFF
```

`bash.exe` 指向 WSL，而本机无已安装发行版 ⇒ `test.sh`（bash 脚本）无法执行。

**替代口径**（AGENTS.md：非 e2e 适用）：
- Python 侧：`python -X utf8 -m pytest -q -p no:randomly` 全量（见 §2）。
- TS 侧：§3 的 13 个 suite 文件全集。
- 不跑全量 vitest（含 e2e），与卡约束一致。

---

## 6. `git diff --stat`（卡内列出的改写面）

```
$ git diff --stat -- packages/multi-workers/CHANGELOG.md packages/coding-agent/CHANGELOG.md
 packages/coding-agent/CHANGELOG.md  | 13 +++++++++++++
 packages/multi-workers/CHANGELOG.md | 15 +++++++++++++++
 2 files changed, 28 insertions(+)
```

附（README 必要同步）：`packages/multi-workers/README.md | 10 ++++++++++`，`git diff --numstat` 对三文件均为 `<n>  0`（**全增不删**）。

---

## 7. 结论

- `npm run check` exit 0，biome 无改写。
- Python 全量 `2 failed, 1523 passed`，红集合与基线逐项一致，新增红 = 0。
- TS 本 key 触达 suite 全集 `13 passed / 340 tests passed`。
- `./test.sh` 因 WSL 无发行版不可运行，已用上述等价口径替代并记录。
