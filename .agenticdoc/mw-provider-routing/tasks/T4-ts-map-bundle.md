# Task T4: TS prefix map + 重建发布物

- 状态: done
- ac_refs: AC-005
- 来源: plan.md T4

## 内容

1. `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts`：`PROVIDER_ID_TO_PREFIX` 加 `"zai-coding-cn": "zai"`（与 mw_common 双侧同步契约）
2. vitest 侧 map 断言（既有 dispatch-models 测试文件追加或新建）
3. 重建扩展 bundle + 全局安装 + dist（`python packages\multi-workers\mw.py build --install`），dist 与 src 同 commit 提交

## 测试点（VC-010）

- TS: PROVIDER_ID_TO_PREFIX["zai-coding-cn"] === "zai"
- py: mw_common.MODEL_PREFIX_TO_PI_PROVIDER["zai"] === "zai-coding-cn"

## 完成判据

- `npm run check` 全绿；vitest 新断言 PASS
