# KDR: mw-rag-integration

## R（需求）

- 技术栈: TypeScript（pi 扩展，无新依赖）+ Python stdlib（mw CLI / launcher / audit）+ Markdown（skill 与调研文档）；MCP 传输 streamable-http + JSON-RPC 2.0（protocolVersion 2025-03-26，Mcp-Session-Id）
- 边界: 不 fork/不分发 rag-mcp 包；不做 require 硬门禁（K3）；不做跨服务语义自动路由；不暴露 rag_chat 给 coding/review；不做通用 MCP 客户端框架
- 关键约束:
  - 配置两层：机器级 `~/.agents/rag-servers.yml`（N 个服务，`transport: mcp|skill|both`）+ 项目级 `<control>/.mw/rag-servers.yml`（覆盖/新增）；项目级 `target.yml` 的 `rag:` 段做选用与"必需用"声明
  - 未启用 = 工具根本不注册（非 RAG 项目零影响是结构性保证）
  - 工具面精选六个（`rag_search`/`rag_symbol`/`rag_graph`/`rag_impact`/`rag_sources`/`rag_feedback`）+ 仅 `rag-research` 类型可见的 `rag_chat`；`server` 作为参数（密闭枚举），不加名字前缀
  - 引用归一化：返回即带 `local_path`/`exists`/`line_hint`/`snapshot_warning`，引用字符串由工具给出
  - 五层降级语义：未启用不可见 / 探活失败仍注册并标注 / 运行失败熔断（连续 3 次）/ `require` 只告警 / 未调用告警
  - 五类证据行：`rag_call` / `rag_fallback` / `rag-unavailable` / `rag-rewrite-degraded` / `rag-required-missing`
  - 长调用与 watchdog 共存：`onUpdate` 心跳 ≤30s；`rag_chat` 单次上限 600s + 预算默认 2 次/任务
  - token 只以 `token_env` 名出现，launcher 注入 env；不落 task.md 与任何证据文件
  - "用了" 的定义 = 产出物里有可核对的引用（`server:source:file_path:line` + 本地 resolve 后行号），不是"调过了"
  - "必需用" 判定粒度：角色声明优先、阶段声明兜底、两者并集（不做例外）
- 用户决策记录（2026-09-22 需求讨论）:
  - B+C 形态：多服务配置 + 逐项目选用 + 明确角色/阶段必需用
  - both：同一服务可同时以 mcp 与 skill 形态接入（工具走 mcp，方法论/降级走 skill 包）
  - 方案 A：扩展内实现 MCP client（否决 Python 代理方案与纯脚本桥方案；后者在 review 档不可达）
  - 配置两层（否决单层）
  - 本期交付 K1+K2，K3 另立 key
  - rewrite 定位修正（用户指出）：`rag_search` 的 `auto_rewrite` 支持自然语言按库改写，替代"agent 猜 symbol"；入口阶梯为 自然语言 → search(rewrite) → symbol/graph 下钻
  - `rag_chat` 落地（用户指出）：全召回流程有价值，适合库调研 → 独立任务类型 + 独立文档，不进 coding/review 面
- 调研留底: `evidence/research/spec-rag-mcp-integration-2026-09-22.md`

## A（架构）

- D-001 client 位置: 选扩展内 TS 实现，否 Python 代理/纯脚本桥（脚本桥在 review 档不可达；代理绑 serve 且第二套归一化）
- D-002 工具注册门控: 选 activate 按配置决定 + worker `setActiveTools` 后追加子集，否静态写死/动态生成白名单（零影响须结构性成立、parity 须可机械校验）
- D-003 配置载体: 选机器级 `~/.agents/rag-servers.yml` + 项目级 `.mw/rag-servers.yml` 浅合并，否单层/放 `~/.pi/agent/`（跨项目复用 + 避开 pi 私有与受保护集合）
- D-004 返回结构: 选归一化信封 + citation + 能力表，否透传/逐工具硬编码（结构漂移不进证据、多 server 零代码扩展）
- D-005 传输与熔断: 选 both 时 mcp 主 cli 兜底留证 + 3 连败熔断，否只 mcp/只 cli/静默兜底（覆盖 skill-only 与 review 档，兜底必须可见）
- D-006 长调用: 选 30s `onUpdate` 心跳 + 600s 上限 + 落盘预算，否调大 idle 阈值/拆短调用（不引入全局副作用）
- D-007 路径解析: 选 TS 内联 + fs 存在性检查，否 spawn `resolve_path.py`/不解析（每次调用都要做，可核对引用是核心判据）
- D-008 证据与 audit: 选 trace 机器行 + 只读 audit（0/1/2），否写回/纯 grep（只读原则 + 存在性无法 grep）
- D-009 task.md 注入: 选双侧同锚追加 `mw-rag: v1` + fingerprint 撕裂检查，否无指纹/只 TS 注入（防静默换库；conductor 路径不能漏）
- D-010 Python 侧接入: 选 post-step env 注入 + 剥离面扩展 + 三动词 CLI，否改 6 分支/塞 providers.json（单点注入；语义不同）
- D-011 rag-research 边界: 选入 Python `REGISTRY` 并加 `conductor_dispatchable=False`（parity 测试**零修改**），否只放 TS 桶 + 改允许列表（等于动门禁）/ 设为可派发（超范围）
- D-012 方法论载体: 选框架仓 skill 单一来源 + `mw rag sync`（显式命令，K1/AC-017），否写进工具描述/会话自动安装（避免双份漂移；自动安装破坏零影响）
- D-013 机器级路径解析: 选 `MW_RAG_SERVERS_HOME` → `HOME` → `USERPROFILE`，目录缺失视为空层且不自动创建，否硬编码 `~`/自动建目录（Windows 与 Node/Python 展开规则不同）
- D-014 零影响面: 选会话运行期不写任何配置/skill/budget 文件，否 activate 预热与安装（让零影响是结构保证）

评审与修订（2026-09-22，第 1 轮）:
- `mw-rag-integration-ref-verify`: VERDICT REFS-BROKEN——16/21 引用一致；修正三处实质问题：`setActiveTools` 在 `before_agent_start` handler 内（每次 run 执行，工具集必须幂等）、`_build_env` 是 5 早返回 + 1 末尾返回、task-dispatcher 只是“内容注入”唯一锚点（task.md 写点共 3 处）；行号漂移已按实据修正；parity 断言原文已取得
- `mw-rag-integration-design-critique`: VERDICT NEEDS-REVISION——采纳 C-1/C-3/C-4/C-5/C-6/C-7 与 W-1~W-10、S-1；**不采纳 C-2**（PyYAML 为既有隐式依赖，`mw_common.py:53`）
- spec 修订：AC-009/AC-013 文字细化（标记 [REVISED @ 2026-09-22]），新增 AC-017（skill 同步，K1）；VC 由 22 条扩到 26 条

调研留底: `evidence/research/design-rag-integration-2026-09-22.md`

## I（实施）

*（PM 执行中追加）*
