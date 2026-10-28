# T-W13 — doctor 可见性两项：AC-015 注册表损坏可见 + AC-016 激活自检

- key: mw-worktree-junction-guard
- 日期: 2026-10-14
- 角色: coding worker（写面 = `mw_common.py` doctor 装配/文本面、`worktree_doctor.py` 富化、`test_worktree_doctor.py` 追加、`test_doctor_activation.py` 新建）

## 结论

两项都落成，且都有反向对照：

1. **AC-015**：`worktree_links.registry_error`（新增顶层镜像字段，同时保留 `scanned.registry_error`）现在被 `_doctor_issues` 消费为 issue（含错误摘要 + 注册表路径，翻转 rc），`format_doctor_text` 在 `registry_error` 非空时**即使 `count==0`** 也打印 `worktree_links: REGISTRY-ERROR <path>: <error>`。反向对照（同一夹具、注册表健康/不存在/合法空表）⇒ 零新增行、零新增 issue、rc=0，与改动前一致。
2. **AC-016**：`doctor_report` 新增 `report["activation"]` 段（装配面），对两份运行面 bundle 判定是否含能力标记 `reparse-point`：文件缺失、标记缺失、读取/编码异常都报出（异常走 fail-open-to-verdict，不 raise，`has_marker=None`，文本如实写 `UNVERIFIABLE (...)`，绝不伪装成“已激活”），修复提示给可照抄的 `mw build --install`。serve 层面**复用**既有 `serve code: STALE CODE` 判据（`mw.py cmd_doctor`），不新增进程探针、不重复输出。反向对照：两份含标记的假 bundle ⇒ 零新增行、零新增 issue、rc 从 1 回到 0（同一项目、无代码改动，证明“部署后自动转绿”）。
3. **真实仓只读运行**：`python mw.py doctor --project H:/git/Multi-Workers` 现在报出 **2 条**新 `guard-not-deployed` issue（两份 bundle 均为 1,115,336 B 且 `reparse-point` 命中 0），rc=1。这是设计意图（当前 bundle 确实没有 G1）；**未执行任何部署**（未跑 `mw build` / `mw build --install` / `mw start|stop`），也**未放宽判据**。

## 证据

### 1. 能力标记的选择与双向实测

候选（卡里建议的两个）在 G1 源码里的坐标：`shared/worktree-junction-guard.ts`（`basis: "reparse-point"` 是 `scanVerdict`/`reparsePointVerdict` 的固定词表值，design §3.2；`mw worktree rm` 是 `reparsePointVerdict` 的处方文本）。全仓 grep 显示 `reparse-point` 只出现在该模块（1 处注释 + 1 处字符串字面量），`mw worktree rm` 出现在该模块的处方模板串。

**修复前（当前两份部署 bundle）**，只读 grep：

```
H:\git\Multi-Workers\packages\multi-workers\dist\extensions\agent-team-loop.js: bytes=1115336 reparse-point=0 mw worktree rm=0 worktree=0
C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js:                bytes=1115336 reparse-point=0 mw worktree rm=0 worktree=0
```

**部署后必然出现**的实测（不落部署产物）：用 `build-extension.sh` 的同一组 esbuild 参数把 `packages/coding-agent/src/extensions/agent-team-loop/index.ts` 打成 `%TEMP%\w13-activation-probe.js`（非 dist、非全局，未执行 `mw build`），再 grep：

```
out: C:\Users\WENBOZ~1\AppData\Local\Temp\w13-activation-probe.js bytes: 1136103
reparse-point: 1
mw worktree rm: 1
worktree: 25
```

**选择 `reparse-point`**，理由：① 它是 G1 判定函数的 `basis` 固定词表值，只有判定代码进入 bundle 才会出现——`mw worktree rm` 是面向人的处方文案，后续卡（W-10 已改过处方文本）可以在不删能力的前提下改词；② 它在本 key 的扩展源码里唯一（只有 `worktree-junction-guard.ts` 含此串），而 `mw worktree rm` 是“命令文档”性质、未来别的模式文案也可能带上；③ 双向实测证明“修复前必然缺失（两份 bundle 均 0）、部署后必然出现（新 esbuild 1 次命中）”。

### 2. 五类用例的实测输出

`packages/multi-workers/test_doctor_activation.py`（10 例，全 `%TEMP%` 夹具）覆盖：

| 用例 | 断言（实测通过） |
|---|---|
| 标记齐全 ⇒ 静默 | `_activation_scan` `ok=True`、`missing=[]`；`doctor_report` 零 activation issue、`summary.issues==[]`、`healthy=True`、文本无 `activation:` |
| 标记缺失 ⇒ issue（含路径 + `mw build --install`） | issue = `guard-not-deployed: <path> - capability marker 'reparse-point' absent; ... run 'mw build --install' (AC-016)`；文本行 `activation: MARKER-ABSENT 'reparse-point' <path> - run 'mw build --install'` |
| bundle 文件缺失 ⇒ issue | issue 含 `<path>` + `bundle file missing` + `mw build --install`；文本行 `activation: MISSING <path> - run 'mw build --install'` |
| 读取异常 ⇒ 不 raise 且文本如实 | 目录冒充文件（`IsADirectoryError`）与非法 UTF-8（`UnicodeDecodeError`）两种夹具：`_activation_scan` 不抛，`has_marker=None`、`error` 非空；issue 含 `unverifiable (...)`，文本 `activation: UNVERIFIABLE ...`，且**不出现** `MARKER-ABSENT`（不伪装已激活） |
| 两份齐全时 rc 不变（反向对照） | 同一项目：两份含标记夹具 ⇒ `mw.cmd_doctor` rc=0；删掉一个标记 ⇒ rc=1 且文本出现 `guard-not-deployed:`/`activation:`；恢复标记 ⇒ rc 回到 0（无代码改动，即“部署后自动转绿”的验收方式） |
| scope gate | 无 `packages/coding-agent/src/extensions/agent-team-loop` 的项目 ⇒ `applicable=False`、零 issue、零 `activation:` 行（保证冻结的 `test_doctor_gates.py` / `test_serve_doctor.py` 的 healthy 断言不被污染） |

`test_worktree_doctor.py` 追加 `test_corrupt_registry_visible_healthy_registry_silent`（AC-015）：

```
healthy(不存在/合法空表): registry_error=None, 无 registry issue, 文本无 REGISTRY-ERROR, rc=0
corrupt({ not json):      count=0, registry_error 非空,
                          issue = worktree-registry-error: cannot read registry <repo>\.mw\worktree-registry.json: ...
                                   - the junction registry at <path> could not be read, so leftover-link
                                   detection is degraded (fail-closed); fix or remove the file (AC-015)
                          文本 = worktree_links: REGISTRY-ERROR <path>: cannot read registry ...
                          rc=1（与 healthy 的 rc=0 构成 rc 变化）
合法空表恢复:              registry_error=None, rc 回到 0, 文本无 REGISTRY-ERROR
```

### 3. 真实仓 doctor 前后对照与 rc（只读）

改动后 `python mw.py doctor --project H:/git/Multi-Workers`：

```
activation: MARKER-ABSENT 'reparse-point' H:\git\Multi-Workers\packages\multi-workers\dist\extensions\agent-team-loop.js - run 'mw build --install'
activation: MARKER-ABSENT 'reparse-point' C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js - run 'mw build --install'
summary: ISSUES: guard-not-deployed: ...dist\extensions\agent-team-loop.js - capability marker 'reparse-point' absent; ...
                  guard-not-deployed: ...\.pi\agent\extensions\agent-team-loop.js - capability marker 'reparse-point' absent; ...
                  STALE CODE (content changed): tree=H:\git\Multi-Workers\packages\multi-workers schema=1/1 serve_pid=49540 ...
serve code: STALE CODE (content changed): ...
rc: 1
```

计数与前后对照（用同一 `doctor_report`，仅把 activation 段临时置为 `applicable=False` 复现改动前）：

| 口径 | 改动前 | 改动后 |
|---|---|---|
| `doctor_report` issues | 0 | **2**（新增 `guard-not-deployed` ×2） |
| `mw doctor` issues（含 `cmd_doctor` 追加的 serve 判据） | 1（STALE CODE） | **3**（2 新 + 1 既有 STALE CODE） |
| rc | 1 | 1 |

rc 之所以未变化：改动前 `mw doctor` 已因既有 serve `STALE CODE` 判据为红。新增 issue 数为 **2**。`worktree_links`：注册表不存在 ⇒ 无 AC-015 新行（真实仓 `.mw/worktree-registry.json` 不存在，`registry_error=None`）。全流程只读，未修改真树任何文件。

### 4. pytest 输出

```
$ python -m pytest test_doctor_activation.py -q
..........                                                               [100%]
10 passed in 4.37s

$ python -m pytest test_worktree_cmd.py test_worktree_doctor.py test_worktree_e2e.py test_tree_watch.py test_tree_watch_doctor.py test_doctor_gates.py test_serve_doctor.py -q
........................................................................ [ 44%]
........................................................................ [ 88%]
..................                                                       [100%]
162 passed in 68.74s            # 基线 161（本 key 前序卡累积，非卡里写的 138）+ 本卡新增 1

$ python -m pytest <上述 7 文件> test_doctor_activation.py -q
172 passed in 77.40s

$ python -c "import mw_common; print('cycle-ok')"
cycle-ok
```

额外（防止 doctor 面波及其他冻结测试）：`test_doctor_autopilot.py test_mwds_t08_doctor_blocked.py test_mw_bootstrap.py test_update_env.py test_common.py -q` ⇒ **160 passed**。

### 5. 夹具路径与清理

- 夹具全部由 pytest `tmp_path` 创建于 `%TEMP%\pytest-of-wenbozhou\pytest-<n>\...`；activation 用例只写普通文件（`.js` / 非法 UTF-8 字节 / 目录冒充文件）与 `proj/.mw/mw.pid`（写当前 pytest PID 以移除“service not running”噪声），**不含任何 reparse point**。
- `test_worktree_doctor.py` 的注册表用例复用既有 `repo`/`fixture` 夹具（`%TEMP%\wjg-w03-*`），只新建/改写 `.mw/worktree-registry.json`，无 junction。
- 真树 `node_modules` 下的 junction 未被触碰；未执行 `git worktree add|remove|prune`、`rm`、`npm install`/`npm ci`、`mw build*`、`mw start|stop`。临时 esbuild 产物 `%TEMP%\w13-activation-probe.js` 与两个临时脚本已删除。

## 改动历史

`file:line`（改动后行号）before → after：

- `packages/multi-workers/worktree_doctor.py`
  - `build_section` 返回体（`:303-311`）：before 无 `registry_error` 键 → after 新增 `"registry_error": reg_error,`（`:309`，顶层镜像 `scanned.registry_error`，AC-015 装配面便利键）。函数 docstring 同步（`:280-283`）。域判定/扫描逻辑未动。
- `packages/multi-workers/mw_common.py`
  - 新增块（`:2735-2832`，插在 `_doctor_bundle` 与 `_source_desc` 之间）：`ACTIVATION_MARKER = "reparse-point"`（`:2745`）、`_EXT_SRC_REL`、`_activation_bundle_paths`（`:2757`）、`_activation_scan`（`:2775`）、`_doctor_activation`（`:2818`）。before：不存在。
  - `_doctor_issues`（stale_entries 循环之后、既有 tree-watch 块之前）：after 新增 `registry_error` 消费（`:3871-3884`，issue `worktree-registry-error:`）+ activation 消费（`:3885-3908`，issue `guard-not-deployed:`）。`mw_common.py:3818` 附近的 tree-watch 块与既有 `worktree_links` 消费块语义未动。
  - `doctor_report`：after 新增 `report["activation"] = _doctor_activation(project_dir)`（`:4029`，紧接 `worktree_links` 段装配之后）。
  - `format_doctor_text`：worktree_links 段（`:4166-4174`，`count` 门控不变）之后新增 `REGISTRY-ERROR` 行（`:4175-4182`，`registry_error` 门控，与 `count` 无关）+ `activation:` 行（`:4183-4198`，仅对缺标记/缺失/不可读的 bundle）。
- `packages/multi-workers/test_worktree_doctor.py`
  - 追加 `_make_service_running`（`:477-481`）与 `test_corrupt_registry_visible_healthy_registry_silent`（`:484-538`）。before：文件止于 `:473`（`test_this_repo_reports_no_worktree_links` 末尾）。
- `packages/multi-workers/test_doctor_activation.py`：新建，243 行，10 个用例。

`git status --porcelain`（本人改动清单；其余 `M` 为其它并行 worker/会话的在途改动）：

```
 M packages/multi-workers/mw_common.py
?? packages/multi-workers/worktree_doctor.py
?? packages/multi-workers/test_worktree_doctor.py
?? packages/multi-workers/test_doctor_activation.py
```

（`worktree_doctor.py` / `test_worktree_doctor.py` 在本 key 内仍未提交，故显示 `??`。）

## 残留与未验证

1. **activation 自检的适用范围是“拥有扩展源码的检出”**，不是任意项目。判据 = 项目内存在 `packages/coding-agent/src/extensions/agent-team-loop`（`_activation_bundle_paths`）。原因：冻结的 `test_doctor_gates.py` / `test_serve_doctor.py` 在 `%TEMP%` 夹具上断言 `summary.issues == []` 且 `healthy is True`（后者还把 `PI_CODING_AGENT_DIR` 指向夹具，从而“全局 bundle 缺失”），一个项目无关的检查会把它们打红，而那不是部署缺陷。**未验证**：为任意（非本仓）项目做项目无关的 G1 激活体检；这需要在 spec/design 层为那批测试定义豁免机制后再做。
2. serve 侧只**复用**既有 `serve code: STALE CODE` 判据，未新增进程探针；如果将来 `STALE CODE` 的语义被改（例如不再覆盖 G4 采样代码），AC-016 ② 需重新确认。
3. “部署后自动转绿”已用含标记的**假 bundle 夹具**证明（rc 1→0），但**没有**跑真实 `mw build --install`（卡明令禁止，PM 落地后复跑）。真实转绿（两份部署 bundle 各含 ≥1 个 `reparse-point`）未在本卡验证。
4. 真实仓 rc 前后都是 1（既有 serve `STALE CODE`），所以“新增 issue 使 rc 由 0→1”只在夹具里被证；真实仓只能证明新增了 2 条 issue，rc 无法单独归因。
5. 读取 1.1 MB × 2 的 bundle 给 `mw doctor` 增加约 2 次全文件读；未做耗时基准（`build_section` 的 ~2 ms 量级仍在毫秒级，未观测到 doctor 变慢）。

## 上下文来源

- 卡/任务：`.agenticdoc/mw-worktree-junction-guard/workers/wjg-w13-doctor-activation/task.md`、`tasks/T-W13-doctor-visibility-activation.md`
- 规格/决策：`.agenticdoc/mw-worktree-junction-guard/spec.md`（AC-015/AC-016、§7 D-14/D-15）、`.agenticdoc/goal.md`（INV-4）
- 独立审计：`.agenticdoc/mw-worktree-junction-guard/evidence/negative-space-audit-20261013.md`（N-01/N-04）
- 代码：`packages/multi-workers/worktree_doctor.py`（`_registry_domain` / `build_section`）、`mw_common.py`（`_doctor_bundle` / `_doctor_issues` / `doctor_report` / `format_doctor_text`）、`mw.py`（`cmd_doctor`、`serve_code_verdict`）、`packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts`（`basis: "reparse-point"`）
- 测试范式：`test_worktree_doctor.py`、`test_doctor_gates.py`、`test_tree_watch_doctor.py`、`test_serve_doctor.py`

TESTS: 172/172 | 标记: reparse-point | 真实仓: 2 rc=1 | CHECK: n/a(python)
