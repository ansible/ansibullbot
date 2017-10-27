#!/usr/bin/env python

import json
import os
from unittest import TestCase

from ansibullbot.utils.component_tools import ComponentMatcher


class FakeIndexer(object):
    CMAP = {}
    botmeta = {'files': {}}
    modules = {}
    files = []

    def find_match(self, name, exact=True):
        '''Adapter for moduleindexer's function'''
        for k,v in self.modules.items():
            if v['name'] == name:
                return v
        return None


def get_component_matcher():

    # Make indexers
    MI = FakeIndexer()
    FI = FakeIndexer()

    # Load the files
    with open('tests/fixtures/filenames/2017-10-24.json', 'rb') as f:
        FI.files = json.loads(f.read())

    # Load the modules
    mfiles = [x for x in FI.files if 'lib/ansible/modules' in x]
    mfiles = [x for x in mfiles if x.endswith('.py') or x.endswith('.ps1')]
    mfiles = [x for x in mfiles if x != '__init__.py']
    mnames =[]
    for mfile in mfiles:
        mname = os.path.basename(mfile)
        mname = mname.replace('.py', '')
        mname = mname.replace('.ps1', '')
        mnames.append(mname)
        MI.modules[mfile] = {'name': mname, 'repo_filename': mfile}

    # Init the matcher
    CM = ComponentMatcher(None, FI, MI)

    return CM


class TestComponentMatcher(TestCase):

    def test_reduce_filepaths(self):

        #MI = FakeIndexer()
        #FI = FakeIndexer()
        #CM = ComponentMatcher(None, FI, MI)
        CM = get_component_matcher()

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
                #'lib/ansible/plugins/callback/jabber.py',
                #'lib/ansible/plugins/callback/jabber.py'
                'lib/ansible/modules/notification/jabber.py',
                'lib/ansible/modules/notification/jabber.py',
            ],
            '- ios_config.py': [
                #'lib/ansible/plugins/action/ios_config.py',
                #'lib/ansible/plugins/action/ios_config.py'
                'lib/ansible/modules/network/ios/ios_config.py',
                'lib/ansible/modules/network/ios/ios_config.py',
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
                #'test/sanity/validate-modules/validate-modules',
                #'test/sanity/validate-modules/validate-modules'
                'test/sanity/validate-modules',
                'test/sanity/validate-modules',
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

        CM = get_component_matcher()

        #COMPONENTS = {
        #    '`plugins/strategy/__init__.py`': [
        #        'lib/ansible/plugins/strategy/__init__.py',
        #        'lib/ansible/plugins/strategy/__init__.py'
        #    ],
        #}

        #import epdb; epdb.st()

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
                self.assertEqual([EXPECTED[0]], res)

            res = CM.search_by_filepath(COMPONENT, partial=True)
            #print('partial: {}'.format(res))
            if EXPECTED[1] is None and not res:
                pass
            else:
                self.assertEqual([EXPECTED[1]], res)

    def test_search_by_filepath_with_context(self):

        CM = get_component_matcher()

        COMPONENTS = {
            'ec2.py': [
                #{'context': None, 'expected': ['contrib/inventory/ec2.py']},
                {'context': 'contrib/inventory', 'expected': ['contrib/inventory/ec2.py']},
                {'context': 'lib/ansible/modules', 'expected': ['lib/ansible/modules/cloud/amazon/ec2.py']},
            ],
            'netapp_e_storagepool storage module': [
                {'context': 'lib/ansible/modules', 'expected': ['lib/ansible/modules/storage/netapp/netapp_e_storagepool.py']},
            ]

        }

        for k,v in COMPONENTS.items():
            COMPONENT = k
            for v2 in v:
                CONTEXT = v2.get('context')
                EXPECTED = v2.get('expected')
                #print('')
                #print(v2)
                res = CM.search_by_filepath(COMPONENT, context=CONTEXT)
                self.assertEqual(EXPECTED, res)


    def test_search_by_regex_module_globs(self):

        CM = get_component_matcher()

        COMPONENTS = {
            'All AWS modules': 'lib/ansible/modules/cloud/amazon',
            'ec2_* modules': 'lib/ansible/modules/cloud/amazon',
            'GCP ansible modules': 'lib/ansible/modules/cloud/amazon',
            'BigIP modules': 'lib/ansible/modules/network/f5',
            'NXOS modules': 'lib/ansible/modules/network/nxos',
            'azurerm modules': 'lib/ansible/modules/cloud/azure',
            'ansiballz/ziploader for modules': [],
            'elasticache modules': [
                'lib/ansible/modules/cloud/amazon/elasticache.py',
                'lib/ansible/modules/cloud/amazon/elasticache_parameter_group.py',
                'lib/ansible/modules/cloud/amazon/elasticache_snapshot.py',
                'lib/ansible/modules/cloud/amazon/elasticache_subnet_group.py',
            ],
            'All FreeIPA Modules': [],
            'All modules': [],
            'All Cisco IOS Modules': [],
            'All EC2 based modules, possibly more.': 'lib/ansible/modules/cloud/amazon',
        }

        for COMPONENT,EXPECTED in COMPONENTS.items():
            if not isinstance(EXPECTED, list):
                EXPECTED = [EXPECTED]
            res = CM.search_by_regex_module_globs(COMPONENT)
            #print('')
            #print(COMPONENT)
            #print(res)
            self.assertEqual(EXPECTED, res)

    def test_search_by_keywords(self):

        CM = get_component_matcher()

        COMPONENTS = {
            #'inventory script': ['lib/ansible/plugins/inventory/script.py'] #ix2390 https://github.com/ansible/ansible/issues/24545
            'inventory script': ['contrib/inventory'] #ix2390 https://github.com/ansible/ansible/issues/24545
        }

        for k,v in COMPONENTS.items():
            COMPONENT = k
            EXPECTED = v
            res = CM.search_by_keywords(COMPONENT)
            self.assertEqual(EXPECTED, res)

    def test_search_by_regex_modules(self):

        CM = get_component_matcher()

        COMPONENTS = {
            'Module: include_role': ['lib/ansible/modules/utilities/logic/include_role.py'],
            'module: include_role': ['lib/ansible/modules/utilities/logic/include_role.py'],
            'module include_role': ['lib/ansible/modules/utilities/logic/include_role.py'],
            #'ec2_asg (AWS EC2 auto scaling groups)': ['lib/ansible/modules/cloud/amazon/ec2_asg.py'],
            'junos_command (but not only !)': ['lib/ansible/modules/network/junos/junos_command.py'],
            'tower_job_list module but I believe that also the other tower_* module have the same error':
                ['lib/ansible/modules/web_infrastructure/ansible_tower/tower_job_list.py'],
            #'F5 bigip (bigip_selfip)': ['lib/ansible/modules/network/f5/bigip_selfip.py'],
            'ansible_modules_vsphere_guest': ['lib/ansible/modules/cloud/vmware/vsphere_guest.py'],
            'shell-module': ['lib/ansible/modules/commands/shell.py'],
            'the docker_volume command': ['lib/ansible/modules/cloud/docker/docker_volume.py'],
            'Azure Inventory Script - azure_rm.py': [],
            ':\n`at` module': ['lib/ansible/modules/system/at.py'],
            ':\n`rax` module': ['lib/ansible/modules/cloud/rackspace/rax.py'],
            '`apt_key` module': ['lib/ansible/modules/packaging/os/apt_key.py'],
            '`apt` module': ['lib/ansible/modules/packaging/os/apt.py'],
            '`ecs_service` module': ['lib/ansible/modules/cloud/amazon/ecs_service.py'],
            '`meta` module': ['lib/ansible/modules/utilities/helper/meta.py'],
            '`meta` module': ['lib/ansible/modules/utilities/helper/meta.py'],
            '`mysql_user` module': ['lib/ansible/modules/database/mysql/mysql_user.py'],
            '`s3` module': [],
            '`user` module': ['lib/ansible/modules/system/user.py'],
            'the "user" module': ['lib/ansible/modules/system/user.py'],
            '`ansible_module_ec2_ami_copy.py`': ['lib/ansible/modules/cloud/amazon/ec2_ami_copy.py'],
            'module: `include_vars `': ['lib/ansible/modules/utilities/logic/include_vars.py'],
            'rabbitmq_plugin  module': ['lib/ansible/modules/messaging/rabbitmq_plugin.py'],
            'F5 bigip (bigip_selfip)': [''],
            'module: `vsphere_guest`': [''],
            'nxos_template': [''],
        }

        for COMPONENT,EXPECTED in COMPONENTS.items():
            res = CM.search_by_regex_modules(COMPONENT)
            self.assertEqual(EXPECTED, res)

    # FIXME
    # [2873] ec2_asg (AWS EC2 auto scaling groups)
    # [2998] junos_command (but not only !)
    # [3531] lib/ansible/modules/storage/netapp/sf_volume-manager.py
    # [3739] tower_job_list module but I believe that also the other tower_* module have the same error
    # [4039] netapp_e_storagepool storage module
    # [4774] azure_rm_deployment (although azure_rm_common seems to be at work here)
