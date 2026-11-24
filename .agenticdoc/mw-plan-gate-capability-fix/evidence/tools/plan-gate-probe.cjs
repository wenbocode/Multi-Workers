const fs = require('node:fs');
const path = require('node:path');
const { createJiti } = require('jiti');
const root = path.resolve(__dirname, '..');
const jiti = createJiti(__filename, { fsCache: false, moduleCache: false });
const report = JSON.parse(fs.readFileSync(path.join(root, '.agenticdoc/mw-remaining-closeout/evidence/framework-installed.json'), 'utf8'));
(async () => {
    const api = await jiti.import(process.argv[2]);
    const results = report.projects.map(row => ({ project: row.project, ...api.inspectPlanGate(row.project) }));
    fs.writeFileSync(process.argv[3], JSON.stringify({ module: process.argv[2], projects: results }, null, 2));
    console.log(`PLAN → TASKS capability: ${results.filter(row => row.ok).length}/${results.length} projects`);
    if (results.some(row => !row.ok)) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
