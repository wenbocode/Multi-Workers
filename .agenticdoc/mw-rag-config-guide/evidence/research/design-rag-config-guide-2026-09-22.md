# 调研证据: mw-rag-config-guide / design 阶段（2026-09-22）

目的：为 D-201~D-208 找"既有模式"与"替代方案被否"的出处，避免发明新写法。

## 1. D-204 文本级追加 `rag:` 段（而非 YAML round-trip）

- `mw.py` 已有先例：`_apply_bootstrap_line` 只改单行、`_atomic_write_yml` 原子替换，注释与其它段一律保留；
  `mw target set` 的注释明确说明「v1 flat 写与历史字节一致」是被测试锁定的契约（AC-013 类）。
- 反证：若用 `yaml.safe_load` + `yaml.dump` 重写 `target.yml`，会丢注释、重排键序、把 flow 风格改成 block（或反之），
  并且**会碰到其它 key**（`mode`/`game`/`engine`/`dual`）。本仓任一 `target.yml` 都是手工维护的共享文件 → 只能用文本级追加。
- 追加位置约定：文件末尾（其后无其它顶层键时最安全）；若末尾存在未闭合的块，仍以"追加到文件末尾 + 前置空行"为准（本 key 只处理
  「无 `rag:` 段」的情况，不做插入式归位，降低风险）。

## 2. D-201 模板常量放新模块（而非塞进 `mw.py`）

- `mw.py` 已 ~4700 行，`_cmd_rag_*` 与 argparse 混在同一文件；模板文本是可被测试与手册引用的**数据**，
  放 `rag_templates.py` 便于 `test_rag_init.py` 与手册 parity 直接 import（也避免手册去 grep `mw.py` 的字符串）。
- 既有同类：`mw_common.py` 承载跨文件共享常量（`RAG_FIELD_CAMEL`、`RAG_TRANSPORT_VALUES`）。

## 3. D-202/D-203 默认落项目层 + `enabled: []`

- 上位 design（`mw-rag-integration/design.md:148`）：`enabled: string[]  项目启用集（缺省 = 全关）`。
  两侧实现一致：`_rag_finalize_target`（`enabled_raw is None → []`）与 `rag/config.ts::parseEnabled`（`undefined → []`）。
- 因此模板写 `enabled: []` = **零影响**，与 AC-001（没有 `rag:` 段或 `enabled: []` → 工具 0 / 注入 0）自洽；
  若模板默认启用占位服务，则任何 `mw rag init` 之后的项目都会在会话启动时对 `localhost:8100` 探活（5s×N）并给工具打
  `[unreachable at session start]`，与"init 不该有副作用"（D-208）冲突。
- 落到 HOME 的默认值否：`machine_rag_servers_path` 的解析顺序是 `MW_RAG_SERVERS_FILE` → `MW_RAG_SERVERS_HOME` → `HOME` → `USERPROFILE`；
  默认写 HOME 会让"试一下 init"意外修改用户的全局配置 → 故默认项目层，机器层用 `--machine` 显式请求（测试用 `MW_RAG_SERVERS_HOME` 指向临时目录）。

## 4. D-205 退出码参照

- 上位 README 已有退出码表：`list`/`probe` = 0 成功、1 配置错；`sync` = 0/1；`audit` = 0/1/2。
  新命令沿用同族语义（0 达成 / 1 拒绝 / 2 用法），保持 `mw rag` 子命令族一致。

## 5. D-207 手册体例参照

- `packages/multi-workers/docs/dual-toolchain-practice-guide.md`：分节 + 可复制命令块 + 字段/退出码表 → 本手册沿用。
- 用户原话要求「每个配置文件都有示例可以直接复制粘贴修改字段就可用，每个字段都要有注释说明，比如 `source` 是干什么的」
  → 逐字段表必须含「是什么 / 取值与默认 / 举例 / 写错的后果」四列（VC-205/VC-209 钉住前两列与诚实性）。

## 6. 被否方案

| 方案 | 否掉原因 |
|---|---|
| 交互式 `rag init`（逐项询问） | 用户明确要"没有输入的按示例写成模板"；交互在 worker/CI 场景必挂（VC-204） |
| 用 YAML round-trip 改 `target.yml` | 毁注释与其他段（D-204） |
| 模板默认 `enabled: [example]` | 让每个 init 过的项目都去探活占位 URL（D-203） |
| 默认写 `~/.agents/rag-servers.yml` | 意外改用户全局配置（D-202） |
| 手册手抄模板文本 | 与 CLI 输出漂移，复发 F-5/P-008 类缺陷（D-201 + VC-206） |
