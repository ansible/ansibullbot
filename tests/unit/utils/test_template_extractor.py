import unittest

import pytest

from ansibullbot.utils.extractors import _extract_template_data


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
        issue_class = 'issue'
        sections = ['ONE', 'TWO', 'THREE']
        tdata = _extract_template_data(
            body, issue_class=issue_class
        )
        assert tdata.get('one') == 'section one'
        assert tdata.get('two') == 'section two'
        assert tdata.get('three') == 'section three'

    def test_1(self):
        body = [
            '#### ISSUE TYPE',
            '- Bug Report',
            '#### COMPONENT NAME',
            'widget module',
            '#### ANSIBLE VERSION',
            '1.9.x'
            '#### SUMMARY',
            'the widget module does not work for me!!!'
        ]
        body = '\r\n'.join(body)
        issue_class = 'issue'
        sections = ['ISSUE TYPE', 'COMPONENT NAME', 'ANSIBLE VERSION', 'SUMMARY']
        tdata = _extract_template_data(
            body, issue_class=issue_class
        )
        assert tdata.get('ansible version') == '1.9.x'
        assert tdata.get('issue type') == 'bug report'
        assert tdata.get('component name') == 'widget'
        assert tdata.get('component_raw') == 'widget module'
        assert tdata.get('summary') == 'the widget module does not work for me!!!'

    @pytest.mark.skip(reason="with github yml templates we do not have to support fuzzy section finding in templates")
    def test_2(self):
        body = [
            '*** issue type ***:',
            '- Bug Report',
            '*** component name ***:',
            'widget module',
            '*** ansible version ***:',
            '1.9.x'
            '*** summary ***:',
            'the widget module does not work for me!!!'
        ]
        body = '\r\n'.join(body)
        issue_class = 'issue'
        sections = ['ISSUE TYPE', 'COMPONENT NAME', 'ANSIBLE VERSION', 'SUMMARY']
        tdata = _extract_template_data(
            body, issue_class=issue_class
        )
        assert tdata.get('ansible version') == '1.9.x'
        assert tdata.get('issue type') == 'bug report'
        assert tdata.get('component name') == 'widget'
        assert tdata.get('component_raw') == 'widget module'
        assert tdata.get('summary') == 'the widget module does not work for me!!!'

    # https://github.com/ansible/ansibullbot/issues/359
    def test_3(self):
        body = [
            '#### ISSUE TYPE',
            '- Bug Report',
            '#### COMPONENT NAME',
            'widget, thingamajig',
            '#### ANSIBLE VERSION',
            '1.9.x'
            '#### SUMMARY',
            'the widget AND thingamig modules are broken!!!'
        ]
        body = '\r\n'.join(body)
        issue_class = 'issue'
        sections = ['ISSUE TYPE', 'COMPONENT NAME', 'ANSIBLE VERSION', 'SUMMARY']
        tdata = _extract_template_data(
            body, issue_class=issue_class
        )
        assert tdata.get('ansible version') == '1.9.x'
        assert tdata.get('issue type') == 'bug report'
        assert tdata.get('component name') == 'widget'
        assert tdata.get('component_raw') == 'widget, thingamajig'
        assert tdata.get('summary') == 'the widget AND thingamig modules are broken!!!'

    # https://github.com/ansible/ansibullbot/issues/385
    def test_4(self):
        body = [
            '#### ISSUE TYPE',
            '- Feature Idea',
            '#### COMPONENT NAME',
            'Modules openssl_privatekey and openssl_publickey',
            '#### ANSIBLE VERSION',
            '```',
            'ansible 2.2.1.0',
            '  config file = /home/kellerfuchs/hashbang/admin-tools/ansible.cfg',
            '  configured module search path = Default w/o overrides',
            '```',
            '#### SUMMARY',
            'the widget AND thingamig modules are broken!!!'
        ]
        body = '\r\n'.join(body)
        issue_class = 'issue'
        sections = ['ISSUE TYPE', 'COMPONENT NAME', 'ANSIBLE VERSION', 'SUMMARY']
        tdata = _extract_template_data(
            body, issue_class=issue_class
        )

        #import epdb; epdb.st()
        assert tdata.get('ansible version').split('\n')[0] == 'ansible 2.2.1.0'
        assert tdata.get('issue type') == 'feature idea'
        assert tdata.get('component name') == 'openssl_privatekey'
        assert tdata.get('component_raw') == 'Modules openssl_privatekey and openssl_publickey'
        assert tdata.get('summary') == 'the widget AND thingamig modules are broken!!!'


    # Test optional Markdown header syntax
    def test_5(self):
        body = [
            '#### ISSUE TYPE ####',
            '- Bug Report',
            '#### COMPONENT NAME ####',
            'widget, thingamajig',
            '#### ANSIBLE VERSION ####',
            '1.9.x'
            '#### SUMMARY ####',
            'the widget AND thingamig modules are broken!!!'
        ]
        body = '\r\n'.join(body)
        issue_class = 'issue'
        sections = ['ISSUE TYPE', 'COMPONENT NAME', 'ANSIBLE VERSION', 'SUMMARY']
        tdata = _extract_template_data(
            body, issue_class=issue_class
        )
        assert tdata.get('ansible version') == '1.9.x'
        assert tdata.get('issue type') == 'bug report'
        assert tdata.get('component name') == 'widget'
        assert tdata.get('component_raw') == 'widget, thingamajig'
        assert tdata.get('summary') == 'the widget AND thingamig modules are broken!!!'
