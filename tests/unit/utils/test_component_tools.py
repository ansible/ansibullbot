#!/usr/bin/env python

import json
from unittest import TestCase

from ansibullbot.utils.component_tools import ComponentMatcher


class FakeIndexer(object):
    CMAP = {}
    botmeta = {'files': {}}
    modules = {}
    files = []


class TestComponentMatcher(TestCase):

    def test_reduce_filepaths(self):

        MI = FakeIndexer()
        FI = FakeIndexer()
        CM = ComponentMatcher(None, FI, MI)

        filepaths = ['commands/command.py', 'lib/ansible/modules/commands/command.py']
        reduced = CM.reduce_filepaths(filepaths)
        self.assertEqual(reduced, ['lib/ansible/modules/commands/command.py'])

    def test_search_by_filepath(self):

        COMPONENTS = {
            '/usr/lib/python2.7/site-packages/ansible/modules/core/packaging/os/rhn_register.py': [
                'lib/ansible/modules/packaging/os/rhn_register.py',
                'lib/ansible/modules/packaging/os/rhn_register.py'
            ],
            'module/network/ios/ios_facts': [
                'lib/ansible/modules/network/ios/ios_facts.py',
                'lib/ansible/modules/network/ios/ios_facts.py'
            ],
            'json_query': [
                'lib/ansible/plugins/filter/json_query.py',
                'lib/ansible/plugins/filter/json_query.py'
            ],
            'module_common.py': [
                'lib/ansible/executor/module_common.py',
                'lib/ansible/executor/module_common.py'
            ],
            '/network/dellos6/dellos6_config': [
                'lib/ansible/modules/network/dellos6/dellos6_config.py',
                'lib/ansible/modules/network/dellos6/dellos6_config.py'
            ],
            'module_utils/vmware': [
                'lib/ansible/module_utils/vmware.py',
                'lib/ansible/module_utils/vmware.py'
            ],
            '`azure_rm.py`': [
                'contrib/inventory/azure_rm.py',
                'contrib/inventory/azure_rm.py'
            ],
            'vmware_inventory': [
                'contrib/inventory/vmware_inventory.py',
                'contrib/inventory/vmware_inventory.py'
            ],
            'skippy': [
                'lib/ansible/plugins/callback/skippy.py',
                'lib/ansible/plugins/callback/skippy.py'
            ],
            'azure_rm_common': [
                'lib/ansible/module_utils/azure_rm_common.py',
                'lib/ansible/module_utils/azure_rm_common.py'
            ],
            'junit': [
                'lib/ansible/plugins/callback/junit.py',
                'lib/ansible/plugins/callback/junit.py'
            ],
            '`plugins/strategy/__init__.py`': [
                'lib/ansible/plugins/strategy/__init__.py',
                'lib/ansible/plugins/strategy/__init__.py'
            ],
            '- jabber.py': [
                'lib/ansible/plugins/callback/jabber.py',
                'lib/ansible/plugins/callback/jabber.py'
            ],
            '- ios_config.py': [
                'lib/ansible/plugins/action/ios_config.py',
                'lib/ansible/plugins/action/ios_config.py'
            ],
            'ansible-test': [
                'test/runner/ansible-test',
                'test/runner/ansible-test'
            ],
            'inventory manager': [
                None,
                'lib/ansible/inventory/manager.py'
            ],
            'ansible/hacking/test-module': [
                'hacking/test-module',
                'hacking/test-module'
            ],
            '- ansible-connection': [
                'bin/ansible-connection',
                'bin/ansible-connection'
            ],
            '`validate-modules`': [
                'test/sanity/validate-modules/validate-modules',
                'test/sanity/validate-modules/validate-modules'
            ],
            '`modules/cloud/docker/docker_container.py`': [
                'lib/ansible/modules/cloud/docker/docker_container.py',
                'lib/ansible/modules/cloud/docker/docker_container.py'
            ],
            'packaging/language/maven_artifact': [
                'lib/ansible/modules/packaging/language/maven_artifact.py',
                'lib/ansible/modules/packaging/language/maven_artifact.py'
            ],
            '`lib/ansible/executor/module_common.py`': [
                'lib/ansible/executor/module_common.py',
                'lib/ansible/executor/module_common.py'
            ],
        }

        #COMPONENTS = ['ansible/hacking/test-module']
        #COMPONENTS = ['packaging/language/maven_artifact']
        #COMPONENTS = ['module/network/ios/ios_facts']
        #COMPONENTS = ['/usr/lib/python2.7/site-packages/ansible/modules/core/packaging/os/rhn_register.py']

        MI = FakeIndexer()
        FI = FakeIndexer()
        CM = ComponentMatcher(None, FI, MI)

        with open('tests/fixtures/filenames/2017-10-24.json', 'rb') as f:
            FI.files = json.loads(f.read())

        for k,v in COMPONENTS.items():
            COMPONENT = k
            EXPECTED = v

            #print('---------------------------------------------------')
            #print('| {}'.format(COMPONENT))
            #print('---------------------------------------------------')

            res = CM.search_by_filepath(COMPONENT)
            #print('!partial: {}'.format(res))
            if EXPECTED[0] is None and not res:
                pass
            else:
                self.assertEqual(res, [EXPECTED[0]])

            res = CM.search_by_filepath(COMPONENT, partial=True)
            #print('partial: {}'.format(res))
            if EXPECTED[1] is None and not res:
                pass
            else:
                self.assertEqual(res, [EXPECTED[1]])
