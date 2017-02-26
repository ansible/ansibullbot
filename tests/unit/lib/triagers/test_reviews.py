#!/usr/bin/env python

import json
import glob
import unittest

from lib.triagers.plugins.needs_revision import get_review_state
from lib.triagers.plugins.needs_revision import changes_requested_by


class TestReviewsMunging(unittest.TestCase):

    def test_foo(self):

        filenames = sorted(set(glob.glob('/tmp/reviews/*.json')))
        for fn in filenames:
            print(fn)

            with open(fn, 'rb') as f:
                jdata = json.load(f)

            if 'submitter' not in jdata:
                continue

            ur = get_review_state(
                jdata['api_reviews'],
                jdata['submitter'],
                www_validate=jdata['www_reviews']
            )
            changes_requested_by(ur)
            #import epdb; epdb.st()

        assert True
