"""Prepare approved original-task R2 cards and fresh immutable dispatch baselines."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
KEY = Path(__file__).resolve().parents[2]
ROOT = KEY.parents[1]
WT = KEY/'implementation-worktree'
E = KEY/'evidence/implementation/s2-r2-pre-dispatch-20261026'
assert sys.dont_write_bytecode and not E.exists()
old_inventory = json.loads((KEY/'evidence/implementation/t08-pm-handoff-20261026/after-inventory.json').read_text(encoding='utf-8'))
def sha(value):
    return hashlib.sha256(value).hexdigest()
inventory = {p.relative_to(WT).as_posix():sha(p.read_bytes()) for p in WT.rglob('*') if p.is_file()}
assert inventory == old_inventory and len(inventory) == 1883
E.mkdir(parents=True)
def save(name, value):
    (E/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def keep(label, rel, value):
    dest = E/label/rel
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(value)
common = '''## 本次 R2 有界覆盖（优先于下方历史卡文字）
本次是用户明确批准的原逻辑任务定点返工，不是新增逻辑任务或扩大交付。授权：`.agenticdoc/mw-dp-consolidation/evidence/implementation/s2-r2-approval-20261026.md:1`。原卡/原run/原红绿/原报告和PM复验证据全部只读留史；下方AC摘录的旧“未锁”注记是历史，当前完整SPEC/53AC已锁，不能据此放宽。
产品仅本卡frontmatter列出的原隔离文件；证据仅本次rework-r2目录（frontmatter/write_face为准）。先在实际副本完整读当前产品及测试到EOF，保存当前before bytes/SHA/EOL/既有diff，再把缺口写成指定测试内真实业务断言，亲自观察正确行为失败的red后才修改产品；import/collection错误不代行为红。保存所有失败迭代与完整stdout/stderr/rc，不以事后mutation或删原用例代红绿。
所有Python命令，包括静态import、脚本、子进程及临时探针，均python -B且PYTHONDONTWRITEBYTECODE=1；私有minimal UTF8 env、HOME/USERPROFILE/TEMP/project只在本次证据fixture、禁pytest plugin autoload/cache；真实HTTP/CLI/provider/服务和活对象禁用。测试导入路径必须绑实际副本。不得删除14个既有pyc或其他越面文件，不因gitignore/清洁要求/工具守卫拒绝绕写。任何新越面事件原样报告。
只跑本卡唯一assigned pytest文件；不跑生成器/其它测试/npm check/build/install，不改T03/T04、peer/消费者/TS/框架/config/预算/watchdog/权限/live原源/goal/spec或旧证据，不复制或刷新mirror。T06/T07不引入在写T08模块或未交接peer依赖；新发现接口/共享测试需求先报告PM，不能自改DAG或等peer写完偷读冒充独立性。
最后给完整after bytes/EOL/hash与增量diff、每项red→green的断言定位/命令/rc、peer-aware面核对（共享镜像合法peer变更不归自身，净hash不能证明作者独占或历史瞬时无写）、五节报告。只称本层已验证，不称生产授权/L2/真实并发/QG/签收/原stage已通过。普通原任务的终态由PM独立验证后自动决定原DAG后继；worker不得自己派后继、交接通过或改phase。
'''
items = [
('T06','validity','dpc-t06-validity',['decision_validity.py','test_dp_consolidation_concurrency.py'],'''### 本次精确修复与验收重点
读PM `.agenticdoc/mw-dp-consolidation/evidence/implementation/t06-pm-handoff-20261026/report.md:1`、probe.json、supplement.json（九当前失败边界），不能执行会覆盖原证据的PM脚本。
- required successful signoff仅有效finalize；continue/user-confirm保留合法业务菜单但不能判required签收valid。核真实key/matter/scope关联及非空可追溯signoff引用；不要用fixture artifact文本声称生产产物已验；不扩大签收强制范围。当前SignoffRef不记合同等缺口只在本卡可证明范围内修，生产引用解析仍原后继，不造trust源。
- 请求合同变更的相关旧证据不能仅记reason后仍applies/reusable；保留语义等价/不受影响依赖复用、自然语言unknown，不用全字节hash制造全量重审。
- 混合法/非法路径时完整claim请求失败关闭；同owner不同task的同文件active claim不可当clear，合法同任务复入/无冲突正例仍成立；不抢claim或执行锁操作。
- 匹配已存effect记录的非法/缺失状态不能当未执行而proceed；unknown/in-progress保持blocked，已applied去重、明确失败及真实无记录等合法正例按原契约保留，不把所有状态无差别冻结。
证据至少逐项genuine red→green与正向控制，保持pure stdlib模块，无I/O/CLI/conductor/peer imports。唯一测试test_dp_consolidation_concurrency.py。
'''),
('T07','policy','dpc-t07-policy',['decision_policy.py','test_dp_consolidation_recovery.py'],'''### 本次精确修复与验收重点
读PM `.agenticdoc/mw-dp-consolidation/evidence/implementation/t07-pm-handoff-20261026/report.md:1`、probe.json、supplement.json（七负例+已撤policy规则ref换request otherref绕过）；不能执行会覆盖原证据的PM脚本。
- pending-review同时核policy与请求required_scope，缺失/越scope不能给allowed=true空scope；合法非空范围正例保留，事件/到期只触发评估。
- 恢复核policy.recovery.authority_ref及请求引用的适用关系/撤权/范围，不只解析request的otherref。已撤/无关引用不得绕过；但不要盲强制两ref相等而拒绝H11真实新human授权。新授权须可验证明确替代/恢复原停止的关系，不造自报或可编辑文件trust源。生产资格证明不在本层创造。
- halted硬guard验证缺失/非法未知、停止origin未知不默认cleared/技术停止；人工停止/撤权须明确恢复授权，保持硬保护。breaker缺user_disabled/非法未知等不默认为False，伪origin/未知消除证据保持阻塞。
- 保留预算单位/累计消耗、原停止/熔断事实、受控H12来源、合法disable；不修改冻结21键/defaults或设新预算/授权/时限。read-only config只按原只读依赖，不import CLI/conductor/在写T08。
每组真实行为red→green，含合法原引用/受限scope及合法明确新H11human恢复控制。唯一测试test_dp_consolidation_recovery.py。
'''),
('T08','transport','dpc-t08-transport',['decision.py','decision_backends.py','test_dp_consolidation_materials.py'],'''### 本次精确修复与验收重点
读PM `.agenticdoc/mw-dp-consolidation/evidence/implementation/t08-pm-handoff-20261026/report.md:1`、probe.json；不能执行会覆盖原证据的PM脚本。
- max_questions=1等现有边界必须返回明确prepared失败/零业务决定/零HTTP，不让DecisionInputError直接逃逸；不得提高/放宽原额度，保留generic decide契约/原retry-budget/box拒绝。
- replay_check仅明确合法bool可证明hit/miss；null、unknown字符串或其他非法/未知结果失败关闭，不伪造replayed成功/novelty而发请求。true/false正例保留，25retired在replay/credential/backend前拒绝，实际T10store/T23CLI仍后继。
- 同请求choice+basis无默认/补请求、不裁剪核心、timi POST/v1/decisions、jev-latest、bare Authorization保留。缺/错/不适用basis保持业务0。
- 额外核清raw transport成功记录与业务拒绝分层：PM只证generic transport行true与prepared业务false并存，未证明已新增有效业务裁决。不要贸然改冻结generic response/REASON_CODES、增加第二决策账本或越面修T10/T23；若本面能无破坏明确分层则测试证实，否则把准确约束/未覆盖链/后继验收说明写入报告，不用假全链绿解除债。
新pytest行为red→green覆盖cap/非法lookup及控制，fake_http始终阻断真实socket；原73用例保留按合法预期修缺陷，不去跑其它既有套件。唯一测试test_dp_consolidation_materials.py。
''')]
rows = []
all_faces = []
for logical_id, slug, worker, products, detail in items:
    old_card = KEY/f'tasks/isolated/{logical_id}-{slug}.md'
    raw = old_card.read_bytes()
    keep('original-cards',old_card.relative_to(KEY).as_posix(),raw)
    text = raw.decode('utf-8')
    old_evidence = f'.agenticdoc/mw-dp-consolidation/evidence/implementation/{worker}'
    new_evidence = old_evidence+'/rework-r2'
    text = text.replace(old_evidence+'/**',new_evidence+'/**')
    marker = '\n---\n'
    where = text.index(marker,4)+len(marker)
    text = text[:where]+'\n'+common+'\n'+detail+'\n'+text[where:]
    text = text.replace('代码状态：未开始；验证状态：未验证；task状态：not-queued；没有执行证据。','本次R2代码状态：未开始；验证状态：需复验；task状态：not-queued。原任务done/exit0/acked及旧失败留史，本句不代新尝试完成。')
    generator_line = '- 生成器/额外测试仅对应本卡：T03离线registry snapshot writer、T04 `python scripts/gen_decide_registry_ts.py`及`--check`、T05 `python scripts/build_decide_cases.py --out <本卡隔离目录>`；不要其他任务提前生成/覆盖。'
    text = text.replace(generator_line,'- 本R2不运行任何生成器或额外suite，唯一assigned测试按上文。')
    new_card = KEY/f'tasks/isolated/{logical_id}-{slug}-r2.md'
    assert not new_card.exists()
    new_card.write_text(text,encoding='utf-8',newline='\n')
    assert new_card.read_bytes() == text.encode('utf-8')
    file_rows = []
    for name in products:
        rel = 'packages/multi-workers/'+name
        assert rel not in all_faces
        all_faces.append(rel)
        value = (WT/rel).read_bytes()
        keep('before-bytes',rel,value)
        live = ROOT/rel
        live_value = live.read_bytes() if live.exists() else None
        if live_value is not None:
            assert not os.path.samefile(WT/rel,live)
            keep('live-before-bytes',rel,live_value)
        file_rows.append({'path':rel,'sha256':sha(value),'bytes':len(value),'crlf':value.count(b'\r\n'),'bare_lf':value.count(b'\n')-value.count(b'\r\n'),'live_exists':live.exists(),'live_sha256':sha(live_value) if live_value is not None else None})
    old_root = KEY/f'evidence/implementation/{worker}'
    original_evidence = {p.relative_to(old_root).as_posix():sha(p.read_bytes()) for p in old_root.rglob('*') if p.is_file()}
    save(logical_id.lower()+'-original-evidence-inventory.json',original_evidence)
    rows.append({'logical_id':logical_id,'task_key':worker+'-r2','card':new_card.relative_to(ROOT).as_posix(),'card_sha256':sha(new_card.read_bytes()),'original_card_sha256':sha(raw),'product_write_face':[f'.agenticdoc/mw-dp-consolidation/implementation-worktree/{f["path"]}' for f in file_rows],'evidence_write_face':new_evidence+'/**','before_files':file_rows,'original_evidence_files':len(original_evidence),'status':'not-queued','semantic_handoff_verified':False})
    assert old_card.read_bytes() == raw
save('mirror-inventory.json',inventory)
assert len(all_faces) == 7
result = {'observed_at':datetime.now(timezone.utc).isoformat(),'mirror_files':len(inventory),'unchanged_from_pm_t08_inventory':True,'product_paths_disjoint':True,'product_paths':all_faces,'attempts':rows,'original_logical_task_count':36,'new_logical_tasks':0,'cleanup_authorized':False,'dispatch_done':False,'product_tests_run':False,'approval_file':'evidence/implementation/s2-r2-approval-20261026.md'}
save('check.json',result)
assert inventory == {p.relative_to(WT).as_posix():sha(p.read_bytes()) for p in WT.rglob('*') if p.is_file()}
print(json.dumps(result,ensure_ascii=False,indent=2))
