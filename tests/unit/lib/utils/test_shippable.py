#!/usr/bin/env python

import json
import unittest

from lib.utils.shippable_api import ShippableRuns


class TestShippableParsing(unittest.TestCase):

    def do_parsing(self, srcfile, expfile=None, filter_paths=[],
                   filter_classes=[]):

        with open(srcfile, 'rb') as f:
            content = json.load(f)

        SR = ShippableRuns()
        res = SR.parse_tests_json(
            content,
            filter_paths=filter_paths,
        )

        if filter_classes:
            res = SR._filter_failures_by_classes(res, filter_classes)

        if expfile:
            with open(expfile, 'rb') as f:
                expected = json.load(f)
            assert res == expected

        return res

    def test_complex_parsing(self):
        src_fn = 'tests/fixtures/shippable_complex_testresults.json'
        exp_fn = 'tests/fixtures/shippable_complex_testresults_expected.json'
        self.do_parsing(src_fn, expfile=exp_fn)

    def test_complex_parsing_with_filters(self):

        filter_paths=['/testresults.json'],
        filter_classes=['sanity']

        src_fn = 'tests/fixtures/shippable_complex_testresults.json'
        res = self.do_parsing(
            src_fn,
            filter_paths=filter_paths,
            filter_classes=filter_classes
        )
        assert res == []


