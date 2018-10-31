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
        cmd = u"git clone --depth=1 --single-branch %s %s" % (self.repo, self.checkoutdir)
        (rc, so, se) = run_command(cmd)
        if rc:
            raise Exception(u"Fail to execute '{}: {} ({}, {})'".format(cmd, rc, so, se))

    def update_checkout(self):
        return False


class TestComponentMatcher(TestCase):

    @classmethod
    def setUpClass(cls):
        """Init the matcher"""
        cachedir = tempfile.mkdtemp()
        gitrepo = GitShallowRepo(cachedir=cachedir, repo=ComponentMatcher.REPO)
        gitrepo.update()

        file_indexer = FileIndexer(gitrepo=gitrepo)
        file_indexer.get_files()
        file_indexer.parse_metadata()

        cls.component_matcher = ComponentMatcher(email_cache={}, gitrepo=gitrepo, file_indexer=file_indexer)

    @classmethod
    def tearDownClass(cls):
        """suppress temp dir"""
        shutil.rmtree(cls.component_matcher.gitrepo.checkoutdir)

    def test_get_meta_for_file_wildcard(self):
        self.component_matcher.file_indexer.botmeta = self.component_matcher.BOTMETA = {
            u'files': {
                u'lib/ansible/plugins/action/junos': {
                    u'maintainers': [u'gundalow'],
                    u'labels': [u'networking'],
                }
            }
        }
        result = self.component_matcher.get_meta_for_file(u'lib/ansible/plugins/action/junos_config.py')
        self.assertEqual(result[u'labels'], [u'networking'])
        self.assertEqual(result[u'maintainers'], [u'gundalow'])

    def test_get_meta_for_file_wildcard_multiple(self):
        self.component_matcher.file_indexer.botmeta = self.component_matcher.BOTMETA = {
            u'files': {
                u'lib/ansible/plugins/action/junos_config.py': {
                    u'maintainers': [u'privateip'],
                    u'labels': [u'config'],
                    u'notified': [u'jctanner'],
                },
                u'lib/ansible/plugins/action/junos': {
                    u'maintainers': [u'gundalow'],
                    u'labels': [u'networking'],
                    u'notified': [u'mkrizek'],
                }
            }
        }
        result = self.component_matcher.get_meta_for_file(u'lib/ansible/plugins/action/junos_config.py')

        assert sorted(result[u'notify']) == sorted([u'gundalow', u'mkrizek', u'jctanner', u'privateip'])
        assert sorted(result[u'labels']) == sorted([u'networking', u'config'])
        assert sorted(result[u'maintainers']) == sorted([u'gundalow', u'privateip'])

    def test_get_meta_for_file_pyfile(self):
        self.component_matcher.file_indexer.botmeta = self.component_matcher.BOTMETA = {
            u'files': {
                u'lib/ansible/modules/packaging/os/yum.py': {
                    u'maintainers': [u'maxamillion'],
                }
            }
        }
        result = self.component_matcher.get_meta_for_file(u'lib/ansible/modules/packaging/os/yum.py')
        self.assertEqual(result[u'maintainers'], [u'maxamillion'])

    def test_get_meta_for_file_powershell(self):
        self.component_matcher.file_indexer.botmeta = self.component_matcher.BOTMETA = {
            u'files': {
                u'lib/ansible/modules/windows/win_ping.py': {
                    u'maintainers': [u'jborean93'],
                    u'labels': [u'windoez'],
                }
            }
        }
        result = self.component_matcher.get_meta_for_file(u'lib/ansible/modules/windows/win_ping.ps1')
        self.assertEqual(result[u'labels'], [u'windoez'])
        self.assertEqual(result[u'maintainers'], [u'jborean93'])

    def test_reduce_filepaths(self):

        filepaths = [u'commands/command.py', u'lib/ansible/modules/commands/command.py']
        reduced = self.component_matcher.reduce_filepaths(filepaths)
        self.assertEqual(reduced, [u'lib/ansible/modules/commands/command.py'])

    def test_search_by_filepath(self):

        COMPONENTS = {
            u'/usr/lib/python2.7/site-packages/ansible/modules/core/packaging/os/rhn_register.py': [
                u'lib/ansible/modules/packaging/os/rhn_register.py',
                u'lib/ansible/modules/packaging/os/rhn_register.py'
            ],
            u'module/network/ios/ios_facts': [
                u'lib/ansible/modules/network/ios/ios_facts.py',
                u'lib/ansible/modules/network/ios/ios_facts.py'
            ],
            # Doesn't work, lib/ansible/modules/network/nso/nso_query.py is
            # found
            #'json_query': [
            #    'lib/ansible/plugins/filter/json_query.py',
            #    'lib/ansible/plugins/filter/json_query.py'
            #],
            u'module_common.py': [
                u'lib/ansible/executor/module_common.py',
                u'lib/ansible/executor/module_common.py'
            ],
            u'/network/dellos6/dellos6_config': [
                u'lib/ansible/modules/network/dellos6/dellos6_config.py',
                u'lib/ansible/modules/network/dellos6/dellos6_config.py'
            ],
            u'module_utils/vmware': [
                u'lib/ansible/module_utils/vmware.py',
                u'lib/ansible/module_utils/vmware.py'
            ],
            u'`azure_rm.py`': [
                u'contrib/inventory/azure_rm.py',
                u'contrib/inventory/azure_rm.py'
            ],
            u'vmware_inventory': [
                u'contrib/inventory/vmware_inventory.py',
                u'contrib/inventory/vmware_inventory.py'
            ],
            u'skippy': [
                u'lib/ansible/plugins/callback/skippy.py',
                u'lib/ansible/plugins/callback/skippy.py'
            ],
            u'azure_rm_common': [
                u'lib/ansible/module_utils/azure_rm_common.py',
                u'lib/ansible/module_utils/azure_rm_common.py'
            ],
            u'junit': [
                u'lib/ansible/plugins/callback/junit.py',
                u'lib/ansible/plugins/callback/junit.py'
            ],
            u'`plugins/strategy/__init__.py`': [
                u'lib/ansible/plugins/strategy/__init__.py',
                u'lib/ansible/plugins/strategy/__init__.py'
            ],
            u'- jabber.py': [
                #'lib/ansible/plugins/callback/jabber.py',
                #'lib/ansible/plugins/callback/jabber.py'
                u'lib/ansible/modules/notification/jabber.py',
                u'lib/ansible/modules/notification/jabber.py',
            ],
            u'- ios_config.py': [
                #'lib/ansible/plugins/action/ios_config.py',
                #'lib/ansible/plugins/action/ios_config.py'
                u'lib/ansible/modules/network/ios/ios_config.py',
                u'lib/ansible/modules/network/ios/ios_config.py',
            ],
            # Unable to follow symlink ? Besides a new file exists: test/sanity/pylint/config/ansible-test
            #'ansible-test': [
            #    'test/runner/ansible-test',
            #    'test/runner/ansible-test'
            #],
            u'inventory manager': [
                None,
                u'lib/ansible/inventory/manager.py'
            ],
            # Doesn't work
            #'ansible/hacking/test-module': [
            #    'hacking/test-module',
            #    'hacking/test-module'
            #],
            u'- ansible-connection': [
                u'bin/ansible-connection',
                u'bin/ansible-connection'
            ],
            # Doesn't work
            #'`validate-modules`': [
            #    'test/sanity/validate-modules/validate-modules',
            #    'test/sanity/validate-modules/validate-modules'
            #],
            u'`modules/cloud/docker/docker_container.py`': [
                u'lib/ansible/modules/cloud/docker/docker_container.py',
                u'lib/ansible/modules/cloud/docker/docker_container.py'
            ],
            u'packaging/language/maven_artifact': [
                u'lib/ansible/modules/packaging/language/maven_artifact.py',
                u'lib/ansible/modules/packaging/language/maven_artifact.py'
            ],
            u'`lib/ansible/executor/module_common.py`': [
                u'lib/ansible/executor/module_common.py',
                u'lib/ansible/executor/module_common.py'
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
            u'ec2.py': [
                #{'context': None, 'expected': ['contrib/inventory/ec2.py']},
                {u'context': u'contrib/inventory', u'expected': [u'contrib/inventory/ec2.py']},
                {u'context': u'lib/ansible/modules', u'expected': [u'lib/ansible/modules/cloud/amazon/ec2.py']},
            ],
            u'netapp_e_storagepool storage module': [
                {u'context': u'lib/ansible/modules', u'partial': False, u'expected': []},
                {u'context': u'lib/ansible/modules', u'partial': True, u'expected': [u'lib/ansible/modules/storage/netapp/netapp_e_storagepool.py']},
            ],
            u'ansible/files/modules/archive.py': [
                {u'context': None, u'partial': True, u'expected': [u'lib/ansible/modules/files/archive.py']}
            ],
            # Doesn't work
            #'lib/ansible/modules/cloud/amazon': [
            #    {u'context': None, 'partial': False, 'expected': ['lib/ansible/modules/cloud/amazon']},
            #    {u'context': None, 'partial': True, 'expected': ['lib/ansible/modules/cloud/amazon']}
            #],
            #'modules/network/f5': [
            #    {u'context': None, 'partial': False, 'expected': ['lib/ansible/modules/network/f5']},
            #    {u'context': None, 'partial': True, 'expected': ['lib/ansible/modules/network/f5']}
            #],
            #'modules/network/iosxr': [
            #    {u'context': None, 'partial': False, 'expected': ['lib/ansible/modules/network/iosxr']},
            #    {u'context': None, 'partial': True, 'expected': ['lib/ansible/modules/network/iosxr']}
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
                CONTEXT = v2.get(u'context')
                PARTIAL = v2.get(u'partial')
                EXPECTED = v2.get(u'expected')
                res = self.component_matcher.search_by_filepath(COMPONENT, context=CONTEXT, partial=PARTIAL)
                assert EXPECTED == res

    def test_search_by_regex_module_globs(self):

        COMPONENTS = {
            u'All AWS modules': u'lib/ansible/modules/cloud/amazon',
            u'ec2_* modules': u'lib/ansible/modules/cloud/amazon',
            u'GCP ansible modules': u'lib/ansible/modules/cloud/google',
            u'BigIP modules': u'lib/ansible/modules/network/f5',
            u'NXOS modules': u'lib/ansible/modules/network/nxos',
            u'azurerm modules': u'lib/ansible/modules/cloud/azure',
            u'ansiballz/ziploader for modules': [],
            u'dellos*_* network modules': [],
            u'elasticache modules': [
                u'lib/ansible/modules/cloud/amazon/elasticache.py',
                u'lib/ansible/modules/cloud/amazon/elasticache_facts.py',
                u'lib/ansible/modules/cloud/amazon/elasticache_parameter_group.py',
                u'lib/ansible/modules/cloud/amazon/elasticache_snapshot.py',
                u'lib/ansible/modules/cloud/amazon/elasticache_subnet_group.py',
            ],
            u'All FreeIPA Modules': [],
            u'All modules': [],
            u'All Cisco IOS Modules': [],
            u'All EC2 based modules, possibly more.': u'lib/ansible/modules/cloud/amazon',
        }

        for COMPONENT,EXPECTED in COMPONENTS.items():
            if not isinstance(EXPECTED, list):
                EXPECTED = [EXPECTED]
            res = self.component_matcher.search_by_regex_module_globs(COMPONENT)

            self.assertEqual(EXPECTED, res)

    def test_search_by_keywords(self):

        COMPONENTS = {
            #'inventory script': [u'lib/ansible/plugins/inventory/script.py'] #ix2390 https://github.com/ansible/ansible/issues/24545
            u'inventory script': [u'contrib/inventory']  # ix2390 https://github.com/ansible/ansible/issues/24545
        }

        for k,v in COMPONENTS.items():
            COMPONENT = k
            EXPECTED = v
            res = self.component_matcher.search_by_keywords(COMPONENT)
            self.assertEqual(EXPECTED, res)

    def test_search_by_regex_modules(self):

        COMPONENTS = {
            u'Module: include_role': [u'lib/ansible/modules/utilities/logic/include_role.py'],
            u'module: include_role': [u'lib/ansible/modules/utilities/logic/include_role.py'],
            u'module include_role': [u'lib/ansible/modules/utilities/logic/include_role.py'],
            #'ec2_asg (AWS EC2 auto scaling groups)': ['lib/ansible/modules/cloud/amazon/ec2_asg.py'],
            u'junos_command (but not only !)': [u'lib/ansible/modules/network/junos/junos_command.py'],
            u'tower_job_list module but I believe that also the other tower_* module have the same error':
                [u'lib/ansible/modules/web_infrastructure/ansible_tower/tower_job_list.py'],
            #'F5 bigip (bigip_selfip)': [u'lib/ansible/modules/network/f5/bigip_selfip.py'],
            u'ansible_modules_vsphere_guest': [u'lib/ansible/modules/cloud/vmware/_vsphere_guest.py'],
            u'shell-module': [u'lib/ansible/modules/commands/shell.py'],
            u'the docker_volume command': [u'lib/ansible/modules/cloud/docker/docker_volume.py'],
            u'Azure Inventory Script - azure_rm.py': [],
            u':\n`at` module': [u'lib/ansible/modules/system/at.py'],
            u':\n`rax` module': [u'lib/ansible/modules/cloud/rackspace/rax.py'],
            u'`apt_key` module': [u'lib/ansible/modules/packaging/os/apt_key.py'],
            u'`apt` module': [u'lib/ansible/modules/packaging/os/apt.py'],
            u'`ecs_service` module': [u'lib/ansible/modules/cloud/amazon/ecs_service.py'],
            u'`meta` module': [u'lib/ansible/modules/utilities/helper/meta.py'],
            #'`meta` module': [u'lib/ansible/modules/utilities/helper/meta.py'],
            u'`mysql_user` module': [u'lib/ansible/modules/database/mysql/mysql_user.py'],
            u'`s3` module': [u'lib/ansible/modules/cloud/amazon/_s3.py'],
            u'`user` module': [u'lib/ansible/modules/system/user.py'],
            u'the "user" module': [u'lib/ansible/modules/system/user.py'],
            u'`ansible_module_ec2_ami_copy.py`': [u'lib/ansible/modules/cloud/amazon/ec2_ami_copy.py'],
            u'module: `include_vars `': [u'lib/ansible/modules/utilities/logic/include_vars.py'],
            u'rabbitmq_plugin  module': [u'lib/ansible/modules/messaging/rabbitmq/rabbitmq_plugin.py'],
            #'F5 bigip (bigip_selfip)': [u'lib/ansible/modules/network/f5/bigip_selfip.py'],
            u'module: `vsphere_guest`': [u'lib/ansible/modules/cloud/vmware/_vsphere_guest.py'],
            u'Add to vmware_guest module, Clone to Virtual Machine task': [
                u'lib/ansible/modules/cloud/vmware/vmware_guest.py'
            ],
            u'Jinja2 includes in ansible template module': [
                u'lib/ansible/modules/files/template.py'
            ],
            u': ec2_vpc_route_table module': [
                u'lib/ansible/modules/cloud/amazon/ec2_vpc_route_table.py'
            ],
            u'copy shell  modules': [
                u'lib/ansible/modules/files/copy.py',
                u'lib/ansible/modules/commands/shell.py'
            ],
            u':\ndocker.py': [
                u'lib/ansible/modules/cloud/docker/_docker.py'
            ],
            u': s3 module': [
                u'lib/ansible/modules/cloud/amazon/_s3.py'
            ],
            u'The new ldap_attr module.': [
                u'lib/ansible/modules/net_tools/ldap/ldap_attr.py'
            ],
            u'- Ansible Core/Cisco ios_command module': [
                u'lib/ansible/modules/network/ios/ios_command.py'
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
