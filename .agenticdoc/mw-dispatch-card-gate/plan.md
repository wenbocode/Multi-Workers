# Plan: worker 任务投递与回收契约（mw-dispatch-card-gate）

- Key: `mw-dispatch-card-gate`｜日期: 2026-10-12｜上游: `spec.md`（定稿）、`design.md`、`evidence/research/design-envelope-selection-20261012.md`
- 拆卡原则：**写入面互不重叠**（同一文件同一时刻只有一个 worker）；接口在卡内冻结，允许跨卡并行。

## 波次

| Wave | 卡片 | 写入面（唯一归属） | 依赖 |
|---|---|---|---|
| W1 | T-01 信封契约库 | `shared/dispatch-card.ts`（新）+ `test/suite/dispatch-card-envelope.test.ts`（新） | 无 |
| W1 | T-03 服务层兜底 | `packages/multi-workers/launcher.py` + 新 Python 测试 | 无 |
| W1 | T-04 回收契约 | `worker/output-sections.ts`、`worker/output-writer.ts` + 新测试 | 无 |
| W1 | T-06 追溯与一致性 | `packages/multi-workers/autopilot/card_audit.py`（新）+ 新测试 | 无 |
| W2 | T-02 生成端注入 + 工具层校验 | `pm/ui-bridge.ts` + 新测试 | T-01（接口已冻结，可提前开工） |
| W2 | T-05 coding 改动历史 | `worker/worker-file-tool.ts`、`worker/worker-mode.ts` + 新测试 | 无（与 W1 无文件冲突，可并行） |
| W3 | T-07 逃生舱真读 + 类型词汇表收口 | `worker/worker-mode.ts`（在 T-05 之后）、`.mw/dispatch.yml` | T-02、T-05 |
| W3 | T-08 cutover 与运行期证据 | `evidence/runs/**`、changelog | 全部 |

## 冻结接口（T-01 提供，T-02/T-03/T-06 消费）

```ts
export const ENVELOPE_SECTIONS: readonly ["context", "requirements", "deliverables"];
export interface EnvelopeCheck {
  ok: boolean;
  missing: string[];
  type: string;
  detected: { context: string; requirements: string; deliverables: string };
}
export function readEnvelope(cardPath: string): EnvelopeCheck;
export function typeExtrasMissing(type: string, text: string): string[];
```

## 门禁与验证

- 每卡自带验收命令；PM 复核（不采信自报）。
- 全绿后 `npm run check`；再按 D-003 做 cutover（`mw.py build --install --allow-dirty` + 重建 dist + `/mw restart` + `/reload`）并留 `evidence/runs/` 一正一负。
