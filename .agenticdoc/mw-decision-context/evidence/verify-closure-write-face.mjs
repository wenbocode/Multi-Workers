import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parseWriteFace, parseWriteFaceEntries, writeFacesOverlap } from '../../../packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts';
const base = resolve('.');
const card = parseWriteFace(readFileSync('.agenticdoc/mw-decision-context/tasks/T08-closure-fixes.md', 'utf8'), {base, caseInsensitive:true});
const task = parseWriteFace(readFileSync('.agenticdoc/mw-decision-context/workers/dc-t08-closure-fixes-r2/task.md', 'utf8'), {base, caseInsensitive:true});
if (card.kind !== 'declared' || task.kind !== 'declared') throw new Error('undeclared carrier');
const paths = card.face.entries.filter(p => p.startsWith('packages/'));
if(paths.length !== 10 || task.face.entries.filter(p => p.startsWith('packages/')).length !== 10) throw new Error('wrong path count');
for(const p of paths){
 const target = parseWriteFaceEntries([resolve(p)], {base, caseInsensitive:true});
 if(target.kind !== 'declared' || writeFacesOverlap(target.face, task.face) === null) throw new Error(`unmatched ${p}`);
}
console.log(JSON.stringify({utc:new Date().toISOString(),run:'dc-t08-closure-fixes-r2',expected:10,matched:10,entries:task.face.entries}));
