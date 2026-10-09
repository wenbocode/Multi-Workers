# Handover: mw-vision-role（状态 DONE，剩余项交接）

- **key**: `mw-vision-role` · phase **DONE**（`_index.parallel` 已同步）
- **commits**: `7a864c1c7`（feat：代码 + 测试，19 文件）· `5c1149f1b`（docs(agentic)：spec/design/plan/19 卡/证据/QG）· `fd30eb8be`（fix：签名冻结断言与提交顺序无关）· `mini-spec.md`（快车道记录）
- **收口文档**: `achieved.md`（系统行为变化 9 条 + 遗留 8 条）· `evidence/quality-gate-report-20260926T1850Z.md`（46 问：44 充分 / 3 验证欠债 / 0 无证据）· `evidence/reviews/qg-review-mw-vision-role-20260926.md`（独立 QG：`PASS-WITH-NITS`、`blockers=0`）
- **主证据**: `evidence/runs/verify-mw-vision-role-20260926.md`（T-14 正文 + T-19 附录 A，含全部原始输出）

## 已落地（现在就能用）

```bash
mw model set vision timi/deepseek-v4-flash-vision-exp   # 配置角色（本仓库尚未配）
mw model show                                            # 每行带 images=yes|no|unknown
mw doctor                                                # 能力不匹配 => suggestion（退出码 0），仅对 vision 角色告警
```

派发面：`type: vision`（含图片引用会自动 `images: yes`）；模型不可读图 ⇒ **派发期拒绝**（零副作用）；未显式指定 `model:` 且角色默认不可读图 ⇒ **auto-route 只换模型**（`type:` 不变）；worker 运行期另有 `[IMAGE-CAP]` 兜底。

**扩展 bundle 已重建并全局安装**（952,453 B，`IMAGE-CAP`/`auto-route` 标记已在），但**运行中的 pi 窗口仍是旧代码** —— 需重启窗口（见 R1）。

---

## 剩余项（R1 → R6，按优先级）

### R1 活窗口复验（唯一有实质验收意义的剩余项）

重启任意 pi 窗口后确认两件事（这两条是 QG 的 ⚠️-2/⚠️-3）：

```bash
# ① 活窗口 doctor 渲染带能力列
/mw doctor          # 期望：派发模型: role=value images=<yes|no|unknown>; ...
# ② 活窗口的 worker 兜底真触发（零 token：exit(1) 发生在首轮前）
#    用 images: yes 的 task.md + 纯文本模型真跑一次 worker（需经 mw launcher 或在窗口内派发）
```

**已完成的等价证据**（提交后、装 bundle 后实测，2026-10-09 03:08）：

```
pi-via-tsx rc = 1
[IMAGE-CAP] model=deepseek-v4.1-flash provider=timi task=l2t declared=images:yes
trace.log: [ERROR] 2026-10-09T03:08:29.187Z [IMAGE-CAP] model=deepseek-v4.1-flash provider=timi task=l2t declared=images:yes
output.md: Task refused (image capability).
```

这次是**走安装后的全局 bundle**（无 `-ne`）跑的，即比 T-14 的源 builtin 证据更贴近活窗口。剩余只是「重启后窗口进程真的加载了新 bundle」。`worker.log` 缺文件属已登记 NIT N-3：它由 mw launcher 捕获 stdout 产生，直调只有 stdout。

### R2 提交 dist 产物（等并发 key 的 src 干净后）

`packages/multi-workers/dist/extensions/agent-team-loop.js` 是**受跟踪产物**，本次 `--allow-dirty` 构建后处于 modified 且有意**未提交**（它同时嵌入了并发 key `mw-autopilot-slot-capacity` 的未提交 src：`autopilot/{console,monitor,status-model}.ts`、`shared/{worker-store,xkey-gate-guard}.ts`、`worker-mode.ts` 的 watchdog 段、`core/tools/bash.ts`）。

```bash
# 待那些 src 提交后（干净树）重跑并提交 dist
cd packages/multi-workers && python mw.py build --install
cd ../.. && git status --short packages/multi-workers/dist
```

### R3 `npm run check` 字面（QG ⚠️-1）

`npm run check` 第一步是 `biome check --write .`，会改写并发会话的在飞文件 ⇒ 本次只逐条跑了只读组件（全仓 biome `--error-on-warnings`、`tsgo --noEmit`、pinned-deps、ts-imports、shrinkwrap、install-lock、browser-smoke）全绿。建议在干净树（或 CI）跑一次字面命令，或把写模式与只读门禁拆分。

### R4 CHANGELOG 条目（本 key 未加）

`packages/{coding-agent,multi-workers}/CHANGELOG.md` 的 `[Unreleased]` 需要 `vision` 角色的 `### Added` 条目；仓库流程要求发布前跑 `/cl` 审计，建议由 `/cl` 统一补（本次未动这两个文件——它们正被并发 key 修改）。

### R5 可选加固（已被独立 QG 记为 NIT，不阻塞）

- N-2：`planDispatchFrontmatter` 对非法 `images` 值（`maybe`/大小写变体）静默按"未声明"处理（用户可达路径均已拒绝）⇒ 可改为 fail-loud，或把"未知值 == 未声明"写进注释契约。
- N-6：VC-014 的 `/worker` USAGE 与 `PARALLEL_PROTOCOL` 断言是子串级，可升级为 token 集比较（`type` 描述已是严格集合）。
- N-5：`vision` 未配置时 doctor 不显示该角色行（"未配置 ⇒ skip"）；若要求未配角色也出行需另开需求。
- N-4/N-7：`evidence-requirement.md` 与 readcap 套件的 VC 同号歧义、测试入口清单过期（文档口径）。

### R6 既有基线红（与 key 无关，未修）

- `test_autopilot_readcap_injection.py::test_baseline_left_end_bound`（E-04）：冻结副本 sha ≠ 当前 `dispatch.py`。在 **`fd30eb8be` 的干净检出上也重现** ⇒ 确为既有红。
- `test_autopilot_readcap_injection.py::test_existing_regression_files_untouched`（E-06）：主工作区里含并发 key 改 `test_autopilot_config.py`；同一条在**干净检出上也红**，因为本机 `core.autocrlf=true` 使 live 字节（CRLF）与 `git show HEAD:`（LF）不等 ⇒ 该断言在 Windows 上恒红，除非改为按规范化后内容比对。

### 已知耦合（已在本 key 内处置）

- `test_autopilot_readcap_injection.py::test_render_task_md_signature_shape`：曾在 `7a864c1c7` 的**干净检出**上红（精确列表里写了并发 key 的 `worker_timeout_min`）——已在 `fd30eb8be` 改为「已知有序前缀相等 + 集合包含于已知集」，**两条提交顺序下都绿**（已分别在主工作区与 detached 干净检出上复验）。
- `test_autopilot_dispatch.py` 的 `_verify(..., flush=True)` 一行**未纳入**本 key 提交（无法归属，留给并发 key）。
- `test_existing_regression_files_untouched` 的红有**两个成因**：并发 key 改了 `test_autopilot_config.py`，以及本机 `core.autocrlf=true` 下 live 字节（CRLF）与 `git show HEAD:`（LF）不等——后者在**干净检出上也复现**。

---

## 新窗口怎么接手（两条路径）

### 路径 A（推荐）：开一个 follow-up key

剩余项是**新的小改动**（R2/R3/R4/R5），`mw-vision-role` 已 DONE —— 不要在 DONE key 上继续写代码（框架语义：done 门禁后新工作属于新 key）。新窗口：

```bash
# 1) 建 key 并进入（新窗口内）
/agentic mw-vision-role-hardening

# 2) 更小的改动可直接走 mini-spec 快车道
#    写 .agenticdoc/<key>/mini-spec.md（<24h）即可解除实现门禁
```

把本文件 `R1..R6` 直接抄进新 key 的 spec/tasks 即可（每条都带命令与验收面）。

### 路径 B：只读接手本 key（用于复验/查看）

无需 claim，直接读：

```bash
cat .agenticdoc/mw-vision-role/handover.md        # 本文件
cat .agenticdoc/mw-vision-role/achieved.md        # 行为变化 + 遗留
cat .agenticdoc/mw-vision-role/evidence/quality-gate-report-20260926T1850Z.md   # 3 项欠债
```

若要在本 key 上**写代码**（会被实现门禁拦），需先在窗口内 `/agentic mw-vision-role`（claim 后 `_index.parallel` 行会重新变为 active）。

### 接手时先跑这三条（确认环境没漂）

```bash
cd packages/multi-workers && python -m pytest test_dispatch_models.py -q -s   # 期望 53 passed，含 [VERIFY] VC-001/003/010/013/015
cd ../../packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-vision-gate.test.ts   # 期望 9 passed，含 VC-006/007/008
# 仓库根
npx tsgo --noEmit                                                             # 期望 rc=0、零输出
```

三条全绿说明本 key 的提交在干净树上自洽。**干净检出实测**（对 `fd30eb8be` 建 detached worktree）：`test_dispatch_models.py + test_autopilot_readcap_injection.py` = **68 passed / 2 failed**，两红均为已登记基线（`test_baseline_left_end_bound` 冻结 sha 早于 HEAD；`test_existing_regression_files_untouched` 的 CRLF 成分）。在 detached worktree 里跑 `test_serve_doctor.py` 会有 3 例 `TestUpdateIndexClaim` 报 `FileNotFoundError`（`.agents/skills/**` 未被跟踪），属 worktree 环境伪影，回主工作区跑即正常。
