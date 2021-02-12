import unittest
from ansibullbot.utils.extractors import extract_template_data


class TestTemplateExtractionSimple(unittest.TestCase):

    def test_generic_template_with_no_input_sections(self):

        # https://github.com/ansible/ansibullbot/issues/1163

        body = [
            '<!--- Verify first that your feature was not already discussed on GitHub -->',
            '<!--- Complete *all* sections as described, this form is processed automatically -->',
            '',
            '##### SUMMARY',
            '<!--- Describe the new feature/improvement briefly below -->',
            'I was using vcenter_license to apply a license to ESXi hosts. Since the last commit on Jan 10, 2019, that module only supports licensing a vCenter. Add support for ESXi licensing',
            '##### ISSUE TYPE',
            '- Feature Idea',
            '',
            '##### COMPONENT NAME',
            'vcenter_license ',
            'or ',
            'vmware_host',
            '',
            '##### ADDITIONAL INFORMATION',
            '<!--- Describe how the feature would be used, why it is needed and what it would solve -->',
            '',
            '<!--- Paste example playbooks or commands between quotes below -->',
            '```yaml',
            '',
            '```',
            '',
            '<!--- HINT: You can also paste gist.github.com links for larger files -->',
            ''
        ]
        body = '\r\n'.join(body)
        tdata = extract_template_data(body)

        assert 'component name' in tdata
        assert tdata['component name'] == 'vcenter_license'
        assert 'component_raw' in tdata
        assert tdata['component_raw'] == 'vcenter_license\nor\nvmware_host'
        assert 'issue type' in tdata
        assert tdata['issue type'] == 'feature idea'
        assert 'summary' in tdata
        assert 'additional information' in tdata
