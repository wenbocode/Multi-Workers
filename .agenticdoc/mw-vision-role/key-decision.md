# KDR: mw-vision-role

## R（需求）

- 技术栈: Python 3（packages/multi-workers）+ TypeScript（packages/coding-agent/src/extensions/agent-team-loop）
- 边界: 只做视觉**输入**（看图），不做图片生成；不新增 provider/凭证；不改 pi 核心
- 关键约束: 派发角色与类型的两侧镜像（Py `mw_common` / TS `shared/dispatch-models`）必须同步；工具白名单两侧逐元素一致（GC-3/GC-4）
- 交付: 新角色 `vision` + 新任务类型 `vision` + 派发期能力门禁（含 worker 侧兜底）+ 配置期探针 + PM 知情面 + 自动路由（auto-route）+ doctor/show 能力列
- 用户确认（2026-09-26，首轮）: (1) 只看图，不生成；(2) 新增 role + type 映射；(3) 门禁要
- 用户确认（2026-09-26，第二轮，spec 评审）:
  1. `vision` 角色模型值 = `timi/deepseek-v4-flash-vision-exp`（用户知情选择 `-exp`，否决了 AI 推荐的 `timi/gpt-5.6-sol`）
  2. `mw model set vision <纯文本模型>` 拒绝，但提供 `--force` 逃生口
  3. AC-018（PM 贴图提示）作废（RQ-5 实证无钩子点）
  4. auto-route **不**越权改写显式 `type:` / `model:`（显式优先 → 走拒绝）
  5. PM 主窗口自身看图不做（不改 `settings.json` defaultModel 优先级语义）
  6. 任务类型名就叫 `vision`（与角色同名；AI 推荐的 `design` 被否决）
  7. 门禁触发形式 = 显式 `images: yes|no` 头 + 仅 TS 派发面 auto-detect（`images: no` 最高优先）
  8. worker 侧兜底（AC-011）保留
  9. `vision` **允许** conductor autopilot 派发（`conductor_dispatchable=True`）；但 conductor 无内容检测，不会自己发现 UI 子任务
  10. `vision` 角色与 `vision` 类型均**追加到末尾**（不动既有顺序断言）
  11. Python 能力探针用 P1（解析现有 `pi --list-models` 表格，不动 pi 核心，GC-2）
  12. `mw model show` 与 `mw doctor` 两侧渲染都加 `images=yes|no|unknown` 列

## A（架构）← system-design 追加

- D-001 门禁落点: 选{TS 派发面前置拒绝 + worker 兜底}，否{Python launcher 侧}（有 registry 且写盘前零副作用）
- D-002 能力数据源: 选{TS 内存 registry / Py `pi --list-models` 探针}，否{pi 加 `--json`；能力快照文件}（同源且不动 pi 核心）
- D-003 声明形式: 选{`images:` 头 + 描述 auto-detect}，否{仅显式头；仅 auto-detect}（可豁免且 PM 免记）
- D-004 auto-route: 选{同点只换模型 + 留证，`type:` 不变}，否{改判 type；报错让 PM 重派}（只读任务不被隐式提权）
- D-005 兜底实现: 选{`session_start` + 复用 `dispatchRefusal`}，否{改 `read` 降级语义；不兜底}（复用既有失败通道）
- D-006 镜像同步: 选{双份常量 + parity 锁}，否{代码生成}（无新构建面）
- D-007 命名与排序: 选{同名 `vision`，末尾追加}，否{`design`；中间插入}（用户拍定 + 不动既有断言）
- D-008 暴露面: 选{show + doctor 都加列 + PM 面四处同步}，否{只加 doctor}（配置期反馈 + PM 主动用）
- D-009 conductor 派发: 选{允许}，否{禁止}（用户拍定；阶段调用点可显式用）
- D-010 留证通道: 选{`model-reason: auto-route` + 回显}，否{只回显；新头}（复用既有头 + 会话可追）
- D-011 能力列格式: 选{行内 `role=value images=<v>`}，否{行尾分组子句}（AC-015 要求每角色行都有）
- D-012 doctor 告警级别: 选{suggestion（退出码 0）}，否{issue（必致退出 1）}（与 AC-010 及既有 dispatch 先例一致）

### 设计期对 spec 的反向修正（均已留痕）

- spec §4 auto-route 边界注：`[REVISED @ 2026-09-26]` 改为“只换模型不改 `type:`”（原注与 AC-017 互斥，且会隐式提权）
- spec AC-010：`[REVISED @ 2026-09-26]` issue → suggestion（doctor 退出码由 `summary.healthy` 决定，落 issues 必导致退出 1，与“三情形退出码 0”互斥）

## I（实施）← PM 执行中追加
