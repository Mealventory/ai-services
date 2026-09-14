import unittest
from services.expiry_dates import extract_expiry_dates


class ExpiryDateTests(unittest.TestCase):
    def test_receipt_noise_and_purchase_dates(self):
        self.assertEqual(extract_expiry_dates('QUOY 1 234\n04/06/26\nPurchased September 14 2026'), [])

    def test_explicit_labels(self):
        for label in ['Best before', 'Use by', 'Expiry', 'Expiration date', 'Expires', 'EXP.', 'BB']:
            with self.subTest(label=label):
                self.assertEqual(extract_expiry_dates(label + ': September 30, 2026'), ['SEPTEMBER 30, 2026'])

    def test_calendar_validation(self):
        for value in ['QUOY 1 234', 'Feb 30 2026', 'Feb 29 2025', '2026-13-01', '31/04/26', 'Sep 0 26', 'Sept 30 234']:
            with self.subTest(value=value):
                self.assertEqual(extract_expiry_dates('Expiry: ' + value), [])
        self.assertEqual(extract_expiry_dates('Expiry: Feb 29 2028'), ['FEB 29 2028'])

    def test_missing_or_ambiguous_dates(self):
        for value in ['Sep 30', '04/06/26', '06-04-2026']:
            self.assertEqual(extract_expiry_dates('Best before ' + value), [])

    def test_unambiguous_formats(self):
        for value in ['2026-09-30', '30/09/26', '09/30/2026', '30 Sept 26', 'Sep. 30, 2026']:
            self.assertEqual(extract_expiry_dates('Use by ' + value), [value.upper()])

    def test_line_boundaries(self):
        self.assertEqual(extract_expiry_dates('Best before:\n2026-09-30'), ['2026-09-30'])
        self.assertEqual(extract_expiry_dates('Best before\n\n2026-09-30'), [])
        self.assertEqual(extract_expiry_dates('Best before: see lid\nPurchased 2026-09-30'), [])

    def test_duplicate_dates_and_label_boundaries(self):
        self.assertEqual(extract_expiry_dates('EXP Sep 30 2026\nBest before 2026-09-30'), ['SEP 30 2026'])
        self.assertEqual(extract_expiry_dates('Unexpected 2026-09-30\nBBQ 2026-09-30'), [])

    def test_no_partial_dates(self):
        for value in ['Sep 30 20266', '2026-09-300', '30/09/20266']:
            self.assertEqual(extract_expiry_dates('Expiry ' + value), [])

    def test_canadian_bilingual_sample(self):
        text = 'BEST BEFORE MEILLEUR AVANT 2027 JA 25 FF 11:57 NEC LES PROTEINE'
        self.assertEqual(extract_expiry_dates(text), ['2027 JA 25'])
        self.assertEqual(extract_expiry_dates('BEST BEFORE/MEILLEUR AVANT\n2027 JA 25'), ['2027 JA 25'])

    def test_canadian_month_symbols(self):
        for code in ['JA', 'FE', 'MR', 'AL', 'MA', 'JN', 'JL', 'AU', 'SE', 'OC', 'NO', 'DE']:
            with self.subTest(code=code):
                self.assertEqual(extract_expiry_dates(f'Best before 27 {code} 25'), [f'27 {code} 25'])

    def test_canadian_invalid_or_unlabelled_dates(self):
        for text in ['2027 JA 25', 'Purchased 2027 JA 25',
                     'MEILLEUR AVANT 2027 JA as', 'Best before 2027 FE 29',
                     'Best before 2027 AL 31', 'Best before 2027 XX 25',
                     'Best before 2027 JA 250', 'Best before JA 25']:
            with self.subTest(text=text):
                self.assertEqual(extract_expiry_dates(text), [])
        self.assertEqual(extract_expiry_dates('Best before 2028 FE 29'), ['2028 FE 29'])


if __name__ == '__main__':
    unittest.main()
