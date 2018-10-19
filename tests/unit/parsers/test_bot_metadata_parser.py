#!/usr/bin/env python

import inspect
import os
import shutil
import unittest

import pytest

from ansibullbot.parsers.botmetadata import BotMetadataParser

import ruamel.yaml
import six

six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

EXAMPLE1 = """
---
macros:
    team_ansible:
        - larry
        - curly
        - moe
    team_cloud:
        - bob
        - sally
    team_cloud_aws:
        - jeff
    team_galaxy:
        - steven
    team_oneline: one line at a time
    modules: lib/ansible/modules
files:
    lib/ansible/cli/galaxy/:
        maintainers: $team_ansible $team_galaxy
        reviewers: jimbob
        ignored: nobody
        labels: cli galaxy

    lib/ansible/parsing/vault/: &VAULT
        maintainers: $team_ansible jeff
        reviewers: jimbob
        ignored: nobody
        labels: parsing vault
        keywords: ["vault encrypt", "vault decrypt"]

    lib/ansible/cli/vault.py:
        <<: *VAULT

    lib/ansible/foobar/:
        maintainers: $team_ansible jeff
        reviewers: jimbob
        ignored: nobody
        labels:
            - foo
            - bar
    # using macro for the key and maintainers
    $modules/x/y: $team_galaxy

    packaging/:
"""


class TestBotMetaIndexerBase(unittest.TestCase):
    def setUp(self):
        cache = '/tmp/testcache'
        if os.path.isdir(cache):
            shutil.rmtree(cache)
        os.makedirs(cache)


class TestBotMetadataParserProperties(TestBotMetaIndexerBase):
    def runTest(self):
        assert hasattr(BotMetadataParser, 'parse_yaml')


class TestBotMetadataParserEx1(TestBotMetaIndexerBase):
    def runTest(self):
        data = BotMetadataParser.parse_yaml(EXAMPLE1)

        assert u'macros' in data
        assert u'files' in data
        assert u'lib/ansible/cli/galaxy' in data[u'files']
        assert u'lib/ansible/cli/vault.py' in data[u'files']
        assert u'lib/ansible/parsing/vault' in data[u'files']
        assert u'lib/ansible/foobar' in data[u'files']

        self.assertEqual(
            data[u'files'][u'lib/ansible/foobar'][u'labels'],
            [u'ansible', u'bar', u'foo', u'foobar', u'lib']
        )

        self.assertEqual(
            data[u'files'][u'lib/ansible/cli/vault.py'][u'maintainers'],
            [u'larry', u'curly', u'moe', u'jeff'],
        )

        # double-macro
        assert u'lib/ansible/modules/x/y' in data[u'files']
        assert u'maintainers' in data[u'files'][u'lib/ansible/modules/x/y']
        self.assertEqual(
            data[u'files'][u'lib/ansible/modules/x/y'][u'maintainers'],
            [u'steven']
        )

        assert u'team_oneline' in data[u'macros']
        assert isinstance(data[u'macros'][u'team_oneline'], list)
        self.assertEqual(
            data[u'macros'][u'team_oneline'],
            [u'one', u'line', u'at', u'a', u'time']
        )

        self.assertEqual(dict, type(data[u'files'][u'packaging']))


class TestBotMetadataParserFileExample1(TestBotMetaIndexerBase):
    def runTest(self):
        fn = 'metadata_1.yml'
        fn = os.path.join(os.path.dirname(__file__), fn)
        with open(fn, 'rb') as f:
            data = f.read()

        pdata = BotMetadataParser.parse_yaml(data)


class TestBotMetadataPropagation(TestBotMetaIndexerBase):
    """Check that:
    - labels are inherited
    - support keyword is inherited when not set
    """
    def test_keywords(self):
        LABELS_SUPPORT_PROPAGATION = """
        macros:
          module_utils: lib/ansible/module_utils
        files:
          $module_utils/network/:
              support: network
              labels: networking
          $module_utils/network/fw:
              labels: firewall
          $module_utils/network/fw/sub:
              support: core
              labels: [fwsub]
          $module_utils/network/fw/sub/childA:
          $module_utils/network/fw/sub/childB:
              support: another_level
              labels: labelB
          $module_utils/network/iwfu.py:
              support: community
              labels: firewall
          $module_utils/other:
              labels: thing
        """

        data = BotMetadataParser.parse_yaml(LABELS_SUPPORT_PROPAGATION)
        self._test(data)

    @pytest.mark.skip(
        reason=
        'Current way of mocking prevents us '
        'from patching unicode aware loader',
    )

    def _test(self, data):

        assert u'macros' in data
        assert u'files' in data

        self.assertEqual(set([u'lib/ansible/module_utils/network',
                              u'lib/ansible/module_utils/network/fw',
                              u'lib/ansible/module_utils/network/fw/sub',
                              u'lib/ansible/module_utils/network/fw/sub/childA',
                              u'lib/ansible/module_utils/network/fw/sub/childB',
                              u'lib/ansible/module_utils/network/iwfu.py',
                              u'lib/ansible/module_utils/other']),
                         set(data[u'files'].keys()))

        #### 'labels' key
        self.assertEqual(
            set(data[u'files'][u'lib/ansible/module_utils/network'][u'labels']),
            set([u'lib', u'ansible', u'module_utils', u'network', u'networking'])
        )

        self.assertEqual(
            set(data[u'files'][u'lib/ansible/module_utils/network/fw'][u'labels']),
            set([u'lib', u'ansible', u'module_utils', u'network', u'networking', u'fw', u'firewall'])
        )

        self.assertEqual(
            set(data[u'files'][u'lib/ansible/module_utils/network/fw/sub'][u'labels']),
            set([u'lib', u'ansible', u'module_utils', u'network', u'networking', u'fw', u'firewall', u'sub', u'fwsub'])
        )

        self.assertEqual(
            set(data[u'files'][u'lib/ansible/module_utils/network/fw/sub/childA'][u'labels']),
            set([u'lib', u'ansible', u'module_utils', u'network', u'networking', u'fw', u'firewall', u'sub', u'fwsub', u'childA'])
        )

        self.assertEqual(
            set(data[u'files'][u'lib/ansible/module_utils/network/fw/sub/childB'][u'labels']),
            set([u'lib', u'ansible', u'module_utils', u'network', u'networking', u'fw', u'firewall', u'sub', u'fwsub', u'childB', u'labelB'])
        )

        self.assertEqual(
            set(data[u'files'][u'lib/ansible/module_utils/network/iwfu.py'][u'labels']),
            set([u'lib', u'ansible', u'module_utils', u'network', u'networking', u'iwfu', u'firewall'])
        )

        #### 'support' key
        self.assertEqual(
            data[u'files'][u'lib/ansible/module_utils/network'][u'support'], [u'network']
        )

        # subpath: support key is inherited
        self.assertEqual(
            data[u'files'][u'lib/ansible/module_utils/network/fw'][u'support'], [u'network']
        )

        # subpath: support key is overridden
        self.assertEqual(
            data[u'files'][u'lib/ansible/module_utils/network/iwfu.py'][u'support'], [u'community']
        )

        # subpath: support key is overridden
        self.assertEqual(
            data[u'files'][u'lib/ansible/module_utils/network/fw/sub'][u'support'], [u'core']
        )

        # subpath: support key is inherited
        self.assertEqual(
            data[u'files'][u'lib/ansible/module_utils/network/fw/sub/childA'][u'support'], [u'core']
        )

        # subpath: support key is overridden
        self.assertEqual(
            data[u'files'][u'lib/ansible/module_utils/network/fw/sub/childB'][u'support'], [u'another_level']
        )

        # default value for support isn't set by botmeta
        self.assertNotIn(u'support', data[u'files'][u'lib/ansible/module_utils/other'])

    @pytest.mark.skip(
        reason=
        'Current way of mocking prevents us '
        'from patching unicode aware loader',
    )
    @mock.patch('yaml.load', ruamel.yaml.YAML().load)
    def test_supported_by_order(self):
        """Check that:
        - supported_by keyword is inherited when not set
        Use ruamel in order to check that order does't count
        """
        LABELS_SUPPORTED_BY_PROPAGATION = """
        macros:
          module_utils: lib/ansible/module_utils
        files:
          $module_utils/network/fw/sub/childA:
          $module_utils/network/fw/sub/childB:
              supported_by: another_level
              labels: labelB
          $module_utils/network/fw/sub:
              supported_by: core
              labels: [fwsub]
          $module_utils/other:
              labels: thing
          $module_utils/network/iwfu.py:
              supported_by: community
              labels: firewall
          $module_utils/network/:
              supported_by: network
              labels: networking
          $module_utils/network/fw:
              labels: firewall
        """

        data = BotMetadataParser.parse_yaml(LABELS_SUPPORTED_BY_PROPAGATION)
        self.assertIsInstance(data, ruamel.yaml.comments.CommentedMap)  # ensure mock is effective

        #### 'supported_by' key
        self.assertEqual(
            data[u'files'][u'lib/ansible/module_utils/network'][u'supported_by'], [u'network']
        )

        # subpath: supported_by key is inherited
        self.assertEqual(
            data[u'files'][u'lib/ansible/module_utils/network/fw'][u'supported_by'], [u'network']
        )

        # subpath: supported_by key is overridden
        self.assertEqual(
            data[u'files'][u'lib/ansible/module_utils/network/iwfu.py'][u'supported_by'], [u'community']
        )

        # subpath: supported_by key is overridden
        self.assertEqual(
            data[u'files'][u'lib/ansible/module_utils/network/fw/sub'][u'supported_by'], [u'core']
        )

        # subpath: supported_by key is inherited
        self.assertEqual(
            data[u'files'][u'lib/ansible/module_utils/network/fw/sub/childA'][u'supported_by'], [u'core']
        )

        # subpath: supported_by key is overridden
        self.assertEqual(
            data[u'files'][u'lib/ansible/module_utils/network/fw/sub/childB'][u'supported_by'], [u'another_level']
        )

        # default value for supported_by isn't set by botmeta
        self.assertNotIn(u'supported_by', data[u'files'][u'lib/ansible/module_utils/other'])
