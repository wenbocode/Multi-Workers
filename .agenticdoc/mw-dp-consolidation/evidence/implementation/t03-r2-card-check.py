from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[4]
key = root / '.agenticdoc/mw-dp-consolidation'
source = key / 'tasks/isolated/T03-protocol.md'
card = key / 'tasks/isolated/T03-protocol-r2.md'
assert not card.exists(), 'R2 card exists; read before changing'
expected = {
 'decision_points.py': 'a3fb1fe8f3a9caea2a6a4acc660298ca6d2cb9921418c152025c401279089047',
 'decide_registry.json': 'cc017e343f2f7702cf2fcdafc1239d543be472b4e6ab6b92d6adaaee7a06c604',
 'test_decide_registry_contract.py': '4c6aedadca32dd26316a5d18407dc1e7889a62b986b6e6860f973d908878c1d0',
 'test_dp_consolidation_registry.py': 'af20145ead7a031a9ec5ca5ffd4227a725ef2f3615111fda9423f3f2d80b5a97',
}
checks = []
for name, digest in expected.items():
 p = key / 'implementation-worktree/packages/multi-workers' / name
 data = p.read_bytes()
 actual = hashlib.sha256(data).hexdigest()
 assert actual == digest, (name, actual, digest)
 assert not p.is_symlink()
 assert not p.samefile(root / 'packages/multi-workers' / name) if (root / 'packages/multi-workers' / name).exists() else True
 checks.append({'path': str(p.relative_to(root)), 'sha256': actual, 'bytes': len(data), 'crlf': data.count(b'\r\n'), 'bare_lf': data.count(b'\n') - data.count(b'\r\n')})
text = source.read_text(encoding='utf-8')
assert hashlib.sha256(source.read_bytes()).hexdigest() == '083b206d9ec9ae9dab4a582c4b01f3187aba29936e0687b41f9856d645796a60'
text = text.replace('evidence/implementation/dpc-t03-protocol/**', 'evidence/implementation/dpc-t03-protocol/rework-r2/**')
text = text.replace('# T03 —', '# T03-R2 —')
text = text.replace('代码状态：未开始；验证状态：未验证；task状态：not-queued；没有执行证据。', '本次尝试代码状态：未开始；验证状态：需复验；task状态：not-queued。原T03真实done/exit0/acked及142 passed保留，不代表语义交接通过。')
appendix = '''

## 本次定点返工范围（优先于原初次实现描述）
人工批准见`.agenticdoc/mw-dp-consolidation/evidence/implementation/t03-rework-approval-20261026.md`；原卡tasks/isolated/T03-protocol.md不改；本轮仅修三项已实测缺口，同一逻辑T03非新增DAG任务。PM探针/校验见evidence/implementation/t03-pm-handoff-20261026/{report.md,probe.py,probe.json,check.json}；原报告evidence/implementation/dpc-t03-protocol/report.md只读。
1. 副本decision_points.py:4265的prepared_request_issues缺actor_role时通过：实际请求资格缺失/非法角色必须拒绝，八入口合法角色保持通过。角色参数校验不冒充生产身份认证；不新增self-report/token/TTY授权。纯preparation校验不提前要求模型产出的choice/basis答案。
2. 副本decision_points.py:4226的preparation_issues接受prepared_at='not-an-ISO-timestamp'：按既有ISO时间合同加非法/缺失/type及合法时间正反例。不凭空扩大合同格式或增加预算/年龄阈值。
3. 副本test_decide_registry_contract.py:443的test_generated_ts_regeneration_belongs_to_t04永久要求旧dp1且拒八新入口，违反后继T04目标。修成可演进的真实契约断言；一并审视同文件约330的all-unwired与432的legacy-TS-row阶段锁，避免后继已获权接线后必须越面改本测试。保留实质字段/字节锁/位置/错误拒绝覆盖，不无条件skip/xfail、删验收、只放宽为任意输入或伪造T04产物。当前旧TS债和合成八入口fixture各明示，合成验证不是T04实际生成/parity/TS通过。
只做本轮三项相关最小差异；原八职责/退役25/53AC-VC/锁/隔离/预算不变。当前四文件hash与PM交接一致；开工仍重新读取四文件EOF、保存本轮before bytes/SHA/EOL及原dirty差异，再写测试行为反例取真实red日志，最小实现后跑原两文件green。不得拿初次T03 collection-error充本轮red，不刷新主树覆盖副本。
证据仅`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t03-protocol/rework-r2/**`，包括脚本、private fixture/home/temp/project、before/after、diff、红绿、路径/禁写核对及report.md；不得改父目录原证据/原worker记录。测试执行最小env、禁插件/cache/pycache、fake backend/零HTTP；导入路径实际绑定副本。只跑上文两文件命令，不调用决策CLI/provider/生成器/服务/全npm check。JSON仅如快照改变时由既有纯函数离线单源生成。
返工交付与最终回复均须五个独立标题：## 结论、## 证据、## 残留与未验证、## 上下文来源、## 改动清单；列出三项逐例红绿证据、合法正例、原四文件及13交接路径新hash、实际修改/未修改、stage-lock处理依据和未覆盖下游。不签全L2或放行T04。scope/资格不明或超预算时如实收口报告，不绕失败/重置watchdog/自行重派。

## 改动历史（R2卡）
- PM新建本轮卡：保留原卡及原worker全部事实，仅收窄新证据子目录并添加已获人工批准的三项返工；本卡尚未派发，不写虚构运行/通过。
'''
text += appendix
for heading in ['## 上下文', '## 要求', '## 写入允许面', '## 写入禁止面', '## 验收命令', '## 改动历史', '## 交付格式']:
 assert heading in text
assert '.agenticdoc/goal.md:5' in text
card.write_text(text, encoding='utf-8', newline='\n')
assert card.read_text(encoding='utf-8') == text
result = {'observed_at': datetime.now(timezone.utc).isoformat(), 'source_card_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'card_path': str(card.relative_to(root)), 'card_sha256': hashlib.sha256(card.read_bytes()).hexdigest(), 'products': checks, 'product_writes': False, 'product_tests_run': False, 'semantic_handoff_verified': False}
result_path = key / 'evidence/implementation/t03-r2-pre-dispatch-check.json'
assert not result_path.exists()
result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
