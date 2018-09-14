#!/usr/bin/env python

import shutil
import tempfile
from unittest import TestCase

import six
six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from ansibullbot.utils.component_tools import AnsibleComponentMatcher as ComponentMatcher
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.file_tools import FileIndexer
from ansibullbot.utils.systemtools import run_command


class GitShallowRepo(GitRepoWrapper):
    """Perform a shallow copy"""

    def create_checkout(self):
        """checkout ansible"""
        cmd = "git clone --depth=1 --single-branch %s %s" % (self.repo, self.checkoutdir)
        (rc, so, se) = run_command(cmd)
        if rc:
            raise Exception("Fail to execute '{}: {} ({}, {})'".format(cmd, rc, so, se))

    def update_checkout(self):
        return False


class TestComponentMatcher(TestCase):

    @classmethod
    def setUpClass(cls):
        """Init the matcher"""
        cachedir = tempfile.mkdtemp()
        gitrepo = GitShallowRepo(cachedir=cachedir, repo=ComponentMatcher.REPO)
        gitrepo.update()

        @mock.patch.object(FileIndexer, 'manage_checkout')
        @mock.patch.object(FileIndexer, 'checkoutdir', create=True, side_effect=gitrepo.checkoutdir)
        def get_file_indexer(m_manage_checkout, m_checkoutdir):
            indexer = FileIndexer()
            indexer.get_files()
            indexer.parse_metadata()
            return indexer

        cls.component_matcher = ComponentMatcher(email_cache={}, gitrepo=gitrepo, file_indexer=get_file_indexer())

    @classmethod
    def tearDownClass(cls):
        """suppress temp dir"""
        shutil.rmtree(cls.component_matcher.gitrepo.checkoutdir)

    def test_get_meta_for_file_wildcard(self):
        self.component_matcher.file_indexer.botmeta = self.component_matcher.BOTMETA = {
            'files': {
                'lib/ansible/plugins/action/junos': {
                    'maintainers': ['gundalow'],
                    'labels': ['networking'],
                }
            }
        }
        result = self.component_matcher.get_meta_for_file('lib/ansible/plugins/action/junos_config.py')
        self.assertEqual(result['labels'], ['networking'])
        self.assertEqual(result['maintainers'], ['gundalow'])

    def test_get_meta_for_file_wildcard_multiple(self):
        self.component_matcher.file_indexer.botmeta = self.component_matcher.BOTMETA = {
            'files': {
                'lib/ansible/plugins/action/junos_config.py': {
                    'maintainers': ['privateip'],
                    'labels': ['config'],
                    'notified': ['jctanner'],
                },
                'lib/ansible/plugins/action/junos': {
                    'maintainers': ['gundalow'],
                    'labels': ['networking'],
                    'notified': ['mkrizek'],
                }
            }
        }
        result = self.component_matcher.get_meta_for_file('lib/ansible/plugins/action/junos_config.py')

        self.assertItemsEqual(result['notify'], ['gundalow', 'mkrizek', 'jctanner', 'privateip'])
        self.assertItemsEqual(result['labels'], ['networking', 'config'])
        self.assertItemsEqual(result['maintainers'], ['gundalow', 'privateip'])

    def test_get_meta_for_file_pyfile(self):
        self.component_matcher.file_indexer.botmeta = self.component_matcher.BOTMETA = {
            'files': {
                'lib/ansible/modules/packaging/os/yum.py': {
                    'maintainers': ['maxamillion'],
                }
            }
        }
        result = self.component_matcher.get_meta_for_file('lib/ansible/modules/packaging/os/yum.py')
        self.assertEqual(result['maintainers'], ['maxamillion'])

    def test_get_meta_for_file_powershell(self):
        self.component_matcher.file_indexer.botmeta = self.component_matcher.BOTMETA = {
            'files': {
                'lib/ansible/modules/windows/win_ping.py': {
                    'maintainers': ['jborean93'],
                    'labels': ['windoez'],
                }
            }
        }
        result = self.component_matcher.get_meta_for_file('lib/ansible/modules/windows/win_ping.ps1')
        self.assertEqual(result['labels'], ['windoez'])
        self.assertEqual(result['maintainers'], ['jborean93'])

    def test_reduce_filepaths(self):

        filepaths = ['commands/command.py', 'lib/ansible/modules/commands/command.py']
        reduced = self.component_matcher.reduce_filepaths(filepaths)
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
            # Doesn't work, lib/ansible/modules/network/nso/nso_query.py is
            # found
            #'json_query': [
            #    'lib/ansible/plugins/filter/json_query.py',
            #    'lib/ansible/plugins/filter/json_query.py'
            #],
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
            # Unable to follow symlink ? Besides a new file exists: test/sanity/pylint/config/ansible-test
            #'ansible-test': [
            #    'test/runner/ansible-test',
            #    'test/runner/ansible-test'
            #],
            'inventory manager': [
                None,
                'lib/ansible/inventory/manager.py'
            ],
            # Doesn't work
            #'ansible/hacking/test-module': [
            #    'hacking/test-module',
            #    'hacking/test-module'
            #],
            '- ansible-connection': [
                'bin/ansible-connection',
                'bin/ansible-connection'
            ],
            # Doesn't work
            #'`validate-modules`': [
            #    'test/sanity/validate-modules/validate-modules',
            #    'test/sanity/validate-modules/validate-modules'
            #],
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

        for k,v in COMPONENTS.items():
            COMPONENT = k
            EXPECTED = v

            res = self.component_matcher.search_by_filepath(COMPONENT)
            if EXPECTED[0] is None and not res:
                pass
            else:
                self.assertEqual([EXPECTED[0]], res)

            res = self.component_matcher.search_by_filepath(COMPONENT, partial=True)
            if EXPECTED[1] is None and not res:
                pass
            else:
                self.assertEqual([EXPECTED[1]], res)

    def test_search_by_filepath_with_context(self):

        COMPONENTS = {
            'ec2.py': [
                #{'context': None, 'expected': ['contrib/inventory/ec2.py']},
                {'context': 'contrib/inventory', 'expected': ['contrib/inventory/ec2.py']},
                {'context': 'lib/ansible/modules', 'expected': ['lib/ansible/modules/cloud/amazon/ec2.py']},
            ],
            'netapp_e_storagepool storage module': [
                {'context': 'lib/ansible/modules', 'partial': False, 'expected': []},
                {'context': 'lib/ansible/modules', 'partial': True, 'expected': ['lib/ansible/modules/storage/netapp/netapp_e_storagepool.py']},
            ],
            'ansible/files/modules/archive.py': [
                {'context': None, 'partial': True, 'expected': ['lib/ansible/modules/files/archive.py']}
            ],
            # Doesn't work
            #'lib/ansible/modules/cloud/amazon': [
            #    {'context': None, 'partial': False, 'expected': ['lib/ansible/modules/cloud/amazon']},
            #    {'context': None, 'partial': True, 'expected': ['lib/ansible/modules/cloud/amazon']}
            #],
            #'modules/network/f5': [
            #    {'context': None, 'partial': False, 'expected': ['lib/ansible/modules/network/f5']},
            #    {'context': None, 'partial': True, 'expected': ['lib/ansible/modules/network/f5']}
            #],
            #'modules/network/iosxr': [
            #    {'context': None, 'partial': False, 'expected': ['lib/ansible/modules/network/iosxr']},
            #    {'context': None, 'partial': True, 'expected': ['lib/ansible/modules/network/iosxr']}
            #]
        }

        '''
        COMPONENTS = {
            'netapp_e_storagepool storage module': [
                {'context': 'lib/ansible/modules', 'partial': False, 'expected': ['lib/ansible/modules/storage/netapp/netapp_e_storagepool.py']},
                {'context': 'lib/ansible/modules', 'partial': True, 'expected': ['lib/ansible/modules/storage/netapp/netapp_e_storagepool.py']},
            ],
        }
        '''

        for k,v in COMPONENTS.items():
            COMPONENT = k
            for v2 in v:
                CONTEXT = v2.get('context')
                PARTIAL = v2.get('partial')
                EXPECTED = v2.get('expected')
                res = self.component_matcher.search_by_filepath(COMPONENT, context=CONTEXT, partial=PARTIAL)
                self.assertEqual(EXPECTED, res)

    def test_search_by_regex_module_globs(self):

        COMPONENTS = {
            'All AWS modules': 'lib/ansible/modules/cloud/amazon',
            'ec2_* modules': 'lib/ansible/modules/cloud/amazon',
            'GCP ansible modules': 'lib/ansible/modules/cloud/google',
            'BigIP modules': 'lib/ansible/modules/network/f5',
            'NXOS modules': 'lib/ansible/modules/network/nxos',
            'azurerm modules': 'lib/ansible/modules/cloud/azure',
            'ansiballz/ziploader for modules': [],
            'dellos*_* network modules': [],
            'elasticache modules': [
                'lib/ansible/modules/cloud/amazon/elasticache.py',
                'lib/ansible/modules/cloud/amazon/elasticache_facts.py',
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
            res = self.component_matcher.search_by_regex_module_globs(COMPONENT)

            self.assertEqual(EXPECTED, res)

    def test_search_by_keywords(self):

        COMPONENTS = {
            #'inventory script': ['lib/ansible/plugins/inventory/script.py'] #ix2390 https://github.com/ansible/ansible/issues/24545
            'inventory script': ['contrib/inventory']  # ix2390 https://github.com/ansible/ansible/issues/24545
        }

        for k,v in COMPONENTS.items():
            COMPONENT = k
            EXPECTED = v
            res = self.component_matcher.search_by_keywords(COMPONENT)
            self.assertEqual(EXPECTED, res)

    def test_search_by_regex_modules(self):

        COMPONENTS = {
            'Module: include_role': ['lib/ansible/modules/utilities/logic/include_role.py'],
            'module: include_role': ['lib/ansible/modules/utilities/logic/include_role.py'],
            'module include_role': ['lib/ansible/modules/utilities/logic/include_role.py'],
            #'ec2_asg (AWS EC2 auto scaling groups)': ['lib/ansible/modules/cloud/amazon/ec2_asg.py'],
            'junos_command (but not only !)': ['lib/ansible/modules/network/junos/junos_command.py'],
            'tower_job_list module but I believe that also the other tower_* module have the same error':
                ['lib/ansible/modules/web_infrastructure/ansible_tower/tower_job_list.py'],
            #'F5 bigip (bigip_selfip)': ['lib/ansible/modules/network/f5/bigip_selfip.py'],
            'ansible_modules_vsphere_guest': ['lib/ansible/modules/cloud/vmware/_vsphere_guest.py'],
            'shell-module': ['lib/ansible/modules/commands/shell.py'],
            'the docker_volume command': ['lib/ansible/modules/cloud/docker/docker_volume.py'],
            'Azure Inventory Script - azure_rm.py': [],
            ':\n`at` module': ['lib/ansible/modules/system/at.py'],
            ':\n`rax` module': ['lib/ansible/modules/cloud/rackspace/rax.py'],
            '`apt_key` module': ['lib/ansible/modules/packaging/os/apt_key.py'],
            '`apt` module': ['lib/ansible/modules/packaging/os/apt.py'],
            '`ecs_service` module': ['lib/ansible/modules/cloud/amazon/ecs_service.py'],
            '`meta` module': ['lib/ansible/modules/utilities/helper/meta.py'],
            #'`meta` module': ['lib/ansible/modules/utilities/helper/meta.py'],
            '`mysql_user` module': ['lib/ansible/modules/database/mysql/mysql_user.py'],
            '`s3` module': ['lib/ansible/modules/cloud/amazon/_s3.py'],
            '`user` module': ['lib/ansible/modules/system/user.py'],
            'the "user" module': ['lib/ansible/modules/system/user.py'],
            '`ansible_module_ec2_ami_copy.py`': ['lib/ansible/modules/cloud/amazon/ec2_ami_copy.py'],
            'module: `include_vars `': ['lib/ansible/modules/utilities/logic/include_vars.py'],
            'rabbitmq_plugin  module': ['lib/ansible/modules/messaging/rabbitmq_plugin.py'],
            #'F5 bigip (bigip_selfip)': ['lib/ansible/modules/network/f5/bigip_selfip.py'],
            'module: `vsphere_guest`': ['lib/ansible/modules/cloud/vmware/_vsphere_guest.py'],
            'Add to vmware_guest module, Clone to Virtual Machine task': [
                'lib/ansible/modules/cloud/vmware/vmware_guest.py'
            ],
            'Jinja2 includes in ansible template module': [
                'lib/ansible/modules/files/template.py'
            ],
            ': ec2_vpc_route_table module': [
                'lib/ansible/modules/cloud/amazon/ec2_vpc_route_table.py'
            ],
            'copy shell  modules': [
                'lib/ansible/modules/files/copy.py',
                'lib/ansible/modules/commands/shell.py'
            ],
            ':\ndocker.py': [
                'lib/ansible/modules/cloud/docker/_docker.py'
            ],
            ': s3 module': [
                'lib/ansible/modules/cloud/amazon/_s3.py'
            ],
            'The new ldap_attr module.': [
                'lib/ansible/modules/net_tools/ldap/ldap_attr.py'
            ],
            '- Ansible Core/Cisco ios_command module': [
                'lib/ansible/modules/network/ios/ios_command.py'
            ]
        }

        #COMPONENTS = {
        #    '- Ansible Core/Cisco ios_command module': [
        #        'lib/ansible/modules/network/ios/ios_command.py'
        #    ]
        #}

        for COMPONENT,EXPECTED in COMPONENTS.items():
            res = self.component_matcher.search_by_regex_modules(COMPONENT)
            self.assertEqual(EXPECTED, res)

    # FIXME
    # [2873] ec2_asg (AWS EC2 auto scaling groups)
    # [2998] junos_command (but not only !)
    # [3531] lib/ansible/modules/storage/netapp/sf_volume-manager.py
    # [3739] tower_job_list module but I believe that also the other tower_* module have the same error
    # [4039] netapp_e_storagepool storage module
    # [4774] azure_rm_deployment (although azure_rm_common seems to be at work here)
