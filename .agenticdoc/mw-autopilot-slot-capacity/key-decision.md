# KDR: mw-autopilot-slot-capacity

## R（需求）

- 技术栈: Python（multi-workers: conductor/launcher/serve/mw.py）+ TypeScript（agent-team-loop: monitor/status-model）
- 边界: 不重写调度架构、不引入中央调度器（GC-1）；不改 pi 核心；proxy/凭证机制只在被证明是瓶颈时才作为依赖项记录
- 关键约束: 并行度是**文件驱动协调**下的参数（`_index.parallel` + 文件锁）；提高并行度会同时放大共享文件写竞争与跨 key 冻结面风险
- 用户原始提问（2026-09-26）: "当前 autopilot 的 slot 为什么只有两个，并行度是不是不够"
- 需求本质（PM 初判）: 用户问的是**上限的成因与充分性**，不是"给我改大"。因此本 key 的第一交付是**证据**（成因三态判定 + 槽位利用率实测），第二交付才是"改 / 不改"的结论与落地方案。
- `[待确认]` U-1..U-5 见 spec §4（目标形态 / 现象 / 成本容忍 / 层级 / 多项目计额）

## A（架构）← system-design 追加

<!-- system-design 追加：架构决策（逐条来源 design.md §10） -->

- D-001 命题模型: 选事实面/政策面两分 + 4 判据，否单层命题（现状 6/6 命题恒真、零信息量）
- D-002 三分处置映射: 选case1 仅预算/假阴窄集/xkey-S4，否stage-close 整体自动（4 反例否定其前置）
- D-003 硬前置修复顺序: 选波 0（D3+D1）→ 波 1（载体+D2+D4），否先上自动再补护栏（无上界自动 approve 是灾难路径）
- D-004 消费记录载体: 选gate 文件字段 + timeline 回退，否独立 ledger / roadmap 侧栏 / 扩轮转（id 跨归档重用；roadmap 被整写；剪掉的记录不可恢复）
- D-005 待复核形态: 选非终态 + 收口前置 + 48h 升级，否算终态 / 旁挂状态（算终态会导致回退已 closed 的 stage）
- D-006 合法重开: 选`review-decided` 只动 key-status，否conductor 自动重开（JC `gate-0008` 即意外回退）
- D-007 证据源与快照: 选三命题 + 取最小 + 单向 dispute；每门 sidecar，否单一优先级 / 只靠 verdict.txt（`l3-verdict.txt` 零绑定且是唯一证据面）
- D-008 对账: 选拦新 `stage-close`，历史只 warn，否自动改回 done / 只告警（不回退历史且不继续制造不一致）
- D-009 自动留痕: 选新事件 + 独立账本 + conductor 派生字段，否塞进 `gate-answered.detail` / 只写 timeline（污染 `re.match` 解析面；2 代轮转）
- D-010 开关: 选`auto_gate_mode` off/shadow/live，不入 `EFFECTIVE_KEYS`，否两 bool / 扩 paused / env / 门级刹车（无非法组合；策略键不该被机器层改写）
- D-011 配额熔断回滚: 选复用 P1–P9 + 熔断落盘 + `gate-auto-revoke`，否自造状态机 / 内存熔断 / 逆操作消费集（原语已足；重启后仍须熔断）
- D-012 影子门槛: 选≥5 夜 ∧ ≥20 条 ∧ 每规则 ≥1 反例，否直接 live / 历史一致率（防恒真规则与选择偏差）
- D-013 守卫覆盖面: 选`_autopilot/**` 纳入封堵 + conductor 侧实现，否放开 agent 写 gate（被审方当前可伪造事件与开关）
- D-014 字段 schema: 选12 + 26 全可选、单行 JSON、`gate_schema`，否扩 `_REQUIRED_FIELDS` / 嵌套 YAML（34 个历史门须照旧解析；解析器不支持嵌套）
- D-015 呈现三层: 选1 行 ≤110 列 / 1+13N / doctor 段 + D1–D7，否自由文本摘要（不可机器校验、LLM 会漂移）
- D-016 (c2) 心跳: 选D+B+C（分类判定 + 心跳 + 二次确认），否单独抬阈值（真因是 bash 输出驱动；数据被截尾）
- D-017 超时死键: 选接线 `timeout:`（不动键集合），否删键（fail-closed 会拒掉现存配置）
- D-018 (d) 并发: 选本 key 只做观测与判据，否本 key 放开（写面机器判定为零；主因是 gate）
- D-019 归属: 选行级 `origin` + `owner_key` + path 兜底，否继续用前缀 / 只用 path（三套口径分歧且前缀是假信号）
- D-020 槽位上限: 选**不改**，否提默认值 / 机器层覆盖 int（cap 从未越界；改默认是空操作）
- D-021 enum 上线: 选两侧同波，否单侧先行（未知值会跳整个 tick）
- D-022 实施波次: 选5 波（见 §1），否—（依赖链决定）

## I（实施）← PM 执行中追加
