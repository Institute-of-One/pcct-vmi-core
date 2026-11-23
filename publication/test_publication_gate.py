import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from publication_gate import CANONICAL_POLICY, CHECKS, ROLES, check, conclusion, sha, snapshot, warnings
import check_registered

class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write('paper.md', '# Discussion\nLimits.\n\n# Conclusion\nContribution supports evaluating verification strategies.\n')
        (self.root / 'policy.md').write_bytes(CANONICAL_POLICY.read_bytes())
        self.write('final.pdf', 'Synthetic artifact, not a clinical validation')
        self.config = dict(project_root='.', manuscript='paper.md', policy='policy.md',
                           artifacts=['final.pdf'], reviews={r: r + '.json' for r in ROLES},
                           human='human.json')
        self.approve()

    def write(self, name, value):
        (self.root / name).write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf-8')

    def approve(self, rationale='Contribution is supported; scope is limited to the tested mechanism.'):
        digest, _ = snapshot(self.config, self.root)
        ending = conclusion((self.root / 'paper.md').read_text())
        for role in ROLES:
            self.write(role + '.json', dict(role=role, snapshot=digest, policy_sha256=sha(self.root / 'policy.md'),
                reviewed_at='2026-01-01T00:00:00Z', decision='pass', independent=True,
                unresolved=[], session='synthetic-session-' + role, ending_quote=ending,
                ending_rationale=rationale, checks={k: {'pass': True, 'evidence': 'Synthetic fixture section 1'} for k in CHECKS}))
        self.write('human.json', dict(approved=True, snapshot=digest, name='Synthetic test author',
            approved_at='2026-01-02T00:00:00Z', approval_evidence='Synthetic fixture only',
            ending_rationale=rationale, review_sha256={r: sha(self.root / (r + '.json')) for r in ROLES}))

    def test_complete_fixture(self):
        self.assertEqual(check(self.config, self.root)['status'], 'PASS')

    def test_changed_inputs_revoke(self):
        for file in ('paper.md', 'policy.md', 'final.pdf'):
            with self.subTest(file=file):
                original = (self.root / file).read_bytes()
                (self.root / file).write_bytes(original + b'\nChanged')
                if file == 'policy.md':
                    with self.assertRaises(ValueError):
                        check(self.config, self.root)
                else:
                    self.assertEqual(check(self.config, self.root)['status'], 'BLOCKED')
                (self.root / file).write_bytes(original)

    def test_missing_review(self):
        (self.root / 'ChatGPT.json').unlink()
        with self.assertRaises(ValueError):
            check(self.config, self.root)

    def test_negative_ending_requires_all_dispositions(self):
        self.write('paper.md', '# Conclusion\nClinical safety has not been evaluated.\n')
        self.approve('')
        self.assertEqual(check(self.config, self.root)['status'], 'BLOCKED')
        self.approve('Necessary scientific qualification; scope explained in Discussion.')
        result = check(self.config, self.root)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['warnings'], ['ENDING_REQUIRES_REVIEW'])

    def test_false_or_unresolved_review(self):
        for change in ({'decision': 'fail'}, {'independent': False}, {'unresolved': ['overclaim']},
                       {'checks': {}}, {'policy_sha256': 'wrong'}, {'ending_quote': 'wrong'},
                       {'role': 'ChatGPT'}, {'session': ''}):
            self.approve()
            r = json.loads((self.root / 'Codex.json').read_text())
            r.update(change)
            self.write('Codex.json', r)
            h = json.loads((self.root / 'human.json').read_text())
            h['review_sha256']['Codex'] = sha(self.root / 'Codex.json')
            self.write('human.json', h)
            result = check(self.config, self.root)
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertTrue(any(e.startswith('Codex:') for e in result['errors']))
            self.assertFalse(any(e.startswith('Human') for e in result['errors']))

    def test_human_required_and_after_review(self):
        for change in ({'approved': False}, {'approved_at': '2025-01-01T00:00:00Z'},
                       {'approval_evidence': 'TODO'}, {'review_sha256': {}},
                       {'snapshot': 'wrong'}, {'name': 'TODO'}):
            self.approve()
            h = json.loads((self.root / 'human.json').read_text())
            h.update(change)
            self.write('human.json', h)
            self.assertEqual(check(self.config, self.root)['status'], 'BLOCKED')

    def test_config_change_revokes(self):
        c = copy.deepcopy(self.config)
        c['project_id'] = 'different'
        self.assertEqual(check(c, self.root)['status'], 'BLOCKED')

    def test_each_ending_disposition_required_independently(self):
        for role in ROLES:
            self.approve()
            r = json.loads((self.root / (role + '.json')).read_text())
            r['ending_rationale'] = ''
            self.write(role + '.json', r)
            h = json.loads((self.root / 'human.json').read_text())
            h['review_sha256'][role] = sha(self.root / (role + '.json'))
            self.write('human.json', h)
            self.assertEqual(check(self.config, self.root)['status'], 'BLOCKED')
        self.approve()
        h = json.loads((self.root / 'human.json').read_text())
        h['ending_rationale'] = ''
        self.write('human.json', h)
        self.assertEqual(check(self.config, self.root)['status'], 'BLOCKED')

    def test_ci_entrypoint_propagates_failure(self):
        self.assertEqual(check_registered.main(self.root), 0)
        (self.root / 'entries').mkdir()
        self.write('entries/paper.json', {})
        with patch('check_registered.subprocess.run') as run:
            run.return_value.returncode = 1
            self.assertEqual(check_registered.main(self.root), 1)
            run.assert_called_once()

    def test_malformed_dates_and_paths(self):
        self.config['artifacts'] = ['../secret']
        with self.assertRaises(ValueError):
            snapshot(self.config, self.root)
        self.config['artifacts'] = ['final.pdf']
        r = json.loads((self.root / 'Codex.json').read_text())
        r['reviewed_at'] = '2099-01-01T00:00:00Z'
        self.write('Codex.json', r)
        with self.assertRaises(ValueError):
            check(self.config, self.root)

    def test_heading_and_warning_variants(self):
        self.assertEqual(conclusion('# Conclusion\nContribution A.\n\n## Outlook\nClinical safety has not been evaluated.\n'),
                         'Clinical safety has not been evaluated.')
        self.assertEqual(conclusion('## 5. Conclusions\nFirst.\n\nLast.\n\n## References\nref'), 'Last.')
        for source in ('# Results\nno conclusion', '# Conclusion\n', '# Conclusion\na\n# Conclusion\nb'):
            with self.assertRaises(ValueError):
                conclusion(source)
        self.assertTrue(warnings('臨床的安全性は検証されていない。'))
        for sentence in ('Clinical safety has not yet been evaluated.',
                         'Prospective validation was never performed.', '臨床的有効性は評価されていない。'):
            self.assertTrue(warnings(sentence))
        self.assertFalse(warnings('These findings identify a measurable failure mechanism.'))

if __name__ == '__main__':
    unittest.main()
