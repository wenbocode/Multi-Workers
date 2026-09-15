# Task T-01: mw_common.py 凭证解析 + providers.json 新 schema

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-016, AC-017]
- vc_refs: [VC-017, VC-018]
- pattern_refs: []

## 描述
新建 `packages/multi-workers/mw_common.py`，实现凭证声明式解析（design D-003）：
1. `load_providers(path) -> ProvidersConfig`：读新 schema（顶层 `credentials` + `providers` 两节），文件缺失时返回内置默认（与仓库 providers.json 同构）
2. `resolve_credential(cred_cfg, env) -> str | None`：按 `sources` 顺序尝试（env → file）；file 源支持 `format: toml|json|plain` + `field` 点路径（如 `auth.api_key`）+ `~` 展开（toml 用 tomllib，3.11+；缺失则该源跳过）
3. `credential_env_names(config) -> set[str]`：全部声明 env 名（供 launcher strip 集合推导）
4. `providers.json` 迁移为新 schema：credentials（anthropic / anthropic-auth / deepseek / timi，timi 含 `~/.timi-anthropic-proxy/config.toml` file 源）+ providers（claude / claude-cli / deepseek / timi）
5. 路由查找辅助：`route_for(cli, provider) -> RouteConfig`（含 claude→claude-cli 默认映射，迁移自 launcher._build_env 内联逻辑）

不改动 launcher.py/mw.py（T-03/T-05/T-06 接入）。

## 输入
- 依赖文件: `packages/multi-workers/providers.json`（现 schema）
- 依赖 Task: 无
- AC 约束:
  > AC-016: 在 providers 配置中为某路由声明配置文件凭证来源（文件路径 + 字段定位）的条件下，launcher 从该文件读取凭证并完成该路由预检与 worker env 注入，无需设置对应 env var
  > AC-017: 在仅修改 providers 配置的条件下，预检、env 构建、doctor 输出反映新配置，launcher.py / mw.py 代码零改动

## 预期产出
- `packages/multi-workers/mw_common.py`
- `packages/multi-workers/providers.json`（新 schema）
- `packages/multi-workers/test_common.py`（env 源 / file toml+点路径 / json / plain / 全缺 None / ~ 展开 / 内置默认）
- 验证方式: VC-017（file 源解析单测）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-08-28 18:11 | 实现并通过单测（见下） | PASS: 相关 pytest 用例全绿 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
