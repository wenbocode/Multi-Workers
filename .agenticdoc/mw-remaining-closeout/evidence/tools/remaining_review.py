import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
record = json.loads((root / '.tmp/remaining-release-stage/stage.json').read_bytes())

def owners(name):
    if name.startswith('packages/ai/dist/') or name.endswith('generate-models.ts') or name == 'packages/ai/CHANGELOG.md':
        return 'mw-zai-glm54 / mw-zai-glm54-release'
    if name in ('biome.json', 'scripts/check-ts-relative-imports.mjs') or name.startswith('packages/ai/'):
        return 'mw-repo-check-baseline / mw-remaining-closeout'
    if 'issue' in name:
        return 'mw-issue-feedback'
    if 'duty' in name:
        return 'mw-duty-followup'
    if 'version' in name:
        return 'mw-runtime-version / mw-pi-version'
    if 'ue-continue-develop-frame' in name or 'ue_frame_install' in name:
        return 'ue-frame-install-generate'
    if any(token in name for token in ('contract_guard', 'signoff', 'contract_freeze')):
        return 'mw-signoff-freeze-metadata / mw-pm-default-evidence-signoff'
    if 'claim' in name or 'active_projection' in name or 'worker-crosskey' in name:
        return 'mw-window-claim-isolation'
    if any(token in name for token in ('engine-policy', 'engine_policy', 'dual.json')):
        return 'mw-dual-engine-policy / mw-dual-build-artifacts / mw-dual-ue-runtime-outputs'
    if any(token in name for token in ('dp-', 'dp_', 'decision_context', 'decision_dashboard', 'file-evidence', 'material-validation')):
        return 'mw-dp-material-pipeline / mw-dp-consolidation'
    if name.endswith('mw.py') or name.endswith('ui-bridge.ts'):
        return 'mw-signoff-freeze-metadata / ue-frame-install-generate / mw-pi-version'
    return 'mw-remaining-closeout（共享接线、原格式调整与回归收尾）'

lines = [
    '# 剩余开发收尾 Review List（2026-11-24）', '',
    '本轮执行 key：`mw-remaining-closeout`。原 key 保留原验收与失败历史；本轮负责接续纠错、当前源码复验、精确提交及冻结安装。', '',
    '| 处理项 | 原 key | 当前结果 |', '| --- | --- | --- |',
    '| 额外可写根 | mw-dual-additional-write-roots | 已提交 4bcdbccd5 并全局安装；本轮继承该版本，不重复修改或抢占原 PM |',
    '| 冻结签收元数据 | mw-signoff-freeze-metadata / mw-pm-default-evidence-signoff | 纳入当前源码联合验证与冻结候选；保留全部签收证据检查 |',
    '| UE 插件框架安装 | ue-frame-install-generate | 纳入 CLI、Pi 适配与模板；修正测试夹具缺少 testcase 对应 gate，未放宽生产门禁 |',
    '| 检查基线 | mw-repo-check-baseline | 保留 Biome 排除；TS import 检查跳过运行目录；模型检查快照固定为 90ace0f6f 的明确目录 |',
    '| 值守 F3 | mw-duty-followup | 修正未发通知却显示可发送、reserved 崩溃后误认 queued 两类问题；30 项永久回归通过 |',
    '| 运行版本入口 | mw-runtime-version / mw-pi-version | CLI、窗口入口与历史回归纳入统一复验及冻结候选 |',
    '| 模型目录 | mw-zai-glm54 / mw-zai-glm54-release | 保留当前运行目录及 GLM-5.4；运行目录与检查快照各自记录来源 |',
    '| 遗留测试 | mw-issue-feedback / mw-window-claim-isolation / mw-dp-material-pipeline / mw-dp-consolidation | 按当前配置、注册及证据合同修正夹具，不减少权限、身份和证据拒绝断言 |',
    '| AgenticTask 签收适用性 | mw-pm-default-evidence-signoff | 原开发克隆保持 df8ecf6 + 未提交字节；独立审查克隆承载同样六个文件，54 项回归通过 |', '',
    '## 验证与运行版本', '',
    '- 当前根检查和定向回归的完整结果位于 `.agenticdoc/mw-remaining-closeout/evidence/`；以最终日志和命令退出码为准，早期红测保留。',
    '- 冻结候选：`mw-remaining-closeout-20261124`；MW 扩展自检与 pi 编译通过。最终提交、激活及入口核对结果补记在本 key 的 `achieved.md`。',
    '- 本轮为 Codex 自验；不将自验称为新的独立复核，也不将旧 SDD key 的阶段直接手改为 DONE。真实 UE/UBT、带费用模型请求及 RenderPerformance 试点不属于本次离线收尾。',
    '- AgenticTask 新版本远端发布及八项目再次升级，遵守用户此前“发布前再确认”的约定；准备好的版本与当前已安装 df8ecf6 分开记录。', '',
    '## 精确文件归属', '',
    '本表对应 `evidence/scoped-files.json` 的冻结输入。生成的其他 dist、历史运行日志、临时目录及其他窗口台账不混入源码提交。', '',
    '| 文件 | 原 key / 收尾 key |', '| --- | --- |',
]
lines += [f'| `{name}` | {owners(name)} |' for name in record['paths']]
lines += ['', 'AgenticTask 独立审查克隆：`.mw/agentictask-signoff-review`。其六个文件为 `scripts/`、`claude/scripts/`、`core/scripts/` 下各自的 `advance_phase.py` 与 `test_advance_phase.py`。', '']
(root / 'docs/mw-remaining-review-list-20261124.md').write_text('\n'.join(lines), encoding='utf-8')
print('Wrote review list for', len(record['paths']), 'scoped files')
