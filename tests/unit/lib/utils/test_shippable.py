#!/usr/bin/env python

import json
import glob
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
            #with open('/tmp/result.json', 'wb') as f:
            #    f.write(json.dumps(res))
            #import epdb; epdb.st()
            assert res == expected

        return res

    '''
    def do_testcase_parsing(self, srcfile, expfile=None, filter_paths=[],
                   filter_classes=[]):

        with open(srcfile, 'rb') as f:
            content = json.load(f)

        content = [x for x in content if x['path'] in filter_paths]
        results = []
        for x in content:
            SR = ShippableRuns()
            res = SR.parse_testcase(
                content,
            )
            results.append(res)

        import epdb; epdb.st()

        if filter_classes:
            res = SR._filter_failures_by_classes(res, filter_classes)

        if expfile:
            with open(expfile, 'rb') as f:
                expected = json.load(f)
            assert res == expected

        return res
    '''

    def test_complex_parsing(self):
        src_fn = 'tests/fixtures/shippable/complex_testresults.json'
        exp_fn = 'tests/fixtures/shippable/complex_testresults_expected.json'
        self.do_parsing(src_fn, expfile=exp_fn)

    '''
    def test_complex_parsing_with_filters(self):

        filter_paths = ['/testresults.json'],
        filter_classes = ['sanity']

        src_fn = 'tests/fixtures/shippable/complex_testresults.json'
        res = self.do_parsing(
            src_fn,
            filter_paths=filter_paths,
            filter_classes=filter_classes
        )
        assert res == []
    '''

    '''
    def test_example1_with_filters(self):


        filter_paths = ['/testresults.json'],
        filter_classes = ['sanity']

        fns = glob.glob('tests/fixtures/shippable/*_jobTestReports.json')
        for fn in fns:
            #res = self.do_parsing(
            res = self.do_testcase_parsing(
                fn,
                filter_classes=filter_classes
            )
            #import epdb; epdb.st()
            assert res != []
    '''
