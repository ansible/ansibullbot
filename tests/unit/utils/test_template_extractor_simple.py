#!/usr/bin/env python

import unittest
from ansibullbot.utils.extractors import extract_template_data


class TestTemplateExtractionSimple(unittest.TestCase):

    def test_generic_template_with_no_input_sections(self):

        # https://github.com/ansible/ansibullbot/issues/1163

        body = [
            u'<!--- Verify first that your feature was not already discussed on GitHub -->',
            u'<!--- Complete *all* sections as described, this form is processed automatically -->',
            u'',
            u'##### SUMMARY',
            u'<!--- Describe the new feature/improvement briefly below -->',
            u'I was using vcenter_license to apply a license to ESXi hosts. Since the last commit on Jan 10, 2019, that module only supports licensing a vCenter. Add support for ESXi licensing',
            u'##### ISSUE TYPE',
            u'- Feature Idea',
            u'',
            u'##### COMPONENT NAME',
            u'vcenter_license ',
            u'or ',
            u'vmware_host',
            u'',
            u'##### ADDITIONAL INFORMATION',
            u'<!--- Describe how the feature would be used, why it is needed and what it would solve -->',
            u'',
            u'<!--- Paste example playbooks or commands between quotes below -->',
            u'```yaml',
            u'',
            u'```',
            u'',
            u'<!--- HINT: You can also paste gist.github.com links for larger files -->',
            u''
        ]
        body = u'\r\n'.join(body)
        tdata = extract_template_data(body)

        assert u'component name' in tdata
        assert tdata[u'component name'] == 'vcenter_license'
        assert u'component_raw' in tdata
        assert tdata[u'component_raw'] == 'vcenter_license\nor\nvmware_host'
        assert u'issue type' in tdata
        assert tdata[u'issue type'] == u'feature idea'
        assert u'summary' in tdata
        assert u'additional information' in tdata
