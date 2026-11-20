"""Portable package checks; replace/add business tests in each owning module."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'agent'))
sys.path.insert(0, str(ROOT / 'agent/gates'))
import ask
import regression


class PackageTests(unittest.TestCase):
    def test_local_references(self):
        self.assertEqual(ask.check(ROOT)['status'], 'ok')

    def test_impact_required(self):
        with self.assertRaises(ValueError):
            regression.select(ask.load_package(ROOT), [])

    def test_unknown_impact_rejected(self):
        with self.assertRaises(ValueError):
            regression.select(ask.load_package(ROOT), ['T-DOES-NOT-EXIST'])
