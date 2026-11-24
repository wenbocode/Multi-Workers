// Offline independent reviewer provider/CLI stand-in for T15-B. It ACTUALLY
// consumes the worker deliverable and RECOMPUTES the declared computation from
// its inputs. Verdict is a function of the consumed bytes (content-based),
// never a hardcoded pass. No network, no paid provider, no signing, no QG.
'use strict';
const fs = require('node:fs');
const crypto = require('node:crypto');

const deliverable = process.argv[2];
const reviewOut = process.argv[3];
if (!deliverable || !reviewOut) {
  console.error('usage: fake-reviewer.cjs <deliverable> <review-out>');
  process.exit(2);
}

const raw = fs.readFileSync(deliverable); // exact producer bytes consumed
const producerSha256 = crypto.createHash('sha256').update(raw).digest('hex');

let verdict = 'fail';
let checks = {};
let recomputed = null;
let error = null;
try {
  const doc = JSON.parse(raw.toString('utf8'));
  const N = Number(doc.inputs && doc.inputs.N);
  let sumSq = 0;
  const parts = [];
  for (let i = 1; i <= N; i += 1) {
    sumSq += i * i;
    parts.push(String(i));
  }
  const seq = parts.join(',');
  const seqSha = crypto.createHash('sha256').update(seq, 'utf8').digest('hex');
  recomputed = { sum_sq: sumSq, seq_sha256: seqSha };
  checks = {
    producer_is_fake_worker: doc.producer === 'fake-worker.cjs',
    sum_sq_matches_recompute: !!(doc.result && doc.result.sum_sq === sumSq),
    seq_sha256_matches_recompute: !!(doc.result && doc.result.seq_sha256 === seqSha),
    card_is_worker_card: doc.card === 'worker-card.md',
  };
  verdict = Object.values(checks).every(Boolean) ? 'pass' : 'fail';
} catch (e) {
  error = String(e && e.message ? e.message : e);
  verdict = 'fail';
}

const review = {
  reviewer: 'fake-reviewer.cjs',
  producer_deliverable: deliverable,
  producer_sha256: producerSha256,
  producer_bytes: raw.length,
  recomputed,
  checks,
  verdict,
  error,
  observed_at: new Date().toISOString(),
};
const text = JSON.stringify(review, null, 2) + '\n';
fs.writeFileSync(reviewOut, text, 'utf8');
console.log(JSON.stringify({
  reviewer: 'fake-reviewer.cjs',
  verdict,
  producer_sha256: producerSha256,
  checks,
}));
