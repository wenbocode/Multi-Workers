from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
assert sys.dont_write_bytecode
(HERE/'ledger-first-failure.md').write_text('Initial ledger-probe.mjs rc1 at header assertion: worker evidence report.md and final output.md have different change tables. Actual output.md has the directory-labelled table header; report.md does not. Preserve initial probe, test both real documents in fresh probe2. No product/parser/worker records modified.\n',encoding='utf-8')
text=(HERE/'ledger-probe.mjs').read_text(encoding='utf-8')
text=text.replace("const report=fs.readFileSync(reportPath,'utf8');","const evidenceReport=fs.readFileSync(reportPath,'utf8');\nconst report=fs.readFileSync(path.join(worker,'output.md'),'utf8');")
text=text.replace("original,synthetic_header_only:synthetic", "original,evidence_report_ledger:diffLedger(evidenceReport,trace,{projectRoot:root,role:'coding'}),synthetic_header_only:synthetic")
text=text.replace("'ledger-probe.json'","'ledger-probe2.json'")
(HERE/'ledger-probe2.mjs').write_text(text,encoding='utf-8',newline='\n')
