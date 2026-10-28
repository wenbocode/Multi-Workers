import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parseWriteFace, parseWriteFaceEntries, writeFacesOverlap } from '../../../packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts';
const base = resolve('.');
for (const [run, expected] of [['dc-t08-ts-integration-r2', 15], ['dc-t08-python-integration-r2', 30]]) {
 const parsed = parseWriteFace(readFileSync(resolve('.agenticdoc/mw-decision-context/workers', run, 'task.md'), 'utf8'), {base, caseInsensitive:true});
 if (parsed.kind !== 'declared') throw new Error(`${run}: undeclared`);
 const paths = parsed.face.entries.filter(p => p.startsWith('packages/'));
 let matched = 0;
 for (const p of paths) {
  const target = parseWriteFaceEntries([resolve(p)], {base, caseInsensitive:true});
  if (target.kind !== 'declared' || writeFacesOverlap(target.face, parsed.face) === null) throw new Error(`${run}: unmatched ${p}`);
  matched++;
 }
 if (matched !== expected) throw new Error(`${run}: count ${matched} != ${expected}`);
 console.log(JSON.stringify({run, paths:matched, expected, matched:true}));
}
