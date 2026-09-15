# Evidence Run: 011-regression-baseline

- Date: 2026-09-11T22:30:00+08:00
- Task: 011-regression-baseline（S4）
- 范围：本 key 全部改动（S1–S4：multi-workers + coding-agent agent-team-loop + 测试）相对既有基线的全量回归对照

## 1. npm run check（全文，exit=0，0 error / 0 warning / 0 info）

```
> pi-monorepo@0.83.0 check
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke

Checked 1046 files in 600ms. No fixes applied.
> check:pinned-deps      （无输出=通过）
> check:ts-imports       （无输出=通过）
> check:shrinkwrap       → packages/coding-agent/npm-shrinkwrap.json is up to date.
> check:install-lock     → packages/coding-agent/install-lock is up to date.
> check:browser-smoke    （无输出=通过）
exit=0
```

- 首轮发现 2 条 biome info（`lint/style/useTemplate`，均本 key 引入：read-scope.ts:181 与 autopilot-read-scope.test.ts:386 的字符串拼接）——已改为模板字面量，复跑 check 全 0；read-scope 套件复验 24/24

## 2. ./test.sh（Git Bash，全量非 e2e，隔离环境；预期 exit 1——基线失败存在）

逐 workspace 结果（源：tmp/test-sh-output.log，UTF-16 全文留档）：

| workspace | 结果 | 失败文件 |
|---|---|---|
| agent | 2 failed / 217 passed (219) | nodejs-env 1、tools 1（均基线 B 类） |
| ai | 1 failed / 837 passed / 825 skipped (1663) | timi-models 1（见 §4 口径外） |
| （小包，绿色） | 6 files / 31 passed | — |
| coding-agent | 61 failed / 2040 passed / 48 skipped (2157) | 23 文件，见 §3 |
| evals | 1 failed / 22 passed (23) | vitest-evals/artifacts 1（口径外） |
| （绿色） | 3 files / 146 passed | — |
| server | 30 failed / 19 passed (49) | conformance 14、sessions 11、server 1、unix 4——全 Unix socket 类（Windows 结构性，unix.test.ts 字面命名） |
| tui | 7 files / 68 passed | — |

## 3. Windows 89 例基线对照（可比口径：真实 HOME + 其余隔离，复刻 2026-09-10 归因方法）

test.sh 的隔离 HOME 引入 3 个基线外伪影（path-utils `~` 展开 1、interactive-mode-status home 相对路径 2——均为 HOME 语义类）；用「保留真实 HOME、清凭据、PI_NO_LOCAL_LLM=1」复跑 agent+coding-agent 得可比数：

**agent：2 败（基线 13）**——nodejs-env 1 + tools 1，均为基线 B 类文件，无基线外文件。剩余 11 个基线失败本次通过（超时类 flaky，归因报告已注明单次 ±2~3 正常）。

**coding-agent：53 败 / 19 文件（基线 76）**，逐文件对照：

| 文件 | 基线 | 本次 | 判定 |
|---|---|---|---|
| config | 7 | 7 | = |
| tools | 9 | 7 | ⊂ |
| external-editor | 3 | 3 | = |
| sdk-session-manager | 3 | 3 | = |
| interactive-mode-suspend | 2 | 2 | = |
| trust-selector | 3 | 3 | = |
| footer-width / resource-loader / agent-session-dynamic-tools / 2791-fswatch / 3592 | 各 1 | 各 1 | = |
| agent-session-concurrent | 1 | 1 | = |
| 5109-exclude-tools | 2 | 2 | = |
| model-registry | 7 | 2 | ⊂ |
| package-command-paths | 3 | 2 | ⊂ |
| extensions-runner | 8 | 4 | ⊂ |
| agent-session-runtime | 6 | 7 | +1（A' 超时类 flaky；两轮跑 6↔7 波动） |
| 3302-find-path-glob | 1 | 3 | +2（B 类路径 glob；两轮跑 1↔3 波动） |
| resolve-config-value / package-manager / auth-storage / trust-manager / auto-compaction-queue | 3+2+1+1+3 | 0 | 本次全过（flaky 通过侧） |
| **基线外文件** | — | **0** | 无新增失败文件 |

**本 key 改动面全绿**：agent-team-loop 全部测试（含新增 dual-root/cross-drive/profile-injection/deny 用例）、multi-workers 全量 402——两轮跑均零失败。

## 4. 口径外观察项（不在 89 基线范围、不在本 key 改动面，仅记录）

- **ai timi-models 1 败（确定性）**：`MODELS.timi` 18 个模型 vs 测试快照 `EXPECTED_MODELS` 15——catalog 与测试漂移，`packages/ai` 工作树干净、漂移已在提交历史中（8806e2be8 及此前 catalog 提交），非本 key、非并发未提交改动；属 ai-baseline-repair（2026-09-10 清零）之后的重新漂移，需独立处理
- **evals vitest-evals/artifacts 1 败**：本 key 未触碰 evals
- **server 30 败**：Unix socket 语义在 Windows 上结构性失败（conformance/sessions/server/unix），CI 只跑 ubuntu 永不可见，与 agent/coding-agent 的 B 类同性质

## 5. VC 判定

```
[VERIFY] VC-002: check-clean=true new-failures=0
```

- check-clean=true：exit 0、0/0/0（修掉本 key 引入的 2 条 info 后）
- new-failures=0：基线口径（agent+coding-agent）内无基线外失败文件；两处计数超额（runtime +1、3302 +2）均为基线内文件的 flaky 波动（两轮跑互有消长、均非本 key 改动面、agent-team-loop 全绿佐证）
