# Development Rules

## AgenticTask Workflow

- Non-trivial implementation (new feature, multi-file change, or anything beyond a one-line fix) requires an active key first. MW PM follows AgenticTask (spec → claim); Codex PM creates an explicit `codex-lite` key through `codex_pm.py init` and records the goal, scope and numbered acceptance criteria in `codex_doc.md`. The trivial-fix `mini-spec.md` fast path remains available. This applies to mid-session requirements too. Check the authoritative `.agenticdoc/_index.parallel` row before the first write to code; `_index.md` is only the complete active-key projection.
- When Codex acts as PM, use the [Codex PM development and verification workflow](packages/multi-workers/docs/codex-pm.md). Lightweight keys use Codex lifecycle and acceptance interfaces; ordinary MW and existing complete-SDD keys retain AgenticTask gates. On resume, recover the explicitly named key and its in-flight work before dispatching more work.

## Conversational Style

- Keep answers short and concise
- No emojis in commits, issues, PR comments, or code
- No fluff or cheerful filler text (e.g., "Thanks @user" not "Thanks so much @user!")
- Technical prose only, be direct
- When the user asks a question, answer it first before making edits or running implementation commands.
- When responding to user feedback or an analysis, explicitly say whether you agree or disagree before saying what you changed.

## Code Quality

- Read files in full before wide-ranging changes, before editing files you have not fully inspected, and when asked to investigate or audit. Do not rely on search snippets for broad changes.
- No `any` unless absolutely necessary.
- Inline single-line helpers that have only one call site.
- Check node_modules for external API types; don't guess.
- **No inline imports** (`await import()`, `import("pkg").Type`, dynamic type imports). Top-level imports only.
- Never remove or downgrade code to fix type errors from outdated deps; upgrade the dep instead.
- Use only erasable TypeScript syntax (Node strip-only mode) in code checked by the root config (`packages/*/src`, `packages/*/test`, `packages/coding-agent/examples`): no parameter properties, `enum`, `namespace`/`module`, `import =`, `export =`, or other constructs needing JS emit. Use explicit fields with constructor assignments.
- Always ask before removing functionality or code that appears intentional.
- Do not preserve backward compatibility unless the user asks for it.
- Never hardcode key checks (e.g. `matchesKey(keyData, "ctrl+x")`). Add defaults to `DEFAULT_EDITOR_KEYBINDINGS` or `DEFAULT_APP_KEYBINDINGS` so they stay configurable.
- Never modify `packages/ai/src/models.generated.ts` directly; update `packages/ai/scripts/generate-models.ts` instead, then regenerate. Including the resulting `models.generated.ts` diff is always OK, even if regeneration includes unrelated upstream model metadata changes.

## Commands

- After code changes (not docs): `npm run check` (full output, no tail). Fix all errors, warnings, and infos before committing. Does not run tests.
- Never run `npm run build` or `npm test` unless requested by the user.
- Never run the full vitest suite directly: it includes e2e tests that activate when endpoint/auth env vars are present. For all non-e2e tests, run `./test.sh` from the repo root. Otherwise run specific tests from the package root: `node ../../node_modules/vitest/dist/cli.js --run test/specific.test.ts`.
- Windows dev machines: `packages/agent` and `packages/coding-agent` suites carry a known baseline of 89 environment failures (13 + 76; Windows shell/path/watch semantics, classified 2026-09-10). The same tests fail on upstream pi on Windows too, so treat them as environment noise, not regressions; compare new breakage against this baseline instead of chasing it.
- If you create or modify a test file, run it and iterate on test or implementation until it passes.
- For `packages/coding-agent/test/suite/`, use `test/suite/harness.ts` + the faux provider. No real provider APIs, keys, or paid tokens.
- Put issue-specific regressions under `packages/coding-agent/test/suite/regressions/` named `<issue-number>-<short-slug>.test.ts`.
- For ad-hoc scripts, `write` them to a temp file (e.g. `/tmp`), run, edit if needed, remove when done. Don't embed multi-line scripts in `bash` commands.
- Never commit unless the user asks.

## Multi-Workers 运行版本

- 项目运行默认使用用户级全局 `mw` 和 `pi`。只有用户明确授权时，才用工作树、旧包或其他版本覆盖项目的运行版本，或切换全局默认包。
- 仓库快捷入口应转发至全局入口。在 pi 窗口用 `/mw version` 核对全局默认、当前窗口和已注册窗口的实际运行路径。

## Dependency and Install Security

- Treat npm dep and lockfile changes as reviewed code. Direct external deps stay pinned to exact versions.
- When updating `undici`, you MUST read its changelog/release notes for the target version and evaluate whether any changes may affect functionality before applying the update.
- Hydrate/update locally with `npm install --ignore-scripts`; clean/CI-style with `npm ci --ignore-scripts`. Don't run lifecycle scripts unless the user asks.
- If dep metadata changes, refresh `package-lock.json` with `npm install --package-lock-only --ignore-scripts`.
- If `packages/coding-agent/npm-shrinkwrap.json` needs regen, run `node scripts/generate-coding-agent-shrinkwrap.mjs` (verify with `--check` or `npm run check`). New deps with lifecycle scripts require review and an explicit allowlist entry in that script; never add one silently.
- Pre-commit blocks lockfile commits unless `PI_ALLOW_LOCKFILE_CHANGE=1`. Don't bypass unless the user wants the lockfile change committed.

## Git

Multiple pi sessions may be running in this cwd at the same time, each modifying different files. Git operations that touch unstaged, staged, or untracked files outside your own changes will stomp on other sessions' work. Follow these rules:

Committing:

- Only commit files YOU changed in THIS session.
- Stage explicit paths (`git add <path1> <path2>`); never `git add -A` / `git add .`.
- Before committing, run `git status` and verify you are only staging your files.
- `packages/ai/src/models.generated.ts` may always be included alongside your files.
- Message format: `{feat,fix,docs}[(ai,tui,agent,coding-agent)]: <commit message> (optionally multiple lines)`. Message is informative and concise.

Never run (destroys other agents' work or bypasses checks):

- `git reset --hard`, `git checkout .`, `git clean -fd`, `git stash`, `git add -A`, `git add .`, `git commit --no-verify`.

If rebase conflicts occur:

- Resolve conflicts only in files you modified.
- If a conflict is in a file you did not modify, abort and ask the user.
- Never force push.

## Issues and PRs

See `CONTRIBUTING.md` for the contributor gate (auto-close workflows, `lgtm`/`lgtmi`, quality bar).

When reviewing PRs:

- Do not run `gh pr checkout`, `git switch`, or otherwise move the worktree to the PR branch unless the user explicitly asks.
- Use `gh pr view`, `gh pr diff`, `gh api`, and local `git show`/`git diff` against fetched refs to inspect PR metadata, commits, and patches without changing branches.
- If you need PR file contents, fetch/read them into temporary files or use `git show <ref>:<path>` without switching branches.

When creating issues:

- Add `pkg:*` labels for affected packages (`pkg:agent`, `pkg:ai`, `pkg:coding-agent`, `pkg:tui`); use all that apply.

When posting issue/PR comments:

- Write the comment to a temp file and post with `gh issue/pr comment --body-file` (never multi-line markdown via `--body`).
- Keep comments concise, technical, in the user's tone.
- End every AI-posted comment with the AI-generated disclaimer line specified by the originating prompt (e.g. `This comment is AI-generated by `/wr``).

When closing issues via commit:

- Include `fixes #<number>` or `closes #<number>` in the message so merging auto-closes the issue. For multiple issues, repeat the keyword per issue (`closes #1, closes #2`); a shared keyword (`closes #1, #2`) only closes the first.

## Testing pi Interactive Mode with tmux

Run the TUI in a controlled terminal (from the repo root):

```bash
tmux new-session -d -s pi-test -x 80 -y 24
tmux send-keys -t pi-test "./pi-test.sh" Enter
sleep 3 && tmux capture-pane -t pi-test -p     # capture after startup
tmux send-keys -t pi-test "your prompt here" Enter
tmux send-keys -t pi-test Escape               # special keys (also C-o for ctrl+o, etc.)
tmux kill-session -t pi-test
```

## Changelog

Location: `packages/*/CHANGELOG.md` (one per package).

Sections under `## [Unreleased]`: `### Breaking Changes` (API changes requiring migration), `### Added`, `### Changed`, `### Fixed`, `### Removed`.

Rules:

- All new entries go under `## [Unreleased]`. Read the full section first and append to existing subsections; never duplicate them.
- Released version sections (e.g. `## [0.12.2]`) are immutable; never modify them.

Attribution:

- Internal (from issues): `Fixed foo bar ([#123](https://github.com/earendil-works/pi-mono/issues/123))`
- External contributions: `Added feature X ([#456](https://github.com/earendil-works/pi-mono/pull/456) by [@username](https://github.com/username))`

## Releasing

**Lockstep versioning**: all packages share one version; every release updates all together. `patch` = fixes + additions, `minor` = breaking changes. No major releases.

1. **Update CHANGELOGs**: ask the user whether they ran the `/cl` prompt on the latest commit on `main`. If not, they must run `/cl` first to audit and update each package's `[Unreleased]` section before releasing.

2. **Local smoke test**: build an unpublished release and smoke test from outside the repo (so it can't resolve workspace files):
   ```bash
   npm run release:local -- --out /tmp/pi-local-release --force
   cd /tmp

   # Node package install smoke tests
   /tmp/pi-local-release/node/pi --help
   /tmp/pi-local-release/node/pi --version
   /tmp/pi-local-release/node/pi --list-models
   /tmp/pi-local-release/node/pi -p "Say exactly: ok"
   /tmp/pi-local-release/node/pi

   # Bun binary smoke tests
   /tmp/pi-local-release/bun/pi --help
   /tmp/pi-local-release/bun/pi --version
   /tmp/pi-local-release/bun/pi --list-models
   /tmp/pi-local-release/bun/pi -p "Say exactly: ok"
   /tmp/pi-local-release/bun/pi
   ```
   Verify both Node and Bun startup, model/account listing, interactive startup, and at least one real prompt with the intended default provider. The bare commands `/tmp/pi-local-release/node/pi` and `/tmp/pi-local-release/bun/pi` start interactive mode; run each in tmux, submit a prompt, and wait for the model reply before considering the interactive smoke test passed. Failures are release blockers unless the user explicitly accepts the risk.

3. **Run the release script**:
   ```bash
   PI_ALLOW_LOCKFILE_CHANGE=1 npm_config_min_release_age=0 npm run release:patch    # fixes + additions
   PI_ALLOW_LOCKFILE_CHANGE=1 npm_config_min_release_age=0 npm run release:minor    # breaking changes
   ```
   Use `npm_config_min_release_age=0` only for the release command. The repo's normal npm age gate can otherwise block the release lockfile refresh when the current workspace package version was published recently. Review any lockfile or shrinkwrap diffs the release creates before push.

   The release script bumps all package versions, updates changelogs, regenerates release artifacts, runs `npm run check`, commits `Release vX.Y.Z`, tags `vX.Y.Z`, adds fresh `## [Unreleased]` changelog sections, commits `Add [Unreleased] section for next cycle`, then pushes `main` and the tag. Do not rerun the release script after a tag was pushed.

4. **CI publishes npm packages**: pushing the `vX.Y.Z` tag triggers `.github/workflows/build-binaries.yml`. The `publish-npm` job uses npm trusted publishing through GitHub Actions OIDC with environment `npm-publish`; no local `npm publish`, `npm whoami`, OTP, or WebAuthn flow is required.

5. **If CI publish fails**: inspect the failed `publish-npm` job. The publish helper is idempotent and skips package versions already present on npm, so rerun the tag workflow after fixing CI or transient npm issues. Do not rerun `npm run release:patch` or `npm run release:minor` for the same version.

## User Override

If the user's instructions conflict with any rule in this document, ask for explicit confirmation before overriding. Only then execute their instructions.

## Multi-Workers 协作约定

直接收到用户需求的 Agent 默认担任 PM。收到 MW 派发的 `task.md` 时，以 Worker 身份执行卡上的工作项，沿用卡上的 key。

先阅读项目已有的 `CLAUDE.md` 或 `CLAUDE.MD`，以及控制工作区的 `.agenticdoc/goal.md`。MW PM 使用已安装的 `agentic-task` skill；Codex PM 按下面的轻量入口工作。讨论和只读调查可以直接进行，实施前必须有已认领的 key。

### Key 和任务卡规模

- 一个 key 只交付一个能在目标环境走通的用户竖切。Spec 控制在一页，最多 5 条 AC 和 10 张卡。超过任一数量时，PM 在 spec 阶段拆 key 后再推进。
- `research` 和 `review` 卡片的 `timeout:` 至少 30 分钟。
- 每张卡写明可观察结果和验收命令的预期退出码，并至少经真实入口调用一次；脚本或测试能触达就不拉真机，重型真机留证只在竖切收口做一次。中间 `coding` 卡验编译通过、最小正例和必要的破坏性负例（中途取消、目标失效、底层不可用时不得报就绪）。PM 先复核实际 diff，改动涉及异步、取消、绑定或失败态路径时另派独立评审。防伪走宿主工具，非 `spec_goal` 产品不自写证据一致性脚本。卡片的 `write_face` 覆盖正文点名的每个编辑目标。

### 每个 key 选择一个 PM

| PM 与流程记录 | 计划、执行和验收方式 |
| --- | --- |
| `pm-state.md` 中 `- PM mode: mw` | 完整 AgenticTask：`spec → design → plan → tasks → execute → verify → done`，沿用原阶段、质量和签收门禁。 |
| `codex_doc.md` 中 `- Workflow: codex-lite` | Codex PM 轻量流程：主记录保存目标、范围、编号验收标准、决定、进度和接续信息；`achieved.md` 保存实际交付与遗留。 |

已有完整 SDD key 继续原流程；`PM mode: codex` 本身不把已有任务转换为轻量任务。PM 交接需记录原方式、新方式、在途任务和接手人，再按目标流程完成认领。

### Codex PM 开始、恢复和结案

- 使用 `packages/multi-workers/codex_pm.py init --project <控制工作区> --key <key>` 建立轻量 key，填写生成的 `codex_doc.md`。任务只需要一份主记录；实施前明确目标、范围、`- AC-001: ...` 验收标准和接续须知。
- `init` 从 `SPEC` 开始；`advance --phase EXECUTE` 通过主记录校验后进入实施，`advance --phase VERIFY` 进入验收。所有命令显式指定 `--key`；多个 `ClaimId: codex` 不能用于猜测当前任务，也不用于区分窗口。同一个 key 由一个 PM 推进。
- `_index.parallel` 保留真实的 `SPEC / EXECUTE / VERIFY / DONE`、active/idle 和认领信息；活动轻量认领统一为 `codex`。`_index.md` 的 `active_keys` 是共享锁内生成的完整投影，不是授权依据。轻量状态由 Codex 接口同步维护，不手改索引或机器字段。
- 轻量 key 的 `pm-state.md` 仅保留认领接口和 `Phase: init`。AgenticTask 原脚本保持原语义；它的“尚无 SDD 阶段可审计”不是轻量任务验收通过。
- 接续时先运行 `status --project <控制工作区> --key <key>`，核对主记录、索引、在途 Worker 和证据。`release` 只释放认领并保留阶段；`claim` 恢复未结案的轻量 key，保持已有交付记录。已完成或完整 SDD key 不自动转换。
- Codex 自己执行的验证用 `check --ac AC-001 -- <程序及参数>` 保存命令和结果；按实际需要区分自验与另一执行者复核。证据绑定目标工作区、源码快照以及主记录的目标、范围和验收标准；同一工作区的其它源码改动也会使旧证据失效，最后一批编辑后重新验证。主记录引用证据路径，不重复复制日志。
- 完成全部验收后写 `achieved.md`，记录系统行为变化、验收证据和遗留去向，再运行 `done --summary <交付摘要>`。结案接口检查证据、在途任务和归属，写入回溯记录，把索引设为 `DONE / idle` 并释放 ClaimId。存在未验证项时保留任务状态和下一步。

### Codex PM 与 MW Worker 交接

- 只有转派工作才在同一 key 的 `tasks/` 建卡。卡片须写明目标及对应 AC、剩余交付、依赖、已有证据、目标工作区、可改文件和验收命令，使 Worker 可以独立开工。
- `dispatch --card <卡名> --claim-id codex` 使用 Codex 专属的轻量派发适配。任务卡、工作区、模型和写入范围等共享检查继续生效；普通 MW 派发仍检查原 SDD 文档。
- Worker 按卡片实施和验证，在本次运行目录用 `output.md` 交付改动、验证结果和遗留。Worker 无需创建 PM 过程文档；派出单项工作后，当前 Codex PM 继续负责整个 key。
- PM 阅读实际改动和报告，再用派发时的验收命令执行 `verify --card <卡名> --claim-id codex -- <程序及参数>`，将结果记回主记录。失败时明确修复项和已有证据，再派新卡。

项目的构建、测试、代码风格和提交授权沿用已有约定。

<!-- mw:agent-collaboration -->
<!-- mw:agent-collaboration-version: 3 -->
