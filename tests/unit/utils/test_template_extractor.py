#!/usr/bin/env python

import unittest
from ansibullbot.utils.extractors import extract_template_data


class TestTemplateExtraction(unittest.TestCase):
    def test_0(self):
        body = [
            u'#### ONE',
            u'section one',
            u'#### TWO',
            u'section two',
            u'#### THREE',
            u'section three'
        ]
        body = u'\r\n'.join(body)
        issue_number = 0
        issue_class = u'issue'
        sections = [u'ONE', u'TWO', u'THREE']
        tdata = extract_template_data(
            body, issue_number=issue_number,
            issue_class=issue_class, sections=sections
        )
        assert tdata.get(u'one') == u'section one'
        assert tdata.get(u'two') == u'section two'
        assert tdata.get(u'three') == u'section three'

    def test_1(self):
        body = [
            u'#### ISSUE TYPE',
            u'- Bug Report',
            u'#### COMPONENT NAME',
            u'widget module',
            u'#### ANSIBLE VERSION',
            u'1.9.x'
            u'#### SUMMARY',
            u'the widget module does not work for me!!!'
        ]
        body = u'\r\n'.join(body)
        issue_number = 0
        issue_class = u'issue'
        sections = [u'ISSUE TYPE', u'COMPONENT NAME', u'ANSIBLE VERSION', u'SUMMARY']
        tdata = extract_template_data(
            body, issue_number=issue_number,
            issue_class=issue_class, sections=sections
        )
        assert tdata.get(u'ansible version') == u'1.9.x'
        assert tdata.get(u'issue type') == u'bug report'
        assert tdata.get(u'component name') == u'widget'
        assert tdata.get(u'component_raw') == u'widget module'
        assert tdata.get(u'summary') == u'the widget module does not work for me!!!'

    def test_2(self):
        body = [
            u'*** issue type ***:',
            u'- Bug Report',
            u'*** component name ***:',
            u'widget module',
            u'*** ansible version ***:',
            u'1.9.x'
            u'*** summary ***:',
            u'the widget module does not work for me!!!'
        ]
        body = u'\r\n'.join(body)
        issue_number = 0
        issue_class = u'issue'
        sections = [u'ISSUE TYPE', u'COMPONENT NAME', u'ANSIBLE VERSION', u'SUMMARY']
        tdata = extract_template_data(
            body, issue_number=issue_number,
            issue_class=issue_class, sections=sections
        )
        assert tdata.get(u'ansible version') == u'1.9.x'
        assert tdata.get(u'issue type') == u'bug report'
        assert tdata.get(u'component name') == u'widget'
        assert tdata.get(u'component_raw') == u'widget module'
        assert tdata.get(u'summary') == u'the widget module does not work for me!!!'

    # https://github.com/ansible/ansibullbot/issues/359
    def test_3(self):
        body = [
            u'#### ISSUE TYPE',
            u'- Bug Report',
            u'#### COMPONENT NAME',
            u'widget, thingamajig',
            u'#### ANSIBLE VERSION',
            u'1.9.x'
            u'#### SUMMARY',
            u'the widget AND thingamig modules are broken!!!'
        ]
        body = u'\r\n'.join(body)
        issue_number = 0
        issue_class = u'issue'
        sections = [u'ISSUE TYPE', u'COMPONENT NAME', u'ANSIBLE VERSION', u'SUMMARY']
        tdata = extract_template_data(
            body, issue_number=issue_number,
            issue_class=issue_class, sections=sections
        )
        assert tdata.get(u'ansible version') == u'1.9.x'
        assert tdata.get(u'issue type') == u'bug report'
        assert tdata.get(u'component name') == u'widget'
        assert tdata.get(u'component_raw') == u'widget, thingamajig'
        assert tdata.get(u'summary') == u'the widget AND thingamig modules are broken!!!'

    # https://github.com/ansible/ansibullbot/issues/385
    def test_4(self):
        body = [
            u'#### ISSUE TYPE',
            u'- Feature Idea',
            u'#### COMPONENT NAME',
            u'Modules openssl_privatekey and openssl_publickey',
            u'#### ANSIBLE VERSION',
            u'```',
            u'ansible 2.2.1.0',
            u'  config file = /home/kellerfuchs/hashbang/admin-tools/ansible.cfg',
            u'  configured module search path = Default w/o overrides',
            u'```',
            u'#### SUMMARY',
            u'the widget AND thingamig modules are broken!!!'
        ]
        body = u'\r\n'.join(body)
        issue_number = 0
        issue_class = u'issue'
        sections = [u'ISSUE TYPE', u'COMPONENT NAME', u'ANSIBLE VERSION', u'SUMMARY']
        tdata = extract_template_data(
            body, issue_number=issue_number,
            issue_class=issue_class, sections=sections
        )

        #import epdb; epdb.st()
        assert tdata.get(u'ansible version').split(u'\n')[0] == u'ansible 2.2.1.0'
        assert tdata.get(u'issue type') == u'feature idea'
        assert tdata.get(u'component name') == u'openssl_privatekey'
        assert tdata.get(u'component_raw') == u'Modules openssl_privatekey and openssl_publickey'
        assert tdata.get(u'summary') == u'the widget AND thingamig modules are broken!!!'


    # Test optional Markdown header syntax
    def test_5(self):
        body = [
            u'#### ISSUE TYPE ####',
            u'- Bug Report',
            u'#### COMPONENT NAME ####',
            u'widget, thingamajig',
            u'#### ANSIBLE VERSION ####',
            u'1.9.x'
            u'#### SUMMARY ####',
            u'the widget AND thingamig modules are broken!!!'
        ]
        body = u'\r\n'.join(body)
        issue_number = 0
        issue_class = u'issue'
        sections = [u'ISSUE TYPE', u'COMPONENT NAME', u'ANSIBLE VERSION', u'SUMMARY']
        tdata = extract_template_data(
            body, issue_number=issue_number,
            issue_class=issue_class, sections=sections
        )
        assert tdata.get(u'ansible version') == u'1.9.x'
        assert tdata.get(u'issue type') == u'bug report'
        assert tdata.get(u'component name') == u'widget'
        assert tdata.get(u'component_raw') == u'widget, thingamajig'
        assert tdata.get(u'summary') == u'the widget AND thingamig modules are broken!!!'
