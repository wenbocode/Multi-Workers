# achieved.md — mw-autopilot-gate-alarm-liveness

基线：`cc9a46a1a`。相位：EXECUTE → 收口。收口日期：2026-10-14。

## 目标（用户三轮重述后的第一性表述）

**autopilot 无人值守时：① 阻塞必须可见；② 派发不得以"有人 watch/接管"为前置；③ 能自动放行的门禁不留给人。**

## 系统行为变化

1. **阻塞可见（①）**
   - `/autopilot monitor` 常驻显示全部 pending gate（无 cap/衰减/去重），**并新增 stage 级主闸行**（每个 stage 的卡门 + age + 被冻结的 key；`halted` 自名 blocker）。
   - 每条 gate 行带**六值抑制原因**（漏斗序：`gate-queue-unreadable > key-in-flight > cap-reached > stage-terminal > not-due`，`unresolved-scope` 正交）。
   - **110 列预算下 DRIFT / reason / age 永不被丢**：改压缩编码（`~D`、`R:*`、紧凑 age、`+N` 计数、`J`/`P` 分类记号）+ 确定性 fit ladder，被压掉的次级字段以 `+N` 留痕。
   - **队列不可读不再伪装成 "0 pending"**：`partial` + 0 可读 ⇒ 显式 `gate-queue-unreadable (N unreadable: samples)`；TS `listGates` 区分 ENOENT 与其它错误（errors 经 `warning:` 行可见）；Python 侧三情形（不存在/空/不可读）分离，`gates` 路径为文件或 EACCES ⇒ 显式 unreadable + 既有 `config` 事件 + CLI 干净报错 + doctor 置 error。
   - 抑制与丢弃都**留痕**：被抑制 gate 按 `(gate, reason, bucket)` 去重写 `phase:"remind-suppressed"` 台账行；无 watch/他 key/读错误导致的丢弃写不带 `seq` 的独立 drop entry（不推 watermark）。

2. **派发不以"有人接管"为前置（②）**
   - 核实：**派发本身不读 watch**（launcher 只读 `_workers.parallel` pending 行；conductor 的 dispatch 调用点无一读 watch）；真正阻断在状态机。
   - **合成 claim**：对"有工作但无 live claim"的 key，conductor 以 `autopilot@<host>:<pid>` 接管（创建/60s 续期/身份失效回收，**无 TTL 猜测**；只对真有未派发工作的 key；idle/已产出/done 的 key 不接管），派发随即恢复。
   - **人工优先**：人工 `switch_key` 立即生效且不被抢回；AI 窗口接管 conductor 接管的 key 时**留痕**（既有 watch entry 的 `tookOverFromConductor` + 既有通知，零新事件名）。
   - **跨主机不双重持有**：外机合成 claim 不再被判 stale/回收/接管（Python 与 TS 判定对齐）。

3. **能自动放行的门禁不留给人（③）**
   - **`stage-close` 自动收证并 approve**：五个判据（stage 可解析 / 全 key 终态 / 无在飞 / reconciliation 未阻断 / dossier 已写 / 每 key 终态凭据齐备）**全部从磁盘现算**；替换原先"读无生产者字段、只能永远拒绝"的 `stage-close-fact-guard`。
   - 留痕零新字段：`answered_by="conductor-auto:<rule_id>"`、`answer_source="conductor-auto"`、`auto_policy_id="<rule>@<version>"`，落既有 `phase:"decide"` 台账行（该 phase 在生产此前为 0 行），事件名复用既有。
   - **回落必可见**：任一判据不满足 ⇒ 不自动放行，回落人工门并**点名缺失项**（实测：JCodingAss `gate-0007` 可放行、`gate-0008` 因缺 `l3-verdict.txt`/`l3-report.md` 必须回落）。
   - `stage-confirm` **不自动**（授权而非文书）；48h 兜底经核实**从不**闭合 stage/不重写 key-status，与自动放行互补不冲突（已加回归断言）。
   - **门生命周期**：re-attest 新建 gate（`context_refs` 载 `reattest-of:<id>`，编号不复用、原判定字节不变、不依赖 `status=="stalled"`；证据刷新后可重评）；destructive reject 需 `--confirm-destructive` 二次确认（未确认零写盘）。
   - **分类**：`blocker_class` 以**序外标量**注册（40 名冻结序不动），值域闭集 `{paperwork, judgment}`，`None` 折叠为 `judgment`（未分类 ⇒ 不自动放行），五形态 fail-closed，面板以 `J`/`P` 显示。

4. **服务自证与漂移**
   - `serve.meta` 身份**先于** `_write_pid` 采集；漂移判据换轴为 **`code_digest`**（runtime 文件集 sha256；mtime 供起点、commit 供命名），**不再用短 OID 比相等**（此前必然永久假漂移）；skip 集补 `test` 目录；`mw status`/`mw doctor` 等 4+1 入口判 `STALE CODE`；commit 不等而 digest 相等 ⇒ `history-only`（只记录不告警，D-009）。
   - 唯一实现点：`mw.py` serve 循环（60s 节流）；conductor 侧只读判定结果（D-016）。

5. **回收契约（worker 产物自带可信状态）**
   - 角色分流：writeless 角色（research/review）只把声明交付物当写意向，报告里的普查路径不再进 `declared`。
   - taskDir 外交付物进入对账（`<key>/evidence/**` + 新鲜度），旧产物按读取引用丢弃（避免假绿）。
   - 基础设施写入**文件级**白名单（框架自身写的文件）与"**不存在即非写入**"（幽灵文件名/代码标识符 ⇒ 可见 warn，不入 falsifying）⇒ **C-36 六子类**全部收敛：过判 / taskDir 外漏计 / 路径污染 / 系统写入误归因 / 幽灵文件名 / 代码标识符。
   - 收窄后**恢复对框架文件的越界检测**：worker 若声明写 `_autopilot/gates/gate-XXXX.md` 等 conductor 控制面文件 ⇒ 报红（QG R-1 的可构造反例已转为回归用例）。

## 验收与证据

- 对抗式质量门：`evidence/quality-gate-report-20261013.md`（AC-001…AC-016 逐条带证据；**11 成立 / 4 部分成立 / 0 判据放宽**；QG 缺陷 R-1…R-5 全部处置，R-6 随 R-1 关闭）。
- 对抗审计原始报告：`workers/mwgal-t18-adversarial-qg/report.md`（11 项探针 + 8 条对抗用例；**探针 5 判定 `stage-close` 自动放行不可构造绕过**；探针 6 判定 48h 兜底不闭合；探针 8 判定 `blocker_class` 五形态全覆盖且双语同向）。
- 生效清单：`evidence/runs/closeout-runtime-actions-20261013.md`（含"未 cutover 时的症状"实证：`mw status` 对活体 PID 168160 报 `STALE CODE`）。
- 文档：`packages/multi-workers/docs/autopilot-observability-guide.md`（9 面 + 生效矩阵）、`packages/multi-workers/README.md` 新节、两个 CHANGELOG 的 `[Unreleased]` 追加。
- 全局检查：`npm run check` exit 0（`Checked 1149 files … No fixes applied`）。
- 16 张实现/修复卡 + 4 张研究卡 + 1 张对抗审计卡全部终态；PM 逐条独立复核（字节 + 字符串锚 + 独立复跑验收）。

## 遗留

1. **G-1（AC-005 部分成立）**：漂移自证依赖 `serve.meta` 的新 schema；旧进程在 cutover 前仍会报 `STALE CODE`（**这正是设计意图**，但文档需人执行重启才生效）。
2. **G-2（AC-014 部分成立）**：外机 conductor 永久下线时，其合成 claim 会让该 key 停止派发且人工接管需 `force`（判定：**宁可有可见停顿，不可静默双主机派发**）。已登记为可见、可人工处置；未做跨主机存活检测。
3. **G-3（AC-015 部分成立）**：`stage-close` 自动放行受既有 shadow 安全阀与 `auto_gate_mode` 默认 off 约束（默认不自动 ⇒ 需显式启用）。
4. **G-4**：`stage-confirm` 只做可见性升级，不自动放行（D-014② 的刻意取舍，非缺陷）。
5. **coding 角色的宽别名过判**（T-17 自报残留）：coding worker 报告里的**读引用**仍可能进 `declared`（如 `_workers.parallel`、`serve.meta` 这类已被 infra 白名单覆盖的除外）。未修。
6. **`mwds-t23-cutover-recheck.test.ts` 的 bundle sha 断言**在 HEAD 即为红（陈旧产物期望，跨 key 问题，非本 key 引入）。
7. **未做 cutover**：Python 侧改动需 `/mw restart`；TS 侧需 `build --install` + `/mw restart` + `/reload`（**需用户执行**）。
8. **未提交**：本 key 全部改动尚未 commit（按规则需用户要求）。
9. 过程发现已归档待后续 key 处理：**上一 key `b65380d1b` 的配置键未同步 TS 注册表与放行集合，P5 锁红着出厂**；根因 `npm run check` 不跑测试 ⇒ 收口判据应补"至少跑一次跨语言 parity 锁"。
10. cutover 后应执行**生效验收测试**：派发一个 trivial worker，期望账本零 gaps（依据：两轮实测共 8 条同类误判全部源于"源码已修、运行 bundle 陈旧"）。
