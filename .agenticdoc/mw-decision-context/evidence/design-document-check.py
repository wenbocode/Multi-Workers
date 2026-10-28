from pathlib import Path
import hashlib
import re

root = Path(__file__).resolve().parents[1]
spec = (root / 'spec.md').read_text(encoding='utf-8')
design_path = root / 'design.md'
design = design_path.read_text(encoding='utf-8')
# Installed checker R2 uses unquoted pipe edge labels.
normalized = re.sub(r'\|"([^"\n]+)"\|', r'|\1|', design)
if normalized != design:
    design_path.write_text(normalized, encoding='utf-8')
    design = normalized
ac_rows = re.findall(r'^\| (AC-\d{3}) \| (.*?) \|$', spec, re.M)
vc_rows = re.findall(r'^\| (VC-\d{3}) \| (.*?) \| (.*?) \| (.*?) \| (AC-\d{3}) \|$', design, re.M)
mapping = design.split('## §8 AC → VC 映射表', 1)[1].split('## §9', 1)[0]
mapped = re.findall(r'^\| (AC-\d{3}) \| (VC-\d{3}) \|', mapping, re.M)
assert len(ac_rows) == 20 and len(vc_rows) == 20 and len(mapped) == 20
assert {a for a, _ in ac_rows} == {a for a, _ in mapped}
assert {v for v, *_ in vc_rows} == {v for _, v in mapped}
assert all((a, v) in mapped for v, _, _, _, a in vc_rows)
fingerprint = hashlib.sha1('\n'.join(f'{a}: {text}' for a, text in ac_rows).encode('utf-8')).hexdigest()[:12]
vc_by_ac = {a: (v, assertion, layer, output) for v, assertion, layer, output, a in vc_rows}
lines = [
    '# Evidence Requirement: mw-decision-context',
    '',
    '> 设计草案配套证据要求，尚未执行；用户确认设计后冻结。',
    '',
    '## 锁定指纹',
    '| 字段 | 值 |',
    '|---|---|',
    '| spec_path | `.agenticdoc/mw-decision-context/spec.md` |',
    '| spec_locked_at | 2026-10-22T23:37:55+08:00 |',
    f'| ac_fingerprint | {fingerprint} |',
    '| ac_ids | ' + ', '.join(a for a, _ in ac_rows) + ' |',
    '| vc_ids | ' + ', '.join(v for v, *_ in vc_rows) + ' |',
    '',
    '## 充分性口径',
    '- 证据需完整命令、exit、时间、文件快照与真实assertions；打印预期VERIFY行不构成通过。',
    '- 每个复合断言全覆盖：不能用表中单个计数证明整条AC。',
    '- L0静态/L1局部/L2受管生产路径faux或loopback HTTP+DOM分别标注，DOM不等真实浏览器。',
    '- 凭证临时合成隔离、读前spy；不得访问真实用户凭证。模型fixture不是真实Jev效果。',
    '- 实现前正确行为RED/GREEN留原始日志；修后重建旧行为不算test-first。',
    '- 测试fixture必须由真实producer创建，不手填关联/反馈/签收字段冒称接线。',
    '- 新旧辨别、失败sidecar、签收commit必须核真实reader消费；未发生/未写入不推断成功。',
    '- 真实浏览器、真实Jev及平台路径权限验收须另获授权；未执行明列缺口，不用静态PASS豁免。',
]
for ac, text in ac_rows:
    v, assertion, layer, output = vc_by_ac[ac]
    lines.extend([
        '', f'## {ac}: {text}',
        '| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |',
        '|---|---|---|---|',
        f'| {v}完整日志与测试坐标 | {layer} | {assertion}；`{output}` | 全断言实跑PASS，不只输出计数 |',
        '| design.md §5/§6 对应路径 | FLOW/边界/失败证据 | 真实创建、消费、失败和公开读取一致 | 正常与已列边界/异常覆盖，注明未验层 |',
    ])
lines.extend(['', '## 质检门禁使用说明', '逐AC核充分性，研究报告是设计依据不是实现证据；任一缺口不宣称该AC完成。'])
content = '\n'.join(lines) + '\n'
assert not any(ord(c) < 9 or 13 < ord(c) < 32 or ord(c) == 127 for c in content)
(root / 'evidence-requirement.md').write_text(content, encoding='utf-8')
print(f'AC=20 VC=20 mapping=20 coverage=100% fingerprint={fingerprint}')
print('Evidence document shape PASS; generated requirements are not execution results')
