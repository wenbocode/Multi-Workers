"""PM-only R3 card and fresh byte/hash preparation. No product/test execution."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess

KEY = Path(__file__).resolve().parents[2]
ROOT = KEY.parents[1]
WORKTREE = KEY / 'implementation-worktree'
EVIDENCE = KEY / 'evidence/implementation'
R2_CARD = KEY / 'tasks/isolated/T03-protocol-r2.md'
CARD = KEY / 'tasks/isolated/T03-protocol-r3.md'
CHECK = EVIDENCE / 't03-r3-pre-dispatch-check.json'
BASELINE = EVIDENCE / 't03-r3-pre-dispatch'
assert not CARD.exists() and not CHECK.exists() and not BASELINE.exists()
source = R2_CARD.read_bytes()
assert hashlib.sha256(source).hexdigest() == '4e6d63b51dbe420aedf7d7b807eb180477ab54abfefd894e5042691988fdf756'
previous = json.loads((EVIDENCE / 't03-r2-pm-handoff-20261026/check.json').read_text(encoding='utf-8'))
rows = []
BASELINE.mkdir()
for record in previous['files']:
    relative = record['path']
    path = WORKTREE / relative
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == record['sha256'], (relative, digest)
    assert not path.is_symlink()
    live = ROOT / relative
    assert not live.exists() or not path.samefile(live)
    dest = BASELINE / Path(relative).name
    with dest.open('xb') as stream:
        stream.write(data)
    assert dest.read_bytes() == data
    rows.append({'path': relative, 'sha256': digest, 'bytes': len(data), 'crlf': data.count(b'\r\n'), 'bare_lf': data.count(b'\n') - data.count(b'\r\n'), 'live_sha256': hashlib.sha256(live.read_bytes()).hexdigest() if live.exists() else None, 'samefile_live': False})
handoff = json.loads((EVIDENCE / 'dpc-t03-protocol/rework-r2/write-scope-check.json').read_text(encoding='utf-8'))['handoff']
for relative, record in handoff.items():
    assert hashlib.sha256((WORKTREE / relative).read_bytes()).hexdigest() == record['after_sha256'], relative
text = source.decode('utf-8')
ac = text[text.index('## AC摘录及VC合同'):text.index('## 验收命令')]
ac_refs = next(line for line in text.splitlines() if line.startswith('ac_refs:'))
vc_refs = next(line for line in text.splitlines() if line.startswith('vc_refs:'))
product = '.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_registry_contract.py'
worker_evidence = '.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t03-protocol/rework-r3/**'
header = f'''---
type: coding
write_face:
  - {product}
  - {worker_evidence}
{ac_refs}
{vc_refs}
deps: [T01, T02]
execution: worker
---

# T03-R3 — 补齐第三项测试演进残留（同一逻辑T03，有界新尝试）

## 状态
本尝试代码未开始/验证需复验/task not-queued；原T03及R2均done/exit0/acked，事实不改。semantic_handoff_verified=false，T04未派。此卡不是第37/38个逻辑任务或新的目标/预算授权。

## 上下文
项目目标`.agenticdoc/goal.md:5`；锁定spec.md:128/53AC、已批design.md:201/53VC及plan.md、implementation-isolated-dag.json、implementation-isolation.md。具体人工处置evidence/implementation/t03-r3-approval-20261026.md；当前主根为本key，产品root仅implementation-worktree；证据仍归本key。下列AC/VC从原T03/R2逐字继承，原“未锁”注记只是历史，当前已锁，不可改合同。
PM证据evidence/implementation/t03-r2-pm-handoff-20261026/{{report.md,check.py,check.json,probe.json,pm-green.log,pm-probe.log}}；原R2卡只读。当前测试test_decide_registry_contract.py:448解析成功仍强制dp4，:497 post-T04仍强制四旧行，两个active-only合成目标实测拒绝。两validator已局部修复/166绿测，不能再改生产协议或重新实现八入口。PM本轮predispatch baseline在evidence/implementation/t03-r3-pre-dispatch/；开工必须自己读取最新，不刷新copy。

## 要求
唯一产品任务是测试文件内两个相同第三项根因：把已退休编号存在性误当解析成功/合法活矩阵的永久前提。只做相关最小helper/断言与回归修复：
1. 不要求dp4或DP1_ID等旧名字作为解析非空/成功证明。真实parser须能接受八active合法required-field矩阵（无旧行），同时对未解析、截断/重复/非法key及字段异常保留有意义拒绝，不改生产TS/生成器以迎合测试。
2. 迁移阶段可保留当前真实TS债/四旧行的准确内容锁，但post-T04以及后续消费八合同不能永久强制旧行存在；独立只读历史/旧cases仍保持。T04只生成TS，T11才改triage-client，二者并不同时发生，不新增“必须同一轮同时迁移”或其他后继无写权的阶段锁。仅八active的目标矩阵合法；仍存在的旧行不得变更字段或混入未知ID，阶段/非法混合的实质反例不删。
3. 新行为回归写在本卡唯一允许测试文件；先保存真实red（原函数仍坏），再最小修改helper与断言后green。两个断言分别证明，不能用旧collection/测试自身拼写错误冒充产品red。真实TS文本fixture走parser正例，不只monkeypatch解析返回值；覆盖合法pre-T04债、post-T04旧consumer过渡、后继active-only、没有旧DP1_ID的合法新名常量/字面键形态及非法字段/未知ID/空或未解析/重复/混合生成IDs等适用反例。测试形态按已有合同，不自立完整TS解析器或新字段/限制，发现无法面内修复如实报告。
4. 保留本文件原有身份/字段type/位置/字节/枚举/八注册/独立retired/实际wiring声明验证与已修两validator的原验收；不可skip/xfail或删除验收换绿、不放宽任意输入。合成fixture明确标非T04真实生成/parity/接线/TS compile证明。导入测试函数或mock只能测试validator，不伪造业务PASS。

## 写入允许面
- {product}
- {worker_evidence}

## 写入禁止面
除此以外全部禁止。特别：decision_points.py、decide_registry.json、test_dp_consolidation_registry.py及13handoff同名镜像、triage-client.ts/生成TS/生成器/四旧case只读；原T03/R2证据及worker run/output/card、PM state/manifest/approval/baseline只读。活源码/所有框架clone/mirror、pi核心、spec/goal/53AC/VC、他key、config/policy/gate/brake/ledger/凭证/预算/签名、dependency/lock/dist/install/build/restart/commit/push无权。无symlink/junction/hardlink/重copy覆盖，不能重置watchdog、私设timeout/授权/无限重试。原服务dp4不可用不再请求/换渠道/修活桥或伪造receipt；本次由具体人工确认授权正常dispatch而非dp4成功。

## 开工和隔离约束
完整读唯一产品文件、另一验收测试及需要比较的最新只读协议/TS peer/生成TS到实际EOF；read工具分段续读，hash不代EOF。完整读已有本卡引用的两断言/红绿/报告，不覆盖他人dirty。保存当前四文件before/after bytes/SHA/EOL和完整实际diff、13交接hash（表仅一个协议变，两个测试不在13表，应如实区分）；保存其他受保护/主树及原证据边界的before/after，mtime需按真实run起点且不声称独占作者。
所有脚本/log/private fixture/home/project/temp仅本卡evidence，最小env不继承provider/worker/project config，PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1、-p no:cacheprovider；逐实际import/subprocess argv核副本path。Fake backend/无真实HTTP/决策CLI/服务探针；测试通过生产writer的业务project只能独立fixture，不能写源码树/祖先活对象。read-only peer fixture副本限证据内，不造T04已生成。唯一产品改动按edit精确替换，避免全文件format/EOL变化。

'''
tail = '''## 验收命令
- cwd=.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers；`python -m pytest -p no:cacheprovider -q test_decide_registry_contract.py test_dp_consolidation_registry.py`
- 修改测试文件必须实际运行并迭代到通过；完整stdout/stderr/argv/cwd/rc及每项red→green留本卡evidence，不能只报count。只跑上述两文件，额外纯fixture探针可在本卡evidence；不执行T04/T05生成器/JSON再生、TS tests/full suite或npm check。npm run check有write formatter，仅原T32 PM-direct另建保护等价workspace，不在共享树跑。

## 改动历史
PM新建R3卡：用户对上轮具体定点返工问答“继续”，本轮收窄为一个原T03测试文件，继承原15AC/VC和依赖，独立证据rework-r3子集。未改原卡/run/红绿，不回填虚构before/进展。实际派发后PM只在编排记录保存run；worker开始时须补本卡证据原before。

## 交付格式
证据report.md和最终回复均独立五标题：## 结论、## 证据、## 残留与未验证、## 上下文来源、## 改动清单。逐两个残留断言的行为red/green、合法各阶段正例与非法反例、真实parser与合成边界、四文件bytes/SHA/EOL及13handoff hash（不得误报3变在13表内）、主树/原证据/禁止面变化限制、实际diff及EOF来源列清。只签局部测试返工成果，不放行T04/S1/L2/QG/签收；超面/预算/未知资格/新根因如实收口而非扩大或自重派。PM终态全文吸收独立复验后ack，done/acked不直接释放依赖。
'''
card_text = header + ac + tail
for section in ('## 上下文', '## 要求', '## 写入允许面', '## 写入禁止面', '## 验收命令', '## 改动历史', '## 交付格式'):
    assert section in card_text
with CARD.open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(card_text)
assert CARD.read_bytes() == card_text.encode('utf-8')
assert hashlib.sha256(R2_CARD.read_bytes()).hexdigest() == '4e6d63b51dbe420aedf7d7b807eb180477ab54abfefd894e5042691988fdf756'
git = subprocess.run(['git', 'status', '--short'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
(BASELINE / 'git-status.log').write_text(git.stdout + '\nSTDERR:\n' + git.stderr + '\nrc=' + str(git.returncode) + '\n', encoding='utf-8')
result = {'observed_at': datetime.now(timezone.utc).isoformat(), 'key': KEY.name, 'logical_id': 'T03', 'attempt': 'dpc-t03-protocol-r3', 'card': str(CARD.relative_to(ROOT)).replace('\\', '/'), 'card_sha256': hashlib.sha256(CARD.read_bytes()).hexdigest(), 'inherited_card_sha256': hashlib.sha256(source).hexdigest(), 'product_write_face': [product], 'worker_evidence_write_face': worker_evidence, 'current_four_files': rows, 'handoff_verified': len(handoff), 'hand_off': handoff, 'product_writes': False, 'product_tests_run': False, 'semantic_handoff_verified': False, 'git_status_rc': git.returncode}
with CHECK.open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
assert json.loads(CHECK.read_text(encoding='utf-8')) == result
print(json.dumps({k: v for k, v in result.items() if k != 'hand_off'}, ensure_ascii=False, indent=2))
