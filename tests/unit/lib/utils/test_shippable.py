#!/usr/bin/env python

import json
import unittest

from lib.utils.shippable_api import ShippableRuns


class TestShippableParsing(unittest.TestCase):

    def test_complex_parsing(self):
        src_fn = 'tests/fixtures/shippable_complex_testresults.json'
        with open(src_fn, 'rb') as f:
            tdata = json.load(f)

        exp_fn = 'tests/fixtures/shippable_complex_testresults_expected.json'
        with open(exp_fn, 'rb') as f:
            expected = json.load(f)

        SR = ShippableRuns()
        res = SR.parse_tests_json(tdata)

        assert res == expected
