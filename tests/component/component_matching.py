#!/usr/bin/env python

import json
import unittest

from ansibullbot.triagers.ansible import AnsibleTriage
from ansibullbot.utils.extractors import extract_template_data


class TestComponentMatching(unittest.TestCase):

    def test_component_matching(self):

        print('')

        AT = AnsibleTriage(args={})
        AT.file_indexer.get_files()

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

            components = AT.file_indexer.find_component_match(
                v['title'],
                v['body'],
                td
            )
            if components and clabels:
                comp_labels = AT.file_indexer.get_component_labels(
                    AT.valid_labels,
                    components
                )
                print('\t' + str(comp_labels))
                #import epdb; epdb.st()
