# 证据：dist 重建（PM 直接执行，用户即时指令）

- key：`mw-autopilot-verify-cli` · 日期：2026-09-26 · 执行者：PM（本 key 的 spec 期之前/期间）
- 性质：**用户指令 #2 的交付证据**。本 key 的 AC-009 据此改写为"判据固化 + 可机器检测"，见下。
- 提交：`d52694cc4 fix(multi-workers,coding-agent): rebuild agent-team-loop dist artifacts for the xkey kind/guard`

## 1. 重建前的落后事实（机器判据：产物内字符串计数）

```
$ python -X utf8 -c "<scan bundles for markers>"
packages/multi-workers/dist/extensions/agent-team-loop.js  bytes=916378
  xkey-authorize 0   XKEY_GATE 0   xkey-gate-guard 0
packages/coding-agent/dist/**  (scan of .js/.mjs/.cjs)
  stale markers present: {}   # 连编译后的 guard 模块都不存在
```

即：两个 tracked 产物都落后于 `181a75332` 的 TS 源码（缺 `xkey-authorize` kind 与 `xkey-gate-guard`），新机器/新窗口加载产物拿不到新行为。

## 2. 执行的两条命令与结果

```
$ python -X utf8 packages/multi-workers/mw.py build
[mw build] built + self-check OK (activate)
[mw build] bundle: H:\git\Multi-Workers\packages\multi-workers\dist\extensions\agent-team-loop.js

$ cd packages/coding-agent; npm run build      # tsgo -p tsconfig.build.json && copy-assets
exit 0

$ python -X utf8 packages/multi-workers/mw.py build --install --no-dist
[mw build] built + self-check OK (activate)
[mw build] agentictask-update extension up-to-date: C:\Users\wenbozhou\.pi\agent\extensions\agentictask-update.ts
[mw build] installed globally: C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js
[mw build] dist rebuild skipped (--no-dist)
[mw build] Restart open pi windows to load the new bundle and dist.
```

顺序说明：先 `npm run build` 单独跑（失败可见），再用 `--install --no-dist` 只做全局安装，避免 `_deploy_bundle` 内部重复跑一遍 `_rebuild_pi_dist()`（`mw.py:3627`）。

## 3. 重建后的机器判据（全部实测）

| 判据 | 实测值 |
|---|---|
| bundle 含新 kind | `packages/multi-workers/dist/extensions/agent-team-loop.js` → `xkey-authorize` ×1 |
| bundle 含新 guard | 同上 → `XKEY_GATE` ×2 |
| 编译产物含新 kind | `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` → `xkey-authorize` |
| 编译产物含新 guard | `packages/coding-agent/dist/extensions/agent-team-loop/shared/xkey-gate-guard.js` → `XKEY_GATE`（新文件，d.ts/d.ts.map/js/js.map 四个） |
| 全局安装位与仓库产物一致 | `%USERPROFILE%\.pi\agent\extensions\agent-team-loop.js` 与仓库 bundle **字节相同**，`sha256 1be95bbae4d4c219`，923479 B |
| 构建确定性 | 连续两次构建 bundle sha 相同（`1be95bba…`） |
| 变更面 | 9 个 tracked 文件被改（8 个 coding-agent/dist + 1 bundle）+ 4 个新编译产物；**零源码文件改动** |

## 4. 残余（交付时如实声明）

1. **已打开的 pi 窗口仍在跑内存里的旧 bundle**——`mw build` 自己打印 "Restart open pi windows to load the new bundle and dist."。即：本机其它会话窗口（含 FM/E2）的 `xkey-gate-guard`（AC-004 的可观测拒绝）要到各自重启后才生效。这是**运行时状态**，不是仓库状态。
2. 本轮是"**执行了一次重建**"；"**未来再次落后能被自动发现**"才是可维护性关键 ⇒ 本 key 的 AC-009 收窄为：产出可机器复现的**陈旧检测判据**（并确认 `mw update-env`/`mw doctor` 是否已覆盖；待 RQ-3 定稿）。若 RQ-3 证明既有锚点已覆盖，则 AC-009 进一步收窄为"把该检测纳入文档/回归断言"，不重复造检测。
3. `mw build --install` 会跑 `npm run build`（tsgo 全量类型检查）：若并行会话存在未提交的 TS 类型错误会构建失败（本轮工作树 TS 侧干净，未遇到）。风险面与护栏待 RQ-3。
