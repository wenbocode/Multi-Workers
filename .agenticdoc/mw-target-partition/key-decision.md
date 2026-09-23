# KDR: mw-target-partition

## R（需求）

- 技术栈: TypeScript（pi 扩展，Node strip-only）+ Python（mw 框架），YAML 配置；TS/Py 1:1 parity（T-17 模式）
- 边界: 单配置文件 target.yml v2（模式块 + active 键）新增 partition 模式（parent 必填 + partition 必填独立分片根 = worker cwd + 可选 roots）；独立 `mw partition` 命令族；不做 merge-back、不做 parent 写防火墙（欠债）、v1 零感知兼容
- 关键约束: fail-closed（规则表 12 行 + 字段层 7 类拒绝派发）；env 只覆盖激活模式字段不翻转 active；错误 kind 双侧 parity；既有 target 测试零修改（零回归）
- 关键决策（用户确认）:
  - 命名 `partition`（2026-09-18 对话；否决 generic / derived）
  - 分片根是**独立目录**而非父项目子目录；根关系校验（不相等/不互嵌，含默认形态）并入 AC-003(g)（2026-09-19 对话，用户确认 A）
  - **单配置文件 v2**（2026-09-19 需求转向 v3，取代两文件方案）：target.yml 模式块（dual:/partition:）+ 顶层唯一 active 键；partition 独立命令族；`on/off` 切换原语；v1（无 active 键）原样解析零感知，仅 partition set 触发迁移（.bak 备份）；source 枚举 {env, target-yml, default}
  - env 覆盖：MW_PARTITION_PARENT / MW_PARTITION_ROOT（仅激活 partition 时；齐备可无文件激活，不落盘；交叉 env 报错）
  - `--partition` 可省略：默认分片根 = 控制根（当前打开的项目目录），set 时展开为绝对路径落盘；解析层 partition: 字段仍必填（2026-09-19 对话）
  - parent 无写回/合并流程、不做写路径防火墙（与 dual 对 engine root 一致；硬防护另立 key）`[用户确认 A]`
  - 撕裂校验：spawn 前比对 task.md profile 模式行 vs 当前 active，不一致任务 failed 不静默换 cwd（AC-020）`[用户确认 A]`
  - 升级零感知：AC-016 legacy 字段投影基线先行录制 main（2026-09-19 对话）
  - 保留任意命名 roots（占位符 {root名}），仅 partition 块合法；键名 [A-Za-z0-9_-]+ 避开保留名 `[AI 推荐]`
  - read_scope 不自动并入 parent（红线：不扩大未声明的 containment）`[AI 推荐]`
- 调研留底: evidence/research/spec-partition-semantics-2026-09-19.md

## A（架构）← system-design 追加（2026-09-19，随单文件方案重写）

- D001 解析入口: 选单一 choke point 内部按文件形态（v1/v2/无）分流，否双入口（6 调用点零改动）
- D002 TS 类型: 选 interface 增量 + gameRoot 可空 + partition 字段，否判别联合（下游 narrowing 威胁零回归）
- D003 错误模型: 选复用 kind + 消息要素，否新增 kind 值（spec 按 kind 锁定）
- D004 规则表: 选 _decide_active_mode 纯函数（§1.5 规则表为规约），否逻辑散置（AC-017 参数化单点）
- D005 profile 注入: 选独立 partition 渲染块 + active 模式行 + 切换整体替换，否扩展单一函数（dual 文本零改动）
- D006 read_scope: 选 mode 集合判定各自锚定，否双函数（dual 位相同）
- D007 launcher cwd: 选 mode 分派 + 撕裂校验（profile 模式行 vs 当前 active），否仅静默重解析
- D008 set 写盘: 选块级编辑 + 临时文件原子替换 + v1 一次性迁移（.bak），否 yaml round-trip（丢注释）
- D009 doctor/缓存: 选段 JSON 零新增键（dual/single/v1）+ partition-only 键 + resolved-config 指纹，否 active_file 进段 JSON
- D010 TS 转发: 选 mirror /mw target 可注入 runner 模式，否新命令框架
- D011 parity 布局: 选复用共享夹具 + 增量字段，否独立目录双 runner（契约单点）
- D012 on/off: 选每命令族 on/off 轻原语（v1 报错提示迁移），否 set 重参数切换
- D013 撕裂检测: 选 task.md profile 模式行与 spawn 时解析模式比对，否派发快照（复用已有注入块）

## I（实施）← PM 执行中追加
