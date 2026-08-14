# Task T-15: Extension build 配置（esbuild/tsup）

## 基本信息
- Stage: 6
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-036]
- vc_refs: [VC-028, VC-047]
- pattern_refs: []

## 描述
为 `packages/coding-agent/src/extensions/agent-team-loop/` 配置构建流程，产出单文件预编译 bundle `dist/extensions/agent-team-loop.js`：
- 无外部 npm 依赖（bundle 内联所有依赖，或声明 pi Extension 运行时提供的 external）
- 目标格式：CommonJS 或 ESM（按 pi Extension 加载机制要求）
- 构建工具：优先 esbuild（速度快）或 tsup（封装 esbuild，配置简洁）
- 构建脚本写入 `package.json` scripts 或独立 `build-extension.sh`

确认现有 `packages/coding-agent/` 的 TypeScript 配置（tsconfig.json）和构建工具，避免重复安装。
产物路径：`dist/extensions/agent-team-loop.js`（mw init 从此路径复制）。

## 输入
- 依赖文件: `packages/coding-agent/` 现有 tsconfig.json、package.json
- 依赖 Task: T-07~T-13（Extension 源码需已完整）
- AC 约束:
  > AC-036: mw init 从 dist/extensions/agent-team-loop.js 复制；若文件不存在则 exit 1

## 预期产出
- 构建配置文件（esbuild.config.js 或 tsup.config.ts 或 package.json script）
- `dist/extensions/agent-team-loop.js`（构建产物，验证文件存在且可被 node 加载）
- 验证方式: VC-028（mw init 后 .pi/extensions/agent-team-loop.js 存在）、VC-047（bundle 不存在时 init exit 1）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: 需先确认 packages/coding-agent/ 现有构建配置和 pi Extension 格式要求
- 处置: 实现前 Glob packages/coding-agent/package.json 和 tsconfig.json 确认
