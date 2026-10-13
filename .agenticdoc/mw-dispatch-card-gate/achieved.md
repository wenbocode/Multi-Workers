# achieved.md — mw-dispatch-card-gate（worker 任务投递与回收契约）

- Key: `mw-dispatch-card-gate`｜Claim: `WENZHOUBOU-PC4:117296`｜阶段: EXECUTE → DONE
- 日期: 2026-10-12 ~ 2026-10-13（跨本地午夜）
- 实现卡: T-01…T-07 / T-09 / T-10 / T-12 / T-13 / T-14 / T-15 / T-16 / T-18 / T-19 / T-20 / T-21 / T-22 / T-24 / T-25（全部 done + PM 独立复核 + ack）；QG: T-11b（FAIL）、T-17（PASS）；cutover: T-08（第一次）、T-25 后第二次；验证: T-23 / T-26b
- 两条设计总原则（用户裁定 D-002）：**投递优先**（机制第一职责是把正确、必要的上下文 + 任务内容 + 交付格式送到 worker，限制只是副产品）；**不设探索限制**（投递物是种子不是上界，worker 应能启发式自行寻找上下文并记录来源）

## 系统行为变化

1. **投递必须带卡（工具层强制）**：`dispatch_worker` 的 `card_path` 为**必填显式参数**；卡必须携带投递信封（type + 上下文/要求/交付格式）、按类型的 extras（coding：写入允许面/写入禁止面/验收命令/改动历史；research：唯一证据文件；review：审计目标/未覆盖面声明）与**种子最小项**（`goal.md` 引用 + 至少一条 `路径:行号`）。不完整卡的派发**被拒且零副作用**（生产路径实测：PM 自己的一张卡被打回，补种子后同 key 通过）。
2. **生成端无条件注入 + 身份行**：PM/conductor 两条路径渲染 `task.md` 时**无条件**注入三段 canon 与 type extras；头部区写出 `card_path:`、`card_sha256:`、`envelope_producer: <producer-id>@<version>`（TS 路径实测 `agent-team-loop-pm@0.83.0`；conductor 路径 `autopilot-conductor@<version>`）。
3. **服务层按时间边界 fail-closed + 三分支可判**：晚于 `ENVELOPE_ENFORCE_SINCE` 的派发一律要求信封；三分支（合规 / legacy / 版本偏移）分别可判可记，拒绝时**指名缺什么 + 怎么修**（实测日志：`envelope missing: 验收命令 … [producer=agent-team-loop-pm@0.83.0 not provably older than baseline=2026-10-12]`）。逃生舱 `envelope_fallback` **默认关**，开启时逐行 `[ENVELOPE_FALLBACK]` 审计、不放宽写面判据；**全零版本按"未知版本"处理，不得判为"比基线老"的 producer-skew**。
4. **回收契约判据健全化**：`output.md` 必备段 + 改动历史（报告清单 ⊆ trace 事件）为正式判据；提取侧新增**否定感知**（禁止面/「未写入 …」不得算写入意图）、**按 worker 归属**（只比对该 worker 自身的 `[WRITE_FILE]` 事件与写面）、**词元卫生**（非法候选仅计 `malformed_candidates`，不参与判定）；**dotless 存在性仲裁**（无扩展名但真实存在的路径按声明处理，避免漏红）。
5. **投递归属（AC-011）**：新增 `ORPHANED` 判定（有未派发工作 ∧ 无活 claim ∧ 无活运行 ∧ 有 owner 证据）与 **claim-free 修复派发** —— 修复**不写 `_index.parallel` claim**，conductor 对该 key **仍 eligible**（反例已断言）；告警按 kind 分流（只有真实拒绝类用"已拒绝"，notice 类用中性措辞）；`out-of-scope` 不再恒亮。随后按 C-30 收窄：工作须**无终态产物**且被该 key 当前状态引用；owner 证据须**当前有效**（`idle` + 数月前 Claim-Id ⇒ 不可修，只告警）；**idle/终态 key 一律只告警、零写入**（禁止自动建档）。
6. **conductor 不再静默停摆**：roadmap keys 表**行级容错**（单元格含未转义 `|` 时按"首列 key／末列 depends_on／中间拼回 role"恢复，坏行跳过不废表）；降级**局部化**（单行问题不得连带禁用 stage-terminal suppression）；解析失败/告警**限频 fail-loud**（含路径+行号+原因+修法，双出口）。
7. **可验证的产物一致性**：`card_sha256` 有真实读取者（默认红，不再依赖 `--strict`）；`card_audit` 可判定 `dispatched / missing / tampered / unlisted_after_boundary`；全局安装 bundle 与 repo bundle 同源可比（第二次 cutover 后两者均为 `5877E4FD3F035BDB…FAC669`）。

## 遗留

1. **T-17 QG 的 12 项 P3**：R-01（无 `card_sha256` 的行不检）、R-02（同手改两文件可绕）、R-03（extras 只写在卡 prologue ⇒ 过拦方向）、R-06（coding 经 bash 通道写 `config.json` 翻转逃生舱的残留链）、R-08（design §1.3 review-bash 行与 spec REVISED 的矛盾；vision/rag-research extras 声明与代码豁免不一致）、R-09（spec §7 `update_index.py` 锚点目录前缀）、R-11（注释藏写序的剥离模式建议收窄为 `mw-*` 标记族）… 均**登记不阻收口**。
2. **C-27**（前 key 文档 shorthand 锚点 + 锚点门口径不一致）—— 已两轮改善引用形态，仍未 resolved，交 C-27 专项 key。
3. **C-28**（两条 Python 基线失败，环境噪声）；**C-29**（自注入 marker 触发自身守卫）已由 T-16 修复。
4. **C-30**：ORPHANED 修复路径曾在 `agent-team-loop` / `mw-dispatch-reliability` 两个 idle key 上误触发（3 条队列行、4 秒 done、污染全局队列）；T-24 已收窄判据，但**那 3 条残留行保留**（撤行风险大于收益），登记为已知残留。
5. **C-31**（身份行版本恒 `0.0.0` ⇒ TS 路径版本不可比）—— T-25 已修（构建期 `define` 注入 + 服务层"未知版本"语义），运行期闭环已由 T-26b 证实（`@0.83.0`）。
6. **C-32**：派发写序列**非原子** —— EPERM 打断后留下**半成品 `task.md`**，仍被服务取走 spawn、随后在信封门被拒（`envelope missing: 验收命令`）⇒ 队列多一条 `failed`。修法方向：渲染完成 + 注入信封后一次性落盘，或写入时打"未完成"标记由服务层拒 spawn。**本 key 未修**。
7. **C-33**：T-23 的测试写死了 cutover #1 的 bundle sha ⇒ 第二次 cutover 后 1 个用例假红。修法：不得写死构建产物哈希，改为动态比较（同源校验本身已足够）。
8. **C-34**：worker 的 ad-hoc 临时产物写到 **cwd（`H:\git`）**，在仓库外留下 40 个文件（已清理；trace 留痕保留）。修法方向：派发时钉死临时目录（`PI_WORKER_TMP`/taskDir），并把"越出仓库根写入"作为可检测事实。
9. **全局队列文件多写入方**：实测 `_workers.parallel` 原子改名 `EPERM`（现场复现），伴随同 task_key 多次 run（本 session **45 条假 `failed` 回读**，最多同 key 11+ 个 run_id）。**`run.json` 应定为运行状态唯一权威、队列行单写入方** —— 本 key 未修。
10. **假 `needs-clarification` 6 次**（T-18/T-19/T-20/T-21/T-22 等）：根因（否定盲区 + 无按 worker 归属 + 词元残渣）已由 T-21 修复，运行期复查（T-23/T-26b）已不再出现 `unrecorded write(s)`。
11. **26 条 `unlisted_after_boundary` 既存红**（cutover 前的历史派发）：按"**时间边界不改、不回填信封**"裁定为**历史证据**保留；cutover 后的派发均为 `dispatched [ok]`。
12. **ORPHANED 准入的放宽→再收窄**已落地，但 **conductor 存活探测**仍未做（存在理论上的同 tick 竞争；`_workers.parallel` 按 taskKey 幂等故无重复行）。
13. **notice 的路径是模式化形态**（`{key}/workers/<task-key>/task.md`）而非逐 key 绝对路径 —— 受 T-19 的形态断言所限；如需展开须专门裁定放宽该断言。
14. **`build-extension.sh` 路径未直接运行验证**（T-25 残留）；`VERSION` 的 `0.0.0` 兜底字面量仍在（`define` 缺失时才生效）。
15. **F-5**：Python label region fix 无跨语言测试（前 key 遗留）。
16. **E2Feature 侧**：其 conductor 恢复推进靠**人工修复 `_roadmap.md`**；T-20 的容错/降级局部化/永不静默需**它自己的服务/conductor 重启**才生效（其 `serve.meta.code_dir` 直指本仓，无需安装）。
17. **本 key 未做**：C-32/C-33/C-34 与队列单写入方的修复、`mw-claude-mirror-parity` 的 C-9 洞（PAUSED key）。
18. **C-35（收口后运行期观察 2026-10-13）**：T-24 收窄在生产路径生效 —— 通知为 `2 key(s) with work but stale owner evidence — claim-free repair skipped, nothing written`（`agent-team-loop`、`mw-dispatch-reliability`，原因均为 `index 状态 idle`）。PM 独立核对被点名 9 个 task：7 个有历史终态产物（`ga-spec-review-1` output.md 09-07 19:32；`mw-dr-glm53`/`mw-dr-ok`/`mw-dr-pi-timi-test`/`mw-dr-live-claude` 08-28 21:01~21:12），3 个无产物（`mw-dr-live-claude2/3/4` —— 系 claude CLI 凭证缺失的按次失败，非「未派发工作」）；9 个均已不在活动队列（已 reap/ack），两 key 在 `_index.parallel` 均为 `idle` 且 Claim-Id 出自 8 月 ⇒ **跳过判定正确、零丢活**。**新登记**：`idle` key 中「有工作但无终态产物」的子集虽被正确跳过，但**除这一行中性提示外没有任何升级出口** —— 若其中确有真丢失的工作，只能靠人自己看见这行。修法方向：对「无终态产物」子集保持中性措辞但附可操作提示（如 `pm retry <key>`），或将其单列成独立 kind。
