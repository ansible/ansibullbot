import shutil
import tempfile
from unittest import TestCase

import pytest

from ansibullbot.utils.component_tools import AnsibleComponentMatcher as ComponentMatcher
from ansibullbot.utils.component_tools import make_prefixes
from ansibullbot.utils.git_tools import GitRepoWrapper
from ansibullbot.utils.systemtools import run_command


class TestMakePrefixes(TestCase):

    def test_simple_path_is_split_correctly(self):
        fp = 'lib/ansible/foo/bar'
        prefixes = make_prefixes(fp)
        assert len(prefixes) == len(fp)
        assert fp in prefixes
        assert prefixes[0] == fp
        assert prefixes[-1] == 'l'


class GitShallowRepo(GitRepoWrapper):
    """Perform a shallow copy"""

    def create_checkout(self):
        """checkout ansible"""
        cmd = "git clone --depth=1 --single-branch %s %s" % (self.repo, self.checkoutdir)
        (rc, so, se) = run_command(cmd)
        if rc:
            raise Exception(f"Fail to execute '{cmd}: {rc} ({so}, {se})'")

    def update_checkout(self):
        return False


class TestComponentMatcher(TestCase):

    @classmethod
    def setUpClass(cls):
        """Init the matcher"""
        cachedir = tempfile.mkdtemp()
        gitrepo = GitShallowRepo(cachedir=cachedir, repo='https://github.com/ansible/ansible')
        gitrepo.update()

        cls.component_matcher = ComponentMatcher(email_cache={}, gitrepo=gitrepo)

    @classmethod
    def tearDownClass(cls):
        """suppress temp dir"""
        shutil.rmtree(cls.component_matcher.gitrepo.checkoutdir)

    @pytest.mark.skip(reason="FIXME")    
    def test_get_meta_for_file_wildcard(self):
        self.component_matcher.botmeta = {
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

    @pytest.mark.skip(reason="FIXME")    
    def test_get_meta_for_file_wildcard_multiple(self):
        self.component_matcher.botmeta = {
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

        assert sorted(result['notify']) == sorted(['gundalow', 'mkrizek', 'jctanner', 'privateip'])
        assert sorted(result['labels']) == sorted(['networking', 'config'])
        assert sorted(result['maintainers']) == sorted(['gundalow', 'privateip'])

    @pytest.mark.skip(reason="FIXME")    
    def test_get_meta_for_file_pyfile(self):
        self.component_matcher.botmeta = {
            'files': {
                'lib/ansible/modules/packaging/os/yum.py': {
                    'ignored': ['verm666'],  # 'verm666' is also listed as an author of yum module
                    'maintainers': ['maxamillion', 'verm666'],
                }
            }
        }
        result = self.component_matcher.get_meta_for_file('lib/ansible/modules/packaging/os/yum.py')
        assert sorted(result['maintainers']) == sorted([
            'Akasurde',
            'ansible',
            'berenddeschouwer',
            'kustodian',
            'maxamillion',
        ])
        assert sorted(result['notify']) == sorted([
            'Akasurde',
            'ansible',
            'berenddeschouwer',
            # u'kustodian',  added in botmeta, not authors, to be merged later
            'maxamillion',
        ])

    def test_get_meta_support_core_from_module(self):
        self.component_matcher.botmeta = {
            'files': {
                'lib/ansible/modules/packaging/os/yum.py': {
                    'ignored': ['verm666'],  # 'verm666' is also listed as an author of yum module
                    'maintainers': ['maxamillion', 'verm666'],
                }
            }
        }
        result = self.component_matcher.get_meta_for_file('lib/ansible/modules/packaging/os/yum.py')
        assert result['support'] == 'core'

    def test_get_meta_support_core_filter_plugin(self):
        self.component_matcher.botmeta = {
            'files': {
                'lib/ansible/plugins/filter/': {
                    'support': 'community',
                    'supported_by': 'community',
                },
                'lib/ansible/plugins/filter/core.py': {
                    'support': 'core',
                    'supported_by': 'core'
                },
            }
        }
        result = self.component_matcher.get_meta_for_file('lib/ansible/plugins/filter/core.py')
        assert result['support'] == 'core'

    def test_get_meta_support_new_filter_plugin(self):
        self.component_matcher.botmeta = {
            'files': {
                'lib/ansible/plugins/filter/': {
                    'support': 'community',
                    'supported_by': 'community',
                },
                'lib/ansible/plugins/filter/core.py': {
                    'support': 'core',
                    'supported_by': 'core'
                },
            }
        }
        result = self.component_matcher.get_meta_for_file('lib/ansible/plugins/filter/new.py')
        assert result['support'] == 'community'

    @pytest.mark.skip(reason="FIXME")
    def test_get_meta_for_file_powershell(self):
        self.component_matcher.botmeta = {
            'files': {
                'lib/ansible/modules/windows/win_ping.py': {
                    'maintainers': ['jborean93'],
                    'labels': ['windoez'],
                }
            }
        }
        result = self.component_matcher.get_meta_for_file('lib/ansible/modules/windows/win_ping.ps1')
        assert result['labels'] == ['windoez']
        #import epdb; epdb.st()
        #expected_maintainers = sorted([u'cchurch', u'jborean93'])
        expected_maintainers = sorted(['jborean93'])
        assert sorted(result['maintainers']) == expected_maintainers

    def test_reduce_filepaths(self):

        filepaths = ['commands/command.py', 'lib/ansible/modules/commands/command.py']
        reduced = self.component_matcher.reduce_filepaths(filepaths)
        self.assertEqual(reduced, ['lib/ansible/modules/commands/command.py'])

    @pytest.mark.skip(reason="FIXME")
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

    @pytest.mark.skip(reason="FIXME")
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
                CONTEXT = v2.get('context')
                PARTIAL = v2.get('partial')
                EXPECTED = v2.get('expected')
                res = self.component_matcher.search_by_filepath(COMPONENT, context=CONTEXT, partial=PARTIAL)
                assert EXPECTED == res

    @pytest.mark.skip(reason="FIXME")
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
            #u'elasticache modules': [
            #    u'lib/ansible/modules/cloud/amazon/elasticache.py',
            #    u'lib/ansible/modules/cloud/amazon/elasticache_info.py',
            #    u'lib/ansible/modules/cloud/amazon/elasticache_parameter_group.py',
            #    u'lib/ansible/modules/cloud/amazon/elasticache_snapshot.py',
            #    u'lib/ansible/modules/cloud/amazon/elasticache_subnet_group.py',
            #],
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
            #'inventory script': [u'lib/ansible/plugins/inventory/script.py'] #ix2390 https://github.com/ansible/ansible/issues/24545
            'inventory script': ['contrib/inventory']  # ix2390 https://github.com/ansible/ansible/issues/24545
        }

        for k,v in COMPONENTS.items():
            COMPONENT = k
            EXPECTED = v
            res = self.component_matcher.search_by_keywords(COMPONENT)
            self.assertEqual(EXPECTED, res)

    @pytest.mark.skip(reason="FIXME")
    def test_search_by_regex_modules(self):

        COMPONENTS = {
            'Module: include_role': ['lib/ansible/modules/utilities/logic/include_role.py'],
            'module: include_role': ['lib/ansible/modules/utilities/logic/include_role.py'],
            'module include_role': ['lib/ansible/modules/utilities/logic/include_role.py'],
            #'ec2_asg (AWS EC2 auto scaling groups)': ['lib/ansible/modules/cloud/amazon/ec2_asg.py'],
            'junos_command (but not only !)': ['lib/ansible/modules/network/junos/junos_command.py'],
            'tower_job_list module but I believe that also the other tower_* module have the same error':
                ['lib/ansible/modules/web_infrastructure/ansible_tower/tower_job_list.py'],
            #'F5 bigip (bigip_selfip)': [u'lib/ansible/modules/network/f5/bigip_selfip.py'],
            #u'ansible_modules_vsphere_guest': [
            #    #u'lib/ansible/modules/cloud/vmware/_vsphere_guest.py'
            #    u'lib/ansible/modules/cloud/vmware/vsphere_copy.py'
            #    u'lib/ansible/modules/cloud/vmware/vsphere_file.py',
            #],
            'shell-module': ['lib/ansible/modules/commands/shell.py'],
            'the docker_volume command': ['lib/ansible/modules/cloud/docker/docker_volume.py'],
            'Azure Inventory Script - azure_rm.py': [],
            ':\n`at` module': ['lib/ansible/modules/system/at.py'],
            ':\n`rax` module': ['lib/ansible/modules/cloud/rackspace/rax.py'],
            '`apt_key` module': ['lib/ansible/modules/packaging/os/apt_key.py'],
            '`apt` module': ['lib/ansible/modules/packaging/os/apt.py'],
            '`ecs_service` module': ['lib/ansible/modules/cloud/amazon/ecs_service.py'],
            '`meta` module': ['lib/ansible/modules/utilities/helper/meta.py'],
            #'`meta` module': [u'lib/ansible/modules/utilities/helper/meta.py'],
            '`mysql_user` module': ['lib/ansible/modules/database/mysql/mysql_user.py'],
            #u'`s3` module': [u'lib/ansible/modules/cloud/amazon/_s3.py'],
            '`user` module': ['lib/ansible/modules/system/user.py'],
            'the "user" module': ['lib/ansible/modules/system/user.py'],
            '`ansible_module_ec2_ami_copy.py`': ['lib/ansible/modules/cloud/amazon/ec2_ami_copy.py'],
            'module: `include_vars `': ['lib/ansible/modules/utilities/logic/include_vars.py'],
            'rabbitmq_plugin  module': ['lib/ansible/modules/messaging/rabbitmq/rabbitmq_plugin.py'],
            #'F5 bigip (bigip_selfip)': [u'lib/ansible/modules/network/f5/bigip_selfip.py'],
            #u'module: `vsphere_guest`': [u'lib/ansible/modules/cloud/vmware/_vsphere_guest.py'],
            #u'module: `vsphere_guest`': [
            #    u'lib/ansible/modules/cloud/vmware/vsphere_copy.py'
            #    u'lib/ansible/modules/cloud/vmware/vsphere_file.py',
            #],
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
            #u':\ndocker.py': [
            #    u'lib/ansible/modules/cloud/docker/_docker.py'
            #],
            #u': s3 module': [
            #    u'lib/ansible/modules/cloud/amazon/_s3.py'
            #],
            'The new ldap_attr module.': [
                'lib/ansible/modules/net_tools/ldap/_ldap_attr.py'
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


class TestComponentMatcherInheritance(TestCase):

    @classmethod
    def setUpClass(cls):
        """Init the matcher"""
        cachedir = tempfile.mkdtemp()
        gitrepo = GitShallowRepo(cachedir=cachedir, repo='https://github.com/ansible/ansible')
        gitrepo.update()

        cls.component_matcher = ComponentMatcher(email_cache={}, gitrepo=gitrepo, use_galaxy=False)

    @classmethod
    def tearDownClass(cls):
        """suppress temp dir"""
        shutil.rmtree(cls.component_matcher.gitrepo.checkoutdir)

    def test_get_meta_for_known_file(self):
        self.component_matcher.botmeta = {
            'files': {
                'foo': {
                    'ignored': ['foo_ignored'],
                    'supershipit': ['foo_supershipit'],
                    'maintainers': ['foo_maintainer'],
                },
                'foo/bar': {
                    'ignored': ['bar_ignored'],
                    'supershipit': ['bar_supershipit'],
                    'maintainers': ['bar_maintainer'],
                },
                'foo/bar/baz.py': {
                    'ignored': ['baz_ignored'],
                    'supershipit': ['baz_supershipit'],
                    'maintainers': ['baz_maintainer'],
                    'support': 'community'
                },
            }
        }

        # send in a file that is known
        result = self.component_matcher.get_meta_for_file('foo/bar/baz.py')

        # make sure everything inherited
        keys = ['ignored', 'maintainer', 'supershipit']
        names = ['bar', 'baz', 'foo']
        for key in keys:
            expected = [x + '_' + key for x in names]

            if key == 'ignored':
                key = 'ignore'
            if key == 'maintainer':
                key = 'maintainers'

            assert sorted(result[key]) == sorted(expected)

        # make sure the support level is preserved
        assert result['support'] == 'community'

    def test_get_meta_for_unknown_extension(self):
        self.component_matcher.botmeta = {
            'files': {
                'foo': {
                    'ignored': ['foo_ignored'],
                    'supershipit': ['foo_supershipit'],
                    'maintainers': ['foo_maintainer'],
                },
                'foo/bar': {
                    'ignored': ['bar_ignored'],
                    'supershipit': ['bar_supershipit'],
                    'maintainers': ['bar_maintainer'],
                },
                'foo/bar/baz': {
                    'ignored': ['baz_ignored'],
                    'supershipit': ['baz_supershipit'],
                    'maintainers': ['baz_maintainer'],
                    'support': 'community'
                },
            }
        }

        # send in a file that matches a prefix, but has an unknown extension
        result = self.component_matcher.get_meta_for_file('foo/bar/baz.psx')

        # make sure everything inherited
        keys = ['ignored', 'maintainer', 'supershipit']
        names = ['bar', 'baz', 'foo']
        for key in keys:
            expected = [x + '_' + key for x in names]

            if key == 'ignored':
                key = 'ignore'
            if key == 'maintainer':
                key = 'maintainers'

            assert sorted(result[key]) == sorted(expected)

        # make sure the support level is applied
        assert result['support'] == 'community'

    def test_get_meta_support_inheritance(self):
        self.component_matcher.botmeta = {
            'files': {
                'foo': {
                    'ignored': ['foo_ignored'],
                    'supershipit': ['foo_supershipit'],
                    'maintainers': ['foo_maintainer'],
                },
                'foo/bar': {
                    'ignored': ['bar_ignored'],
                    'supershipit': ['bar_supershipit'],
                    'maintainers': ['bar_maintainer'],
                },
                'foo/bar/baz': {
                    'ignored': ['baz_ignored'],
                    'supershipit': ['baz_supershipit'],
                    'maintainers': ['baz_maintainer'],
                    'support': 'core'
                },
            }
        }

        # send in a file that matches a prefix, but has an unknown extension
        result = self.component_matcher.get_meta_for_file('foo/bar/baz.psx')

        # make sure the support level is applied
        assert result['support'] == 'core'
