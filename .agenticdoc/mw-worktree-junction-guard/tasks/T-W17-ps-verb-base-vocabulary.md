# T-W17 — D-19：删除面动词与基准面词表按 PowerShell 补全

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**破坏性 git/文件命令；禁 `npm install|ci`；夹具只能在 `%TEMP%` 内

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` INV-1（含 reparse point 的 worktree 没有任何执行通道能连目标一起删）。护栏必须覆盖它实际运行的那个 shell。
- **来源**: `evidence/delta-adversarial-audit-20261013.md` §1b（对抗性审计的**最强反例**）：`mw_common.ensure_pi_shell_path`（`packages/multi-workers/mw_common.py:1434` 附近）把 pi 的 shell 钉在 **PowerShell**，因此 `! ri -r -fo <link>/`、`! del -Recurse <link>/*`、`! rd …` 与 `Remove-Item -Recurse …` 同能力，却因头词白名单只有 `rm`/`remove-item` 而**放行**；`cd /d <dir>`、`pushd <dir>`、`sl <dir>` 同属已声明的「基准跟踪」能力内的白名单缺项（`readLocationTarget` 只认 `cd`/`set-location`，且把 cmd 的 `/d` 当成目标路径）。`spec.md` §7 **D-19** 已定稿为「只补词表、不动判定谓词」。
- **既有实现坐标（先读全文确认，勿凭本卡行号）**: `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts` 的 `readLocationTarget`（约 `:517-525`，当前判据 `head !== "cd" && head !== "set-location"`）、`parseDeleteInvocation`（约 `:549-554`，当前判据 `head !== "rm" && head !== "remove-item"`）、`decideDeletePenetration`（约 `:332`）、`notRemove`（约 `:695`）、处方文本（约 `:712`）、`expandToken`（约 `:609`）。

## 要求

1. **基准面词表补全**（`readLocationTarget`）：头词扩为 `cd` | `set-location` | `pushd` | `sl` | `chdir`；取目标值时跳过 cmd 风格 `/d`、`/D` 与 PS `-Path`/`-LiteralPath` 的**旗标位**（`-Path <dir>` 与 `-Path=<dir>` 两种写法都要能取到值），跳过所有 `-` 前缀词（现有行为）；无目标（如裸 `pushd` —— PS 语义是回 home）⇒ 视为 `unresolved` fail-closed（与 `cd $UNSET` 同处置），**不得**静默沿用旧 cwd。
2. **删除面动词补全**（`parseDeleteInvocation`）：头词扩为 `rm` | `remove-item` | `ri` | `del` | `erase` | `rd` | `rmdir`。**只动词表变化**：递归旗标 + 尾分隔符/通配 + `notRemove` 的谓词与处方文本一律不动。
3. **不误拦（反向对照，必须逐条断言）**：
   - `del <file.txt>`、`ri <file.txt>`、`erase <file.txt>`、`rd tempdir`（无尾分隔符/无通配）、`rmdir /S <dir>`（D-4 已声明不穿透）⇒ **放行**；
   - 干净基准命令 `sl <dir>`、`chdir <dir>`、`pushd <dir>` 单独出现（其后无删除动作）⇒ 放行；
   - 既有处方命令（`mw worktree rm "<wt>"`、`cmd /c rmdir "<link>"`）⇒ 仍放行（注意 `cmd /c rmdir "<link>"` 里的 `rmdir` 出现在 `cmd /c` 之后，**不得**因为新词表而改判——按段首词判定）。
4. **必须拦（每词至少一条）**：`ri -r -fo "<link>/"`、`del -Recurse "<link>/*"`、`erase -Recurse "<link>/"`、`rd -Recurse "<link>/*"`、`rmdir -Recurse "<link>/"` ⇒ `block=true`，且命中 `delete-penetration` 面、给第二套文本（非 worktree 目标）；基准漂移形态 `pushd "<含链 wt 的父目录>"; git worktree remove --force wt`、`sl <dir>; git worktree remove --force wt`、`cd /d <dir>; git worktree remove --force wt` ⇒ 拦（`cd /d` 修复前会误解析 `/d` 为目标 ⇒ 这正是要修的点）。
5. **验收**：`node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts test/suite/worktree-junction-guard-coverage.test.ts` ⇒ decide **25 + 新增**、coverage **13**（不得回归）；`npm run check` 零 error/warning/info；vitest 全量输出不 tail。

## 交付格式

- 代码变更（见写面）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W17-ps-verb-base-vocabulary-20261013.md`：`## 结论`、`## 证据`（每个新词的拦/放实测断言输出、`cd /d` 修复前后对照、既有处方命令未改判的断言、vitest 与 check 输出、夹具路径与清理）、`## 改动历史`、`## 残留与未验证`、`## 上下文来源`。
- 末行 `TESTS: <decide>/<coverage> | 新词: 5 动词 + 3 基准 | 反向对照: <n> | CHECK: <clean|N errors>`。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/worktree-junction-guard.ts`
- `packages/coding-agent/test/suite/worktree-junction-guard-decide.test.ts`
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W17-ps-verb-base-vocabulary-20261013.md`（新建）

## 写入禁止面

- `test/suite/worktree-junction-guard-coverage.test.ts`（W-14 的案例面，冻结）、`test/suite/harness.ts`、其它 `test/suite/**`、`index.ts`
- `packages/multi-workers/**`（同轮 W-16 在改）、`scripts/**`
- **禁部署**：不跑 `mw build`/`mw build --install`/`mw start|stop`；真树禁 `git worktree add|remove|prune`、禁 `rm`、禁碰真树 `node_modules` 链；夹具链目标必须在夹具内；清理 = `cmd /c rmdir <link>`（无 `/S`）→ `rmdir /S /Q <root>`

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts test/suite/worktree-junction-guard-coverage.test.ts
cd ../..
npm run check
```

## 改动历史

报告内逐条列 `file:line` before→after + `git status --porcelain` 的本人改动清单。
