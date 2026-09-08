"""Local regression tests. All fixtures stay under internal/qa-artifacts/."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pymupdf as fitz
from prefill_agreement_from_inquiry import generate, load_map, read_fields, draft_values, apply_studio

HERE = Path(__file__).resolve().parent
CFG = load_map()
MASTER = (HERE / CFG['agreement_master']).resolve()
INQUIRY = (HERE / CFG['inquiry_master']).resolve()
SAMPLE = HERE / 'samples/Sample_Inquiry_With_Address.pdf'

class PrefillTests(unittest.TestCase):
    def setUp(self):
        (HERE / 'qa-artifacts').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=HERE / 'qa-artifacts')
        self.root = Path(self.temp.name)
        self.output = self.root / 'draft.pdf'
        self.hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [MASTER, INQUIRY, SAMPLE]}

    def tearDown(self):
        for p, digest in self.hashes.items():
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), digest)
        self.temp.cleanup()

    def values(self, path):
        with fitz.open(path) as d:
            return read_fields(d)[0]

    def test_sample_transfer_and_visual_preservation(self):
        output, report = generate(SAMPLE, self.output)
        src, got = self.values(SAMPLE), self.values(output)
        for key, targets in CFG['direct'].items():
            for target in targets:
                self.assertEqual(got[target], src[key])
        self.assertEqual(got['project_type'], 'Production-Ready Mobile MVP')
        self.assertEqual(got['platforms'], 'iPhone / iOS, Android')
        for key in ['project_objective', 'included_features', 'additional_terms']:
            self.assertTrue(got[key].startswith('REQUIRES STUDIO REVIEW'))
        for key in CFG['studio_controlled'] + CFG['always_blank'] + list(CFG['milestones']):
            self.assertEqual(got[key], '')
        self.assertIn('Client stated budget: US$4,800 total project fee', report.read_text())
        self.assertIn('Client preferred target date: November 27, 2026', report.read_text())
        with fitz.open(MASTER) as original, fitz.open(output) as result:
            self.assertEqual(len(original), len(result))
            for a, b in zip(original, result):
                self.assertEqual(a.get_pixmap(annots=False).samples, b.get_pixmap(annots=False).samples)
                self.assertEqual([(w.field_name, w.rect, w.field_type) for w in a.widgets() or []],
                                 [(w.field_name, w.rect, w.field_type) for w in b.widgets() or []])
            emails = [w.field_value for p in result for w in p.widgets() or [] if w.field_name == 'client_email']
            self.assertEqual(emails, ['alex@example.com', 'alex@example.com'])
            for p in result:
                for w in p.widgets() or []:
                    if w.field_name == 'project_name':
                        w.field_value = 'Editable after generation'; w.update()
            result.save(self.root / 'edited.pdf')
        self.assertEqual(self.values(self.root / 'edited.pdf')['project_name'], 'Editable after generation')

    def test_original_inquiry_and_missing_address(self):
        original = (HERE / CFG['original_inquiry_master']).resolve()
        _, report = generate(original, self.output)
        self.assertIn('client_address', report.read_text())
        self.assertIn('Client address unavailable', report.read_text())

    def test_company_fallback_all_mappings_and_ambiguity(self):
        v = self.values(SAMPLE)
        v['company_name'] = ''
        v.update({k: False for k in CFG['project_types']})
        for field, label in CFG['project_types'].items():
            v[field] = True
            result, _ = draft_values(v, CFG)
            self.assertEqual(result['project_type'], label)
            self.assertEqual(result['client_company'], v['client_name'])
            v[field] = False
        v.update({k: True for k in CFG['platforms']})
        v.update({k: True for k in CFG['features']})
        v['svc_mvp'] = v['svc_ai'] = True
        result, drafts = draft_values(v, CFG)
        self.assertEqual(result['project_type'], '')
        self.assertEqual(result['platforms'], ', '.join(CFG['platforms'].values()))
        for label in CFG['features'].values():
            self.assertIn(label, drafts['included_features'])
        for key in CFG['studio_controlled'] + CFG['always_blank']:
            self.assertNotIn(key, result)

    def test_payments_and_reviewed_scope(self):
        output, report = generate(SAMPLE, self.output, {'total_fee': '4800', 'payment_currency': 'USD',
            'included_features': 'User accounts; activity catalog; booking requests; booking confirmations.',
            'excluded_features': 'Payments; AI assistant; advanced analytics.'})
        got = self.values(output)
        for key, expected in zip(CFG['milestones'], ['USD 1,440.00', 'USD 1,440.00', 'USD 1,200.00', 'USD 720.00']):
            self.assertEqual(got[key], expected)
        self.assertEqual(got['total_fee'], 'USD 4,800.00')
        self.assertEqual(got['delivery_date'], '')
        self.assertTrue(got['excluded_features'].startswith('Payments;'))
        for fee in ['0.01', '0.02', '0.05', '1234.57']:
            r = {}; apply_studio(r, CFG, {'total_fee': fee, 'payment_currency': 'PHP'})
            from decimal import Decimal
            amounts = [Decimal(r[k].split()[1].replace(',', '')) for k in CFG['milestones']]
            self.assertEqual(sum(amounts), Decimal(fee))

    def test_invalid_fee_and_signature_config(self):
        for config in [{'total_fee': '4800'}, {'total_fee':'-10','payment_currency':'USD'},
                       {'total_fee':'1.001','payment_currency':'USD'}, {'total_fee':'NaN','payment_currency':'USD'},
                       {'client_signature':'Not allowed'}, {'client_date':'Not allowed'}, {'client_email':'override'}]:
            with self.assertRaises(ValueError):
                generate(SAMPLE, self.output, config)
            self.assertFalse(self.output.exists())

    def test_wrong_flattened_and_conflicting_inquiry(self):
        wrong = self.root / 'wrong.pdf'
        with fitz.open() as d:
            d.new_page().insert_text((40,40), 'Not an inquiry'); d.save(wrong)
        with self.assertRaises(ValueError): generate(wrong, self.output)
        bad = self.root / 'conflict.pdf'
        with fitz.open(SAMPLE) as d:
            page=d[0];w=fitz.Widget();w.field_name='client_email';w.field_type=fitz.PDF_WIDGET_TYPE_TEXT
            w.rect=fitz.Rect(10,780,150,798);w.field_value='conflict@example.com';page.add_widget(w);d.save(bad)
        with self.assertRaises(ValueError): generate(bad, self.output)

    def test_never_overwrites(self):
        generate(SAMPLE, self.output)
        before = self.output.read_bytes()
        with self.assertRaises(ValueError): generate(SAMPLE, self.output)
        self.assertEqual(self.output.read_bytes(), before)
        for dest in [MASTER, INQUIRY, SAMPLE]:
            with self.assertRaises(ValueError): generate(SAMPLE, dest)
        self.output.unlink()
        with self.assertRaises(ValueError): generate(SAMPLE, self.output)  # existing report

    def test_original_master_checksums_and_updated_inquiry(self):
        original = (HERE / CFG['original_inquiry_master']).resolve()
        for path, key in [(original,'inquiry'), (MASTER,'agreement')]:
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), CFG['original_master_sha256'][key])
        with fitz.open(original) as a, fitz.open(INQUIRY) as b:
            self.assertEqual(len(a),len(b))
            old = [(p.number,w.field_name,list(w.rect),w.field_type,w.field_value) for p in a for w in p.widgets() or []]
            new = [(p.number,w.field_name,list(w.rect),w.field_type,w.field_value) for p in b for w in p.widgets() or [] if w.field_name!='client_address']
            self.assertEqual(old,new)
            self.assertEqual(a[1].get_pixmap().samples,b[1].get_pixmap().samples)
            self.assertIn('client_address',self.values(INQUIRY))

if __name__ == '__main__':
    unittest.main(verbosity=2)
