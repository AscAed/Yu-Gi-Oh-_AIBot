import copy
import unittest
from fractions import Fraction
from unittest.mock import patch

from ygo_eval.information_math import (
    audit_ordering, audit_probability, fisher_yates_distribution,
    validate_distribution, validate_probability_report, validate_ordering_report,
)


class InformationMathTests(unittest.TestCase):
    def test_handwritten_two_and_three_label_distributions(self):
        self.assertEqual(fisher_yates_distribution(('A', 'B')),
                         {('A', 'B'): Fraction(1, 2), ('B', 'A'): Fraction(1, 2)})
        expected = {tuple(s): Fraction(1, 6)
                    for s in ('ABC', 'ACB', 'BAC', 'BCA', 'CAB', 'CBA')}
        self.assertEqual(fisher_yates_distribution(('A', 'B', 'C')), expected)

    def test_exact_labelled_and_code_marginals(self):
        report = audit_probability()
        self.assertEqual(report['labelled_count'], 120)
        self.assertEqual(report['card_order_count'], 20)
        self.assertEqual(report['labelled_mass'], {'numerator': 1, 'denominator': 1})
        self.assertEqual(report['card_order_mass'], {'numerator': 1, 'denominator': 1})
        self.assertTrue(all(e['probability'] == {'numerator': 1, 'denominator': 120}
                            for e in report['labelled_distribution']))
        self.assertTrue(all(e['probability'] == {'numerator': 1, 'denominator': 20}
                            for e in report['card_order_distribution']))
        self.assertFalse(report['native_probability_verified'])

    def test_distribution_rejects_corrupt_branches_and_mass(self):
        entries = [{'outcome': ['A'], 'probability': {'numerator': 1, 'denominator': 2}},
                   {'outcome': ['B'], 'probability': {'numerator': 1, 'denominator': 2}}]
        self.assertEqual(validate_distribution(entries), Fraction(1))
        for bad in (entries[:1], entries + entries[:1]):
            with self.assertRaises(ValueError):
                validate_distribution(bad)
        for numerator, denominator in ((-1, 2), (1, 0), (True, 2), (1, -2)):
            bad = copy.deepcopy(entries)
            bad[0]['probability'] = {'numerator': numerator, 'denominator': denominator}
            with self.assertRaises(ValueError):
                validate_distribution(bad)

    def test_ordering_matches_handwritten_choice_bytes_without_merging_cards(self):
        report = audit_ordering()
        cards = report['cards']
        self.assertEqual(cards[0]['choice'], {'kind': 'cards', 'indices': [0, 1]})
        self.assertEqual(cards[1]['choice'], {'kind': 'cards', 'indices': [1, 0]})
        self.assertEqual(cards[0]['bytes'], [0, 0, 0, 0, 2, 0, 0, 0,
                                            0, 0, 0, 0, 1, 0, 0, 0])
        self.assertEqual(cards[1]['bytes'], [0, 0, 0, 0, 2, 0, 0, 0,
                                            1, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(cards[0]['card_codes'], ['A', 'A'])
        self.assertEqual(report['places'][0]['bytes'], [0, 4, 0, 0, 4, 1])
        self.assertEqual(report['places'][1]['bytes'], [0, 4, 1, 0, 4, 0])
        self.assertFalse(report['order_equivalence_proven'])
        self.assertEqual(report['native_legality'], 'unverified')

    def test_corrupt_aggregation_rejected_even_with_probability_mass_one(self):
        report = audit_probability()
        self.assertTrue(validate_probability_report(report))
        bad = copy.deepcopy(report)
        bad['card_order_distribution'][0]['probability'] = {'numerator': 1, 'denominator': 10}
        bad['card_order_distribution'][1]['probability'] = {'numerator': 0, 'denominator': 1}
        with self.assertRaises(ValueError):
            validate_probability_report(bad)

    def test_pure_audits_do_not_start_processes_or_open_files(self):
        with patch('subprocess.Popen', side_effect=AssertionError('process forbidden')), \
                patch('builtins.open', side_effect=AssertionError('file forbidden')):
            self.assertTrue(audit_probability()['valid'])
            self.assertTrue(audit_ordering()['valid'])

    def test_ordering_validator_rejects_mismatch_and_instance_collapse(self):
        self.assertTrue(validate_ordering_report(audit_ordering()))
        mutations = (
            lambda r: r['cards'][0]['choice']['indices'].reverse(),
            lambda r: r['cards'][0]['bytes'].__setitem__(8, 1),
            lambda r: r['cards'][0]['card_codes'].pop(),
            lambda r: r['cards'][0]['positions'].pop(),
            lambda r: r['places'][0]['choice']['zones'].reverse(),
            lambda r: r.__setitem__('native_legality', 'illegal'),
            lambda r: r.__setitem__('order_equivalence_proven', True),
        )
        for mutate in mutations:
            report = audit_ordering()
            mutate(report)
            with self.assertRaises(ValueError):
                validate_ordering_report(report)

    def test_probability_validator_rejects_false_metadata(self):
        for key, value in (
                ('labelled_count', 119), ('card_order_count', 21),
                ('labelled_mass', {'numerator': 2, 'denominator': 1}),
                ('card_order_mass', {'numerator': 0, 'denominator': 1}),
                ('native_probability_verified', True), ('instance_merging_verified', True),
                ('shuffle_deletion_safe', True), ('origin', 'native'), ('valid', False)):
            report = audit_probability()
            report[key] = value
            with self.assertRaises(ValueError):
                validate_probability_report(report)


if __name__ == '__main__':
    unittest.main()
