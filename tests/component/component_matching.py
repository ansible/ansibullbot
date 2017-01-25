#!/usr/bin/env python

import json
import unittest

from lib.triagers.ansible import AnsibleTriage
from lib.utils.extractors import extract_template_data


class TestComponentMatching(unittest.TestCase):

    def test_component_matching(self):

        print('')

        AT = AnsibleTriage(args={})

        jfile = 'tests/fixtures/issue_template_meta.json'
        with open(jfile, 'rb') as f:
            jdata = json.load(f)

        keys = sorted([int(x) for x in jdata.keys()])

        for key in keys:

            k = str(key)
            v = jdata[k]

            if '/pull/' in v['html_url']:
                continue

            if not v.get('labels'):
                continue

            if 'module' in v['labels']:
                continue

            clabels = [x for x in v['labels'] if x.startswith('c:')]
            #if not clabels:
            #    continue

            print(v['html_url'])

            # extract fields from the body
            td = extract_template_data(
                v['body'],
                issue_number=key,
                issue_class=None
            )

            components = AT.find_component_match(v['title'], v['body'], td)
            if components and clabels:
                import epdb; epdb.st()
