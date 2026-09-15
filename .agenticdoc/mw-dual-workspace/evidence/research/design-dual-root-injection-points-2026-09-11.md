# Research: 双根注入点与 deny 执行层级（design）

## 决策问题

支撑 design 决策：D-A1（worker cwd）、D-B1（双根解析所有权）、D-B2（deny globs 执行层级）、D-B3（profile 注入通道）、D-A5（glob 匹配依赖）。

## 调研方法与出处

2026-09-11 直接阅读源码与依赖清单（file:line 均为当日核对）：

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:225-231, 477-483`
- `packages/coding-agent/src/extensions/agent-team-loop/index.ts:20`
- `packages/multi-workers/launcher.py:125, 153, 522-524`
- `packages/coding-agent/src/core/extensions/types.ts:899-911, 1246`
- `packages/coding-agent/src/core/tools/find.ts:126-134, 163-261`
- `packages/coding-agent/src/core/tools/grep.ts:27-28, 131-132, 172-215`
- `packages/coding-agent/package.json`（依赖清单）

## 发现

1. **worker 控制根无需新 env**：worker-mode.ts:229-231 从 `PI_WORKER_TASK`（绝对路径，launcher.py:125/153 注入）dirname 推导 agenticdocRoot / trueAgenticdocRoot。双工作区下该 env 指向控制工作区任务目录，推导自动落在控制根。**launcher 只需把 spawn cwd 从 project_dir 改为 target.game（launcher.py:522-524），控制根传递链零改动。**
2. **PM 侧与 mw serve 零改动**：PM 扩展 cwd=控制工作区（pm-orchestrator.ts:588 process.cwd()），mw serve --project=控制工作区——双工作区语义下两者本就锚控制根，不变。
3. **tool_call 事件 input 可变但加字段无效**：types.ts:901-902（"event.input is mutable... No re-validation is performed after mutation"）——但 grep/find 内部只读取 schema 已知字段（grep.ts:27-28：pattern/path/glob/limit/ignoreCase），突变追加 exclude 类字段不会被消费。
4. **registerTool 存在**（types.ts:1246）：扩展可注册影子 find/grep 包装工具（含 exclude 参数），可行但重复实现核心工具，复杂度高。
5. **find（fd）遍历语义**：`--glob --color=never --hidden`，git repo 外加 `--no-require-git`（find.ts:230-234）——fd 在非 git 目录仍尊重 .gitignore；工具不暴露 exclude 参数。输出截断 DEFAULT_LIMIT 结果 / DEFAULT_MAX_BYTES（find.ts:126）。
6. **grep（rg）遍历语义**：`--json --line-number --hidden`，尊重 .gitignore/.ignore；`glob` 输入参数是正向单串过滤（grep.ts:27），无负向排除。输出截断同 find（grep.ts:131）。
7. **遍历洪泛天然有界**：rg/fd 输出截断 + read-scope file/byte caps（D-106）双层兜底；P4 工作区无 .gitignore 时（ProjectH 实测无，Engine 有）遍历不排除 DDC，但每次调用被截断限流。
8. **deny glob 匹配零新增依赖**：minimatch@10.2.5 已是 coding-agent 直接依赖（package.json），支持 `**` 语义。
9. **read-scope 拦截器在扩展层**（worker-mode.ts:477-483，read/ls/find/grep 四类）——deny 扩展的落点即此拦截器 + read-scope.ts。

## 结论 → 决策映射

- 发现 1/2 → D-A1/D-B1：cwd=Game 根 + PI_WORKER_TASK 推导控制根；launcher 唯一注入点；PM/serve 不动。改动面远小于 spec §4 风险 3 的预估。
- 发现 3/4/5/6/7 → D-B2：deny 三层——L1 调用级强制拦截（tool_call path 命中 deny globs → block + trace，满足 AC-006 字面）；L2 遍历有界（.gitignore 尊重 + 输出截断 + caps 兜底，不满足 AC 字面但限流）；L3 提示级（profile ignore 注入）。否决：改核心工具加 exclude（GC-1）、registerTool 影子工具（发现 4，复杂度 > 收益）。
- 发现 8 → D-A5：deny_globs 用 minimatch，`*.uasset` / `DerivedDataCache/**` 均为标准语义。
- 发现 1 → D-B3：profile 注入走 task.md 渲染（task.md 自包含原则与 PI_WORKER_TASK 设计一致，launcher.py:221/266 注释）；注入要点 + 控制工作区绝对路径引用，dispatch 生成 read_scope 时自动附加控制根（worker 读 profile 全文的授权）。

## 补充核查（2026-09-11，design 证据复查）

- PyYAML 可用性实测：`python -c "import yaml; print(yaml.__version__)"` → 6.0.3（2026-09-11）→ 支撑 D-010；mw 代码零 yaml import（rg 验证），为新隐式依赖。
- minimatch Windows 语义实测（node v24.19.0，repo node_modules，2026-09-11，临时脚本测后删除）：
  - `F:\ProjectH\Content\X.uasset` vs `**/*.uasset` = **true**（反斜杠绝对路径可命中，无需预归一分隔符）
  - `F:/ProjectH/DerivedDataCache/a/b` vs `DerivedDataCache/**` = **false**（裸目录形态不匹配绝对路径）
  - `DerivedDataCache/a/b` vs `DerivedDataCache/**` = **true**（game 根相对路径命中）
  - `F:/ProjectH/DerivedDataCache/a/b` vs `**/DerivedDataCache/**` = **true**
  → 支撑 D-003 双基准匹配定义：AC-006 的两种 deny 形态必须经「绝对 + game 根相对」双匹配才都生效。
- parity 适配量口径：T-17（test_autopilot_l0.py 锁 TOOL_ALLOWLISTS ↔ REGISTRY）为**模式复用**——target.yml parity 需双侧新解析器 + 新测试文件，非既有测试改写 → 支撑 D-002 适配成本标注。
- TS 侧 YAML 依赖核实（2026-09-11，读 package.json + node_modules）：`yaml@2.9.0` 已是 packages/coding-agent 与 packages/agent 的**直接依赖**（hoisted node_modules/yaml 存在）→ TS 侧解析 target.yml 零新增依赖；Py 侧 PyYAML 6.0.3。双侧均无新依赖引入，D-010 落地风险再降一档。
