// Full L1 verification run for T-17
import { StateManager } from '../coding-agent/src/extensions/agent-team-loop/pm/state-manager.ts';
import { dispatchTask } from '../coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts';
import { WorkerStore } from '../coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts';
import { IndexStore } from '../coding-agent/src/extensions/agent-team-loop/shared/index-store.ts';
import { writeOutput, appendTrace } from '../coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts';
import { runPhases } from '../coding-agent/src/extensions/agent-team-loop/worker/phase-runner.ts';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

const results: Array<{id: string; pass: boolean; msg: string}> = [];
const p = (id: string, msg: string) => results.push({id, pass: true, msg});
const f = (id: string, msg: string) => results.push({id, pass: false, msg});

async function main() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'l1-full-'));
  const root = tmp;
  const key = 'task-l1';
  const taskDir = path.join(tmp, key);
  fs.mkdirSync(taskDir, {recursive: true});

  // VC-038: WorkerStore two entries
  const ws = new WorkerStore(root);
  await ws.upsert({taskKey: 'k1', status: 'pending', cli: 'pi', provider: '', taskPath: '/t1', dispatchedAt: '', updatedAt: ''});
  await ws.upsert({taskKey: 'k2', status: 'running', cli: 'codex', provider: '', taskPath: '/t2', dispatchedAt: '', updatedAt: ''});
  const all = ws.readAll();
  if (all.length === 2) p('VC-038', 'WorkerStore two entries');
  else f('VC-038', `Expected 2, got ${all.length}`);

  // VC-041: 7-col format
  const wFile = path.join(root, '_workers.parallel');
  const lines = fs.readFileSync(wFile, 'utf8').split('\n').filter(l => l.trim());
  if (lines.every(l => l.split(' | ').length === 7)) p('VC-041', '_workers.parallel 7-col');
  else f('VC-041', `Bad: ${lines.find(l => l.split(' | ').length !== 7) ?? lines[0]}`);

  // VC-040: invalid phase rejected
  const sm = new StateManager(root, key);
  let threw = false;
  try { await sm.write({phase: 'WRONG' as any}); } catch { threw = true; }
  if (threw) p('VC-040', 'Invalid phase rejected');
  else f('VC-040', 'Should throw');

  // VC-018/019
  writeOutput({taskKey: key, agenticdocRoot: root, exitCode: 0, summary: 'Done', changedFiles: ['x.ts'], verificationSteps: 'npm test', exitReason: 'OK'});
  const out = fs.readFileSync(path.join(taskDir, 'output.md'), 'utf8');
  const has4 = ['## Summary','## Changed Files','## Verification Steps','## Exit Reason'].every(s => out.includes(s));
  if (has4 && out.length > 50) p('VC-018/019', 'exit 0 4 sections >50 bytes');
  else f('VC-018/019', `ok=${has4} len=${out.length}`);

  // VC-042/043/044
  writeOutput({taskKey: key, agenticdocRoot: root, exitCode: 1, summary: 'Err', exitReason: 'bad'});
  if (fs.readFileSync(path.join(taskDir,'output.md'),'utf8').includes('## Exit Reason')) p('VC-042','exit 1 Exit Reason');
  else f('VC-042','exit 1 missing Exit Reason');

  writeOutput({taskKey: key, agenticdocRoot: root, exitCode: 2, summary: 'Need', questions: 'What?'});
  if (fs.readFileSync(path.join(taskDir,'output.md'),'utf8').includes('## Questions')) p('VC-043','exit 2 Questions');
  else f('VC-043','exit 2 missing Questions');

  writeOutput({taskKey: key, agenticdocRoot: root, exitCode: 130, summary: 'Cancelled'});
  if (fs.existsSync(path.join(taskDir,'output.md'))) p('VC-044','exit 130 file exists');
  else f('VC-044','exit 130 missing');

  // VC-020: appendTrace
  appendTrace(key, root, 'tool_call bash');
  const trace = fs.readFileSync(path.join(taskDir,'trace.log'),'utf8');
  if (trace.includes('[FLOW]')) p('VC-020','trace [FLOW]');
  else f('VC-020','trace missing [FLOW]');

  // VC-024/025/026
  const tmpPhase = fs.mkdtempSync(path.join(os.tmpdir(), 'l1-ph-'));
  const pKey = 'ph-key';
  fs.mkdirSync(path.join(tmpPhase, pKey), {recursive: true});
  const pr = await runPhases([{name: 'step1',prompt:''},{name:'step2',prompt:''}], {taskKey: pKey, agenticdocRoot: tmpPhase, pi: {} as any});
  const ph1 = path.join(tmpPhase, pKey, 'progress', 'phase-1.md');
  const trph = path.join(tmpPhase, pKey, 'trace.log');
  if (fs.existsSync(ph1) && fs.readFileSync(ph1,'utf8').length>20) p('VC-024','phase-1.md >20b'); else f('VC-024','phase-1.md short');
  if (fs.existsSync(trph) && fs.readFileSync(trph,'utf8').includes('[GOAL_CHECK]')) p('VC-025','[GOAL_CHECK]'); else f('VC-025','no [GOAL_CHECK]');
  if (typeof pr[0].goalMtime==='number') p('VC-026','goalMtime number'); else f('VC-026','goalMtime type');
  fs.rmSync(tmpPhase,{recursive:true});

  // VC-036: IndexStore 7-col
  const is = new IndexStore(root);
  await is.upsert({key:'my-key',status:'active',phase:'EXECUTE',claimId:'123',deps:'',desc:'test',updated:new Date().toISOString()});
  const idxLines = fs.readFileSync(path.join(root,'_index.parallel'),'utf8').trim().split('\n');
  if (idxLines.every(l=>l.split(' | ').length===7)) p('VC-036','_index.parallel 7-col'); else f('VC-036',`bad: ${idxLines[0]}`);

  // VC-041-dispatch
  await dispatchTask({taskKey:'disp-1',status:'pending',cli:'pi',provider:'',taskPath:'/t'}, ws);
  const dLine = fs.readFileSync(path.join(root,'_workers.parallel'),'utf8').split('\n').find(l=>l.includes('disp-1'))||'';
  const dCols = dLine.split(' | ');
  const iso = /^\d{4}-\d{2}-\d{2}T/.test(dCols[5]?.trim()||'');
  if (iso) p('VC-041-disp','ISO 8601 timestamps'); else f('VC-041-disp',`bad ts: ${dCols[5]}`);

  fs.rmSync(tmp,{recursive:true});

  console.log('\n====== L1 Summary ======');
  const passed = results.filter(r=>r.pass);
  const failed = results.filter(r=>!r.pass);
  for (const r of results) console.log(`${r.pass?'PASS':'FAIL'}: ${r.id} — ${r.msg}`);
  console.log(`\nTotal: ${results.length} | PASS: ${passed.length} | FAIL: ${failed.length}`);
  if (failed.length>0) process.exit(1);
}

main().catch(e => { console.error(e); process.exit(1); });
