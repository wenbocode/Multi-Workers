# Task T-3: `/mw doctor` 显示 RAG 行

## 元信息
- Stage: 2
- 依赖: **T-2 必须先完成**（同一文件 `pm/ui-bridge.ts`，且 `shared/mw-runner.ts` 也会被两者触碰）
- 风险: 低
- Agent: coding worker
- ac_refs: [AC-304, AC-305]
- vc_refs: [VC-309, VC-310]

## 背景（实测）

- Python 已经产出数据：`mw.py:517` `report["rag"] = _doctor_rag(project_dir)`；`_doctor_rag`（`mw.py:2248`）字段集：
  `exists / machine_file / project_file / skill{status,…} / error? / enabled[] / default_server / fingerprint / probe{name:{reachable,transport,error}} / required_missing`。
- Python 的文本行由 `_format_rag_doctor_line`（`mw.py:2297`）渲染，形如：
  - `rag: not enabled (skill missing)`
  - `rag: ERROR - rag server 'x': adapter must be 'overcode-v1'`
  - `rag: enabled=A, B; probe=A=reachable, B=unreachable; fingerprint=436b6a35ff60; skill=installed; required_missing=2`
- TS 侧 `formatDoctorReport`（`pm/ui-bridge.ts:1452`）**没有** rag 行；`DoctorJson`（`shared/mw-runner.ts:341`）也无 `rag` 字段。

## 交付物

1. `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`
   - `DoctorJson` 增加可选 `rag?: { exists?: boolean; machine_file?: string | null; project_file?: string | null; skill?: { status?: string; [k: string]: unknown }; error?: string; enabled?: string[]; default_server?: string | null; fingerprint?: string | null; probe?: Record<string, { reachable?: boolean; transport?: string; error?: string | null }>; required_missing?: number }`（全可选，字段名与 Python 一致）。
2. `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
   - 导出纯函数 `formatRagDoctorLine(rag: NonNullable<DoctorJson["rag"]>): string`，渲染规则**逐字**对齐 `mw.py:_format_rag_doctor_line`（含分隔符 `; `、`probe=A=reachable, B=unreachable` 的逗号+空格、fingerprint 取**前 12 位**、`required_missing>0` 才追加 `; required_missing=N`、`skill` 缺失显示 `unknown`、`error` 优先）；
   - `formatDoctorReport` 在 `report.rag` 存在时把该行插到合适位置（建议紧接 `派发模型` 行之后，或紧随“服务”行——实现自定，但要有测试断言它出现且只出现一次）；`report.rag` 缺失时**不出现**该行且不抛异常。

## 测试（追加到 `packages/coding-agent/test/suite/rag-window.test.ts`）

- VC-309（跨语言逐字一致）：对三组 fixture/临时项目
  (a) 未启用（`enabled: []`）、(b) 配置错误（如 `adapter: v2`）、(c) 已启用且 probe 不可达（用 `127.0.0.1:9xxx` 避免 5s 与网络依赖），
  跑 `python mw.py doctor --project=<tmp> --json` 取 `report.rag` 喂给 `formatRagDoctorLine`，
  同时跑 `python mw.py doctor --project=<tmp>`（非 JSON）取其中 `rag: ` 开头的那一行，断言**两串逐字相等**。
  子进程显式 `encoding: "utf8"`；临时项目与 `MW_RAG_SERVERS_HOME` 都放 `os.tmpdir()`。
- VC-310：`formatDoctorReport({...} without rag...)` 的输出不含 `rag:`；带 `rag` 时恰好出现一次。

## 约束

- 只改 `shared/mw-runner.ts`、`pm/ui-bridge.ts`、`test/suite/rag-window.test.ts`；不改 T-1/T-2 已交付的测试用例与源文件其它部分。
- 不改 `mw.py`/`mw_common.py`（Python 行为零改动；若发现 Python 行渲染有问题，写进报告不要改）。
- 无 `any`（`rap` 类型按上面的形状写全）；`[VERIFY]` 用 `process.stdout.write`。
- 不 commit。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-window.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
cd H:/git/Multi-Workers && npm run check
```

## 报告要求

最终消息给出：改动文件、测试计数、`[VERIFY]` 行原文（含三组 fixture 的 TS 串 == Python 串 实测结果）、偏离与未覆盖项。
