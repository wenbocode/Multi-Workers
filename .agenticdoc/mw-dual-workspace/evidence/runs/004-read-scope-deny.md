# Evidence Run: 004-read-scope-deny

- Date: 2026-09-11T18:25:00+08:00
- Task: 004-read-scope-deny（S2）
- Deliverables:
  - `worker/read-scope.ts`: `matchedDenyGlob()`（双基准 + 尾部 `/**` 目录自匹配）、`ReadScopeRule` 增 `deny-glob`、`ReadScopeConfig.scope: string[] | null`（null=deny-only 模式）+ `denyGlobs`、`checkReadScopeCall` deny 优先（scope/caps 仅在 scope 模式生效）、`readScopeConfigFromMeta` 支持 deny-only
  - `worker/worker-mode.ts`: TaskMeta 增 `denyGlobs`、parseTaskMd 解析 `deny_globs:` 块列表（引号剥离——dispatch 侧 `**` 开头项须加引号，YAML alias 标记规避）
  - `test/suite/autopilot-read-scope.test.ts`: +4 用例（双基准/裸目录/优先级/解析）+ 全链 wiring 用例

## 测试命令与结果

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-read-scope.test.ts
  Tests 24 passed (24)   # 20 既有 + 4 新增（含 wiring）

# 关联套件（parseTaskMd/worker-mode 改动影响面）
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop*.test.ts test/suite/autopilot-protocol.test.ts
  Tests 139 passed (139)

npm run check → exit 0
```

## [VERIFY] 行

```
[VERIFY] VC-011: deny-block-rate=100 trace-has-reason=true (blocks=6, trace-lines=6)
[VERIFY] VC-012: precedence=deny
```

- VC-011 全链断言：两种 deny 形态（`**/*.uasset` 绝对+相对基准 / `DerivedDataCache/**` 相对基准）× read/ls/find/grep → 6 次调用 100% block，trace.log 6 行 `rule=deny-glob`，reason 含匹配到的 glob 原文；scope 内非 deny 路径照常放行
- VC-012 纯函数断言：同路径命中 allow scope + deny glob → rule=`deny-glob`（非 `scope`——allow 不兜底）

## 设计修正（执行期，已回写 design.md D-003 [EXEC 注记]）

纯 minimatch 语义下 `DerivedDataCache/**` 不匹配目录本身——`ls`/`find` 以裸目录为路径可列内容，L1 防火墙漏洞。测试首跑抓出（vEscape/`find DerivedDataCache` 未拦截），修正为：尾部 `/**` 的 glob 额外匹配剥掉 `/**` 后的相对路径（`DerivedDataCache/**` 同时命中 `DerivedDataCache` 与其内容）。

## 语义说明

- deny-only 模式：task.md 只有 `deny_globs` 无 `read_scope` → scope=null（无 containment、无 caps，仅 deny 防火墙）——deny 不因缺 scope 静默失效（D-004 L1）；两类字段都无 → 零拦截（AC-012 红线不变，既有 legacy 用例复验通过）
