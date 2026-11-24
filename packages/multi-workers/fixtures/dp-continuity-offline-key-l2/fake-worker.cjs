// Offline worker provider/CLI stand-in for T15-B (isolated fake, no network,
// no paid provider, no LLM). Produces one deterministic, recomputable
// deliverable. It never decides pass/fail and never signs.
'use strict';
const fs = require('node:fs');
const crypto = require('node:crypto');

const out = process.argv[2];
if (!out) {
  console.error('usage: fake-worker.cjs <deliverable>');
  process.exit(2);
}

const N = 64;
let sumSq = 0;
const parts = [];
for (let i = 1; i <= N; i += 1) {
  sumSq += i * i;
  parts.push(String(i));
}
const seq = parts.join(',');
const seqSha = crypto.createHash('sha256').update(seq, 'utf8').digest('hex');

const doc = {
  producer: 'fake-worker.cjs',
  card: 'worker-card.md',
  inputs: { N },
  result: { sum_sq: sumSq, seq_sha256: seqSha },
};
const text = JSON.stringify(doc, null, 2) + '\n';
fs.writeFileSync(out, text, 'utf8');
console.log(JSON.stringify({
  producer: 'fake-worker.cjs',
  N,
  sum_sq: sumSq,
  seq_sha256: seqSha,
  bytes: Buffer.byteLength(text),
}));
