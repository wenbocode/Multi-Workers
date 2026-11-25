"""Install and exercise the distribution in a fresh unrelated module."""
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TEMPLATE = Path(__file__).resolve().parents[1]


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'IndependentModule'
        self.root.mkdir()
        (self.root / 'src').mkdir()
        (self.root / 'src/logic.py').write_text('def execute(value):\n    return value + 1\n', encoding='utf-8')
        (self.root / 'AGENTS.md').write_text('Existing module policy\n', encoding='utf-8')
        self.call(TEMPLATE / 'install.py', '--target', self.root, '--name', 'IndependentModule', '--source-root', 'src')

    def call(self, script, *args, success=True):
        result = subprocess.run([sys.executable, '-B', str(script), *map(str, args)],
                                cwd=self.temp.name, capture_output=True, encoding='utf-8')
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def read(self, name):
        return json.loads((self.root / 'agent' / name).read_text(encoding='utf-8'))

    def write(self, name, value):
        (self.root / 'agent' / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def catalog(self, *args, success=True):
        return self.call(self.root / 'agent/catalog.py', *args, success=success)

    def complete_module(self):
        catalog = self.read('catalog.json')
        catalog['terms'].append(dict(term_id='T-EXEC', path='src/logic.py', symbol='execute', definition='Increment one value', unit=''))
        gate = dict(catalog['gates'][0], gate_id='G-EXEC', term_id='T-EXEC', selection='conditional',
                    trigger='execute change', runner='agent/gates/check_logic.py', requirement='1 becomes 2')
        catalog['gates'].append(gate)
        (self.root / 'agent/gates/check_logic.py').write_text(
            "import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))\nfrom logic import execute\nassert execute(1)==2\nprint('PASS')\n", encoding='utf-8')
        self.write('catalog.json', catalog)
        config = self.read('module.json')
        config['design_status'] = 'ready'
        self.write('module.json', config)
        design = self.root / 'DESIGN.md'
        design.write_text(design.read_text(encoding='utf-8').replace('（草稿）', '')
                          .replace('## 主要 Flow', '[T-EXEC]\n\n## 主要 Flow')
                          .replace('## 生命周期', '[N:execute]\n\n## 生命周期')
                          .replace('## 持久化', '[N:execute]\n\n## 持久化'), encoding='utf-8')
        self.catalog('--write')

    def approve_fixture_gates(self):
        # Synthetic approvals only inside the disposable fixture, never production.
        script = '''from pathlib import Path
import sys,csv,json
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'agent'));import ask
p=root/'agent/gates.csv'
with p.open(encoding='utf-8-sig',newline='') as f:
 reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
records=[]
for gid in dict.fromkeys(r['gate_id'] for r in rows):
 group=[r for r in rows if r['gate_id']==gid];ref='R-FIXTURE-'+gid
 target=root/('agent/logs/'+gid+'.json')
 target.write_text(json.dumps(dict(category='gates',item_id=gid,decision='accepted',item_sha256=ask.item_digest(group,root),confirmed_by='synthetic fixture',confirmed_at='fixture',source_ref='unit test only')),encoding='utf-8')
 for row in group: row.update(status='accepted',decision_ref=ref)
 records.append([ref,group[0]['term_id'],'','human_decision','fixture','',target.relative_to(root).as_posix(),'Synthetic fixture only'])
with p.open('w',encoding='utf-8-sig',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
with (root/'agent/records.csv').open('a',encoding='utf-8',newline='') as f: csv.writer(f).writerows(records)
'''
        path = Path(self.temp.name) / 'approve_fixture.py'
        path.write_text(script, encoding='utf-8')
        self.call(path, self.root)
        self.catalog('--write')

    def test_missing_source_root_is_refused(self):
        other = Path(self.temp.name) / 'NoSource'
        other.mkdir()
        result = self.call(TEMPLATE / 'install.py', '--target', other, '--name', 'NoSource',
                           '--source-root', 'Source', success=False)
        self.assertIn('source-root directory missing', result.stdout)
        self.assertFalse((other / 'agent').exists())

    def test_install_is_local_and_non_destructive(self):
        agent_policy = (self.root / 'AGENTS.md').read_text(encoding='utf-8')
        self.assertIn('Existing module policy', agent_policy)
        self.assertIn('版本控制边界', agent_policy)
        for path in ['AGENTS.md', 'GOAL.md', 'DESIGN.md', 'agent/']:
            self.assertIn(path, agent_policy)
        self.assertIn('不进 CL', agent_policy)
        self.assertFalse((self.root / 'gates').exists())
        self.assertFalse((self.root / 'agent/testcases.csv').exists())
        for file in ['terms.csv', 'testcase.csv', 'gates.csv']:
            self.assertTrue((self.root / 'agent' / file).read_bytes().startswith(b'\xef\xbb\xbf'))
        self.catalog('--check')
        for level in range(4):
            result = self.call(self.root / 'agent/ask.py', '--level', level)
            self.assertIn(json.loads(result.stdout)['status'], ['ok', 'empty'])
        self.call(TEMPLATE / 'install.py', '--target', self.root, '--name', 'Other', success=False)
        self.call(self.root / 'agent/gates/design_gate.py', success=False)

    def test_independent_module_minimal_execution(self):
        self.complete_module()
        self.approve_fixture_gates()
        baseline = Path(self.temp.name) / 'baseline.json'
        self.call(self.root / 'agent/gates/design_gate.py', '--snapshot', baseline)
        result = self.call(self.root / 'agent/gates/regression.py', '--impact', 'T-EXEC', '--baseline', baseline,
                           '--report-root', Path(self.temp.name) / 'runs')
        summary = json.loads(result.stdout)
        self.assertEqual(summary['passed'], 3)
        self.assertLess(len(result.stdout), 1000)
        self.assertEqual(self.read('module.json')['module'], 'IndependentModule')
        for action in ('--refresh-plan', '--refresh', '--help'):
            with self.subTest(action=action):
                rejected = self.call(self.root / 'agent/gates/run.py', '--gate', 'G-DESIGN',
                                     '--', '--baseline', baseline, action, success=False)
                self.assertIn('takes only --baseline', rejected.stdout)

    def test_source_fact_failure_preserves_catalogs(self):
        original = (self.root / 'agent/terms.csv').read_bytes()
        catalog = self.read('catalog.json')
        catalog['terms'][0]['symbol'] = 'InventedSymbol'
        self.write('catalog.json', catalog)
        result = self.catalog('--write', success=False)
        self.assertIn('No source declaration', result.stdout)
        self.assertEqual(original, (self.root / 'agent/terms.csv').read_bytes())

    def test_implementation_change_invalidates_approval(self):
        self.complete_module()
        self.approve_fixture_gates()
        runner = self.root / 'agent/gates/check_logic.py'
        runner.write_text(runner.read_text() + '\n# implementation changed\n')
        result = self.catalog('--write')
        self.assertEqual(json.loads(result.stdout)['invalidated'], ['G-EXEC'])
        self.catalog('--check')
        with (self.root / 'agent/gates.csv').open(encoding='utf-8-sig') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(next(r for r in rows if r['gate_id'] == 'G-EXEC')['status'], 'proposed')
        self.assertEqual(next(r for r in rows if r['gate_id'] == 'G-ASK')['status'], 'accepted')

    def test_config_change_invalidates_gate_approvals(self):
        self.approve_fixture_gates()
        config = self.read('module.json')
        config['ue']['default_map'] = '/Game/Other'
        self.write('module.json', config)
        result = self.catalog('--write')
        self.assertEqual(set(json.loads(result.stdout)['invalidated']), {'G-ASK', 'G-DESIGN'})

    def test_commented_ue_registration_is_not_a_test(self):
        self.complete_module()
        (self.root / 'src/Test.cpp').write_text('// IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFake,"Independent.Fake",0)\n')
        catalog = self.read('catalog.json')
        catalog['testcases'].append(dict(case_id='C-FAKE', term_id='T-EXEC', name='Independent.Fake', path='src/Test.cpp',
            preconditions='fixture', steps='fixture', expected='fixture', command='Automation RunTests Independent.Fake'))
        self.write('catalog.json', catalog)
        self.assertIn('Missing real UE AutomationTest', self.catalog('--write', success=False).stdout)

    def test_removal_requires_opt_in_and_new_review(self):
        self.complete_module()
        self.approve_fixture_gates()
        catalog = self.read('catalog.json')
        catalog['gates'] = [r for r in catalog['gates'] if r['gate_id'] != 'G-EXEC']
        self.write('catalog.json', catalog)
        self.assertIn('Removal requires', self.catalog('--write', success=False).stdout)
        result = json.loads(self.catalog('--write', '--allow-remove').stdout)
        self.assertEqual(result['removed']['gates'], ['G-EXEC'])
        self.assertEqual(set(result['pending']['gates']), {'G-ASK', 'G-DESIGN'})

    def test_invalid_generated_graph_rolls_back(self):
        files = ['terms.csv', 'testcase.csv', 'gates.csv', 'source_nodes.json', 'REVIEW.md']
        before = {name: (self.root / 'agent' / name).read_bytes() for name in files}
        catalog = self.read('catalog.json')
        catalog['gates'].append(dict(catalog['gates'][0], requirement='Conflicting duplicate'))
        self.write('catalog.json', catalog)
        self.assertIn('Inconsistent record', self.catalog('--write', success=False).stdout)
        for name, content in before.items():
            self.assertEqual((self.root / 'agent' / name).read_bytes(), content)

    def test_real_registration_generates_proposed_testcase(self):
        self.complete_module()
        (self.root / 'src/Test.cpp').write_text(
            'IMPLEMENT_SIMPLE_AUTOMATION_TEST(FIndependentSmoke,"Independent.Smoke",0)\n'
            'bool FIndependentSmoke::RunTest(const FString&) { return true; }\n', encoding='utf-8')
        catalog = self.read('catalog.json')
        catalog['testcases'].append(dict(case_id='C-SMOKE', term_id='T-EXEC', name='Independent.Smoke',
            path='src/Test.cpp', preconditions='Synthetic source-registration fixture; not an engine run',
            steps='Run fixture', expected='True', command='Automation RunTests Independent.Smoke'))
        self.write('catalog.json', catalog)
        self.assertIn('Testcase missing impact gate', self.catalog('--write', success=False).stdout)
        catalog['gates'].append(dict(catalog['gates'][-1], case_id='C-SMOKE'))
        self.write('catalog.json', catalog)
        self.catalog('--write')
        with (self.root / 'agent/testcase.csv').open(encoding='utf-8-sig') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(rows[0]['name'], 'Independent.Smoke')
        self.assertEqual(rows[0]['status'], 'proposed')
        self.catalog('--check')


if __name__ == '__main__':
    unittest.main()
