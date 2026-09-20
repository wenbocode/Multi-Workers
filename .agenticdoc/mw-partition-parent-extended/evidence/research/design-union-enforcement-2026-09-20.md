# Research: parent 扩展区语义的执行点与测试面（design）

## 决策问题
回答 design §1（D-001 双层执行点、D-002 union 载体、D-003 不作用域、D-005 标签同步面）与 §3（改动面清单）。

## 调研方法与出处
- 代码事实（2026-09-20 通读）：
  - `autopilot/dispatch.py:146-176`：`_expand_read_scope(scope, config, project_root)` 现行结构——mode 门控 → 相对条目锚定 → control 追加（normcase 判重）；**scope 为空时整函数短路返回**（`if mode not in ("dual","partition") or not scope: return scope`）→ union/追加天然不作用于空 scope
  - `worker/worker-mode.ts:447-449、516-529`：wiring 形态——`readScopeConfigFromMeta(meta)` 构建 config；`pi.on("tool_call")` 拦截器显式列名 `read`/`ls`/`find`/`grep` 四工具（其余工具直接 return undefined）；`parseTaskMd(taskPath)` 在 wiring 前已调用，taskPath 在作用域内
  - `worker/read-scope.ts:224-243`：`readScopeConfigFromMeta(meta)` 纯函数，`scope: meta.readScope === undefined ? null : meta.readScope`——空数组保持 `[]`（全拒），deny-only 为 `null`（无包含检查）
  - `launcher.py:521`：撕裂校验模式行正则 `^\[mw\] mode: (single|dual|partition)[ \t]*$`（MULTILINE，marker 后 8 行窗口）——TS 侧 union 门控可对齐该行形态（全文锚定行匹配即可，无需窗口）
  - 标签消费者全量清单（grep `Parent root`）：`task-dispatcher.ts:135`（TS 渲染）、`mw_common.py:2239` 区（Py 渲染）、`test/fixtures/partition-profile-block.golden.md:6`（Py golden）、`agent-team-loop-profile-injection.test.ts:345`（TS 断言）、`test_partition_dispatch.py:92、473`（Py 模板与断言）、`mw.py:1233/1321`（show 输出与路径校验报错——措辞中性无需改）
  - `mw.py` "read-only" 仅两处：~1302（--parent 缺参报错）、~2812（argparse help）
  - 测试基建：`test/suite/autopilot-read-scope.test.ts`——纯函数 describe（containment/caps/deny）+ `startScopedWorker(root, taskKey, frontmatter)` wiring 夹具（写 conductor 形态 task.md、chdir root、激活 worker-mode、`worker.toolCall(name, input)` 断言 block/reason）；既有用例 "containment matrix … non-read tools untouched"（:491）已覆盖非读工具不经拦截
  - Py 侧翻转点：`test_partition_dispatch.py:604-620`（`test_partition_anchors_at_partition_root`）+ `test_partition_no_duplicate_control`（:622）
- spec 留底：`evidence/research/spec-parent-extended-semantics-2026-09-20.md`（发现 1/3/5：唯一机械拦截 = 读包含性；两派发路径不对称；空 scope 全拒形态）

## 发现
1. **两派发路径不对称是结构性的**：read_scope 展开只存在于 Py conductor 路径（`autopilot/dispatch.py:279`）；TS dispatchTask 路径（PM 窗口）不展开 scope，task.md 的 read_scope 原样进 worker。仅在 Py 侧追加 parent root 对 TS 路径任务无效——union 必须落在 worker 侧才能让"parent 是扩展区"成为模式属性。
2. **worker 侧 union 的最小载体**：read-scope.ts 已是纯决策函数层（无 pi 依赖），新增两个纯函数（内容解析 + config 变换）+ worker-mode.ts wiring 三行改动即可；`parseTaskMd`/`TaskMeta` 接口面零变化（避免波及其测试夹具）。
3. **空 scope 短路已天然存在**：Py 侧 `not scope` 短路 + TS 侧 `readScopeConfigFromMeta` 空 `[]` 全拒——union 的"仅非空 scope 生效"在两侧都只需在正确位置加条件，无防御性重构。
4. **模式行门控对齐既有锚**：launcher 撕裂校验已用 `^\[mw\] mode: partition$` 行形态；TS union 解析器用同形态全文匹配（不设窗口——profile 块是 task.md 内该行的唯一来源，任务正文整行命中该正则的概率可忽略，且 task.md 的信任边界本就在派发层）。
5. **`Parent root` 前缀匹配兼容新旧标签**：标签从 `Parent root:` 改为 `Parent root (extended workspace, writable):` 后，前缀 `Parent root` 匹配两种形态——升级时在途 task.md（旧标签）union 不失效。
6. **AC-004 已有半数覆盖**：wiring 用例 "non-read tools untouched" 已断言非读工具不拦截；补 parent 路径 write 显式断言即可，无需新框架。
7. **Py golden 与模板是三处联动**：golden fixture（:6）、`_PARTITION_YML` 期望模板（:92）、conductor 注入断言（:473）都含 `Parent root:` 标签——标签变更三处同步 + TS 断言（:345）共四个测试触点。

## 结论 → 决策映射
- 支撑 D-001（双层执行点）：Py 展开（frontmatter 透明）+ worker union（全路径一致）——发现 1
- 支撑 D-002（union 载体）：read-scope.ts 两纯函数 + wiring 三行——发现 2
- 支撑 D-003（不作用域）：空 scope/deny-only 不并入——发现 3
- 支撑 D-004（解析器门控）：模式行正则 + `Parent root` 前缀——发现 4/5
- 支撑 D-005/D-006（标签同步与测试面）：四测试触点 + 既有 wiring 用例复用——发现 6/7
