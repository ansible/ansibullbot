#!/usr/bin/env python

import unittest
from ansibullbot.utils.extractors import extract_template_data

# def extract_template_data(
#   body,
#   issue_number=None,
#   issue_class='issue',
#   SECTIONS=SECTIONS
# ):

class TestTemplateExtraction(unittest.TestCase):
    def test_0(self):
        body = [
            '#### ONE',
            'section one',
            '#### TWO',
            'section two',
            '#### THREE',
            'section three'
        ]
        body = '\r\n'.join(body)
        issue_number = 0
        issue_class = 'issue'
        sections = ['ONE', 'TWO', 'THREE']
        tdata = extract_template_data(
            body, issue_number=issue_number,
            issue_class=issue_class, SECTIONS=sections
        )
        assert tdata.get('one') == 'section one'
        assert tdata.get('two') == 'section two'
        assert tdata.get('three') == 'section three'
