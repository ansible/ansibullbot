#!/usr/bin/env python

import json
import unittest

from ansibullbot._text_compat import to_text
from ansibullbot.triagers.ansible import AnsibleTriage
from ansibullbot.utils.extractors import extract_template_data

class TestModuleMatching(unittest.TestCase):


    def test_module_matching(self):

        print('')

        AT = AnsibleTriage(args={})

        jfile = 'tests/fixtures/issue_template_meta.json'
        with open(jfile, 'rb') as f:
            jdata = json.load(f)

        keys = sorted([int(x) for x in jdata.keys()])

        for key in keys:

            k = to_text(key)
            v = jdata[k]

            if '/pull/' in v['html_url']:
                continue

            print(v['html_url'])

            # extract fields from the body
            td = extract_template_data(
                v['body'],
                issue_class=None
            )

            # schema tests
            assert isinstance(td, dict)
            assert 'component_raw' in td
            assert 'component name' in td

            # confirm the raw converted to the component name
            assert td['component_raw'] == v['component_raw']
            assert td['component name'] == v['component_name']

            # confirm module matching works.
            mm = AT.find_module_match(v['title'], td)
            if v['module_match']:
                if mm is None:
                    import epdb; epdb.st()
                elif mm['filepath'] != v['module_match'] and \
                        mm['name'] != v['module_match']:
                    import epdb; epdb.st()
            elif mm is not None:
                import epdb; epdb.st()

            #assert mm == v['module_match']['filepath']
            #import epdb; epdb.st()

