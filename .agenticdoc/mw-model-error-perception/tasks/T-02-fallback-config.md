# T-02: fallback 配置层（mw.py + mw_common.py）

type: coding

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（不引入中心化调度器；Python 后台服务 + 配置守护）。
- spec：`.agenticdoc/mw-model-error-perception/spec.md`（AC-008 配置半、AC-009 预校验半）；design：design.md §3.3（本任务蓝图）、§2 D5、§4 协议契约。
- 关键锚点（TRQ-5 取证，行号自行校对）：
  - dispatch.yml 现有结构与角色/模型默认值解析（resolveDefaults 在 mw_common.py / mw.py）
  - **三处 `_model_write` 整文件重写只带 models map：mw.py:3524/3539/3553——不扩展会静默丢 `fallback_models` 键（本任务核心坑）**
  - `models.<role>` 值被两侧硬校验为单行字符串 → `fallback_models` 必须是**顶层新键**
  - doctor 结构：mw.py doctor 子命令（route/凭证检查器可复用做 fallback 凭证预检 warn）
- 契约（design §4）：顶层 `fallback_models: {<type>: ["provider/model", ...]}`，列表上限 4，格式 `provider/model` 单行；缺省=该类别无备用（行为与现状一致）。

## 要求

1. 配置 schema 与校验：新增顶层 `fallback_models` 读取/校验函数（键=已知 task type 集合，值=1~4 个 `provider/model` 字符串，格式非法/超限报错；大小写与去重规范化）。
2. 三处 `_model_write`（mw.py:3524/3539/3553）改为读-改-写：重写时保留 `fallback_models` 键（整文件重写前先读旧文件提取该键；不得用仅含 models 的新 dict 覆盖）。
3. doctor：新增 fallback 配置检查——格式错误 error；目标 route 缺失或凭证缺失 warn（复用既有 route/credential 检查器，不新增网络探测）。
4. 校验错误信息可机读（供 launcher/doctor 消费），风格对齐既有 config 校验。
5. 禁止：改 launcher.py（T-03 所有）、改 pi 扩展 TS 侧、写 `~/.pi`、改 models.<role> 既有校验语义。

## 写入允许面

- `packages/multi-workers/mw.py`
- `packages/multi-workers/mw_common.py`

## 写入禁止面

- `packages/multi-workers/launcher.py`（T-03 所有）、test_*.py（T-06 所有）、TS 全部、`~/.pi`

## 交付格式

- 修改后的 mw.py / mw_common.py（仅限写入允许面）
- 交付说明：改动点清单、_model_write 保留键的实现方式、doctor 新增检查项；验收命令输出摘要

## 验收命令

```
python -m pytest test_dispatch_models.py test_mw_serve_config_partial.py test_doctor_gates.py -x
python -c "import ast; ast.parse(open('mw.py',encoding='utf-8').read()); ast.parse(open('mw_common.py',encoding='utf-8').read())"
```

- 全绿 + 语法通过；并行说明：launcher.py/test_*.py 由其他并行 worker 负责，其报错不归你修

## 改动历史

- 2026-10-15 任务创建（T-02，Stage 1）
