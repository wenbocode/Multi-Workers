# T-04 TS 镜像与写侧（新键 + 导出常量 + reviver 判整数 + console 进锁）

- AC: AC-006, AC-011, AC-012 · VC: VC-006, VC-011, VC-015 · 波次: 1
- 写面：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`、同目录 `console.ts` + 对应 TS 测试（路径以实际为准，先确认再改）

## 契约（plan.md §2.1/§2.2）

1. **新键镜像**：`xkey_verify_cwd: ""` 加入 interface / `DEFAULT_CONFIG` / 类型登记 / `readConfig` 的 `merged` / `saveConfig` 的 `ordered`；头注释 `12 fields` 改 13。
2. **导出三个私有常量**（`status-model.ts:112/115/118`：BOOL/LIST/INT 登记表），供 T-07 的镜像判据使用。
3. **整数字面量判据（D-007 Direction B）**：`readConfig` 的 `JSON.parse` 加 reviver，用第三参 `context.source` 对 int 字段拒绝"原始字面量非纯整数"（正则 `/^-?(?:0|[1-9]\d*)$/`），错误信息含字段名与字面量。TS 5.9 lib 无该重载 ⇒ **窄类型 + 一次 cast**，不得引入 `any`。
4. **console 进锁**：`console.ts` 的四个 RMW handler（enable/disable/pause/resume，`:287/:339`）改为锁内 read→modify→write；新增 `configLockPath(root)` 与 `saveConfigLocked(...)`（复用 `shared/file-lock.ts:12 acquireLock`），锁参数 `retries=6, base_delay=0.02` **可注入**（测试用 `lockOpts`）；锁不可得 ⇒ 明确报错、不写。
5. 只读路径（status/monitor）**不加锁、不建目录**。

## 验证

- `node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts test/suite/autopilot-monitor.test.ts`（包根）全绿；新增用例：12 种字面量（`4`/`4.0`/`1e2`/`4.5`/`-0.0`/超范围等）的接受/拒绝、锁被占用 ⇒ 拒绝且字节不变、释放后可重试、两侧锁路径同名。
- 非空洞对照：去掉 reviver ⇒ `4.0` 用例必须红。
- `[VERIFY]` 行：reviver 判据、锁拒绝、13 键镜像。
