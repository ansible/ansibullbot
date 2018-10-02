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

        assert 'macros' in data
        assert 'files' in data
        assert 'lib/ansible/cli/galaxy' in data['files']
        assert 'lib/ansible/cli/vault.py' in data['files']
        assert 'lib/ansible/parsing/vault' in data['files']
        assert 'lib/ansible/foobar' in data['files']

        self.assertEqual(
            data['files']['lib/ansible/foobar']['labels'],
            ['ansible', 'bar', 'foo', 'foobar', 'lib']
        )

        self.assertEqual(
            data['files']['lib/ansible/cli/vault.py']['maintainers'],
            ['larry', 'curly', 'moe', 'jeff']
        )

        # double-macro
        assert 'lib/ansible/modules/x/y' in data['files']
        assert 'maintainers' in data['files']['lib/ansible/modules/x/y']
        self.assertEqual(
            data['files']['lib/ansible/modules/x/y']['maintainers'],
            ['steven']
        )

        assert 'team_oneline' in data['macros']
        assert isinstance(data['macros']['team_oneline'], list)
        self.assertEqual(
            data['macros']['team_oneline'],
            ['one', 'line', 'at', 'a', 'time']
        )

        self.assertEqual(dict, type(data['files']['packaging']))

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
    @mock.patch('yaml.load', ruamel.yaml.YAML().load)
    def test_keywords_order(self):
        """Check that:
        - labels are inherited
        - support keyword is inherited when not set
        Use ruamel in order to check that order does't count
        """
        LABELS_SUPPORT_PROPAGATION = """
        macros:
          module_utils: lib/ansible/module_utils
        files:
          $module_utils/network/fw/sub/childA:
          $module_utils/network/fw/sub/childB:
              support: another_level
              labels: labelB
          $module_utils/network/fw/sub:
              support: core
              labels: [fwsub]
          $module_utils/other:
              labels: thing
          $module_utils/network/iwfu.py:
              support: community
              labels: firewall
          $module_utils/network/:
              support: network
              labels: networking
          $module_utils/network/fw:
              labels: firewall
        """

        data = BotMetadataParser.parse_yaml(LABELS_SUPPORT_PROPAGATION)
        self.assertIsInstance(data, ruamel.yaml.comments.CommentedMap)  # ensure mock is effective

        self._test(data)

    def _test(self, data):

        self.assertIn('macros', data)
        self.assertIn('files', data)

        self.assertEqual(set(['lib/ansible/module_utils/network',
                              'lib/ansible/module_utils/network/fw',
                              'lib/ansible/module_utils/network/fw/sub',
                              'lib/ansible/module_utils/network/fw/sub/childA',
                              'lib/ansible/module_utils/network/fw/sub/childB',
                              'lib/ansible/module_utils/network/iwfu.py',
                              'lib/ansible/module_utils/other']),
                         set(data['files'].keys()))

        #### 'labels' key
        self.assertEqual(
            set(data['files']['lib/ansible/module_utils/network']['labels']),
            set(['lib', 'ansible', 'module_utils', 'network', 'networking'])
        )

        self.assertEqual(
            set(data['files']['lib/ansible/module_utils/network/fw']['labels']),
            set(['lib', 'ansible', 'module_utils', 'network', 'networking', 'fw', 'firewall'])
        )

        self.assertEqual(
            set(data['files']['lib/ansible/module_utils/network/fw/sub']['labels']),
            set(['lib', 'ansible', 'module_utils', 'network', 'networking', 'fw', 'firewall', 'sub', 'fwsub'])
        )

        self.assertEqual(
            set(data['files']['lib/ansible/module_utils/network/fw/sub/childA']['labels']),
            set(['lib', 'ansible', 'module_utils', 'network', 'networking', 'fw', 'firewall', 'sub', 'fwsub', 'childA'])
        )

        self.assertEqual(
            set(data['files']['lib/ansible/module_utils/network/fw/sub/childB']['labels']),
            set(['lib', 'ansible', 'module_utils', 'network', 'networking', 'fw', 'firewall', 'sub', 'fwsub', 'childB', 'labelB'])
        )

        self.assertEqual(
            set(data['files']['lib/ansible/module_utils/network/iwfu.py']['labels']),
            set(['lib', 'ansible', 'module_utils', 'network', 'networking', 'iwfu', 'firewall'])
        )

        #### 'support' key
        self.assertEqual(
            data['files']['lib/ansible/module_utils/network']['support'], ['network']
        )

        # subpath: support key is inherited
        self.assertEqual(
            data['files']['lib/ansible/module_utils/network/fw']['support'], ['network']
        )

        # subpath: support key is overridden
        self.assertEqual(
            data['files']['lib/ansible/module_utils/network/iwfu.py']['support'], ['community']
        )

        # subpath: support key is overridden
        self.assertEqual(
            data['files']['lib/ansible/module_utils/network/fw/sub']['support'], ['core']
        )

        # subpath: support key is inherited
        self.assertEqual(
            data['files']['lib/ansible/module_utils/network/fw/sub/childA']['support'], ['core']
        )

        # subpath: support key is overridden
        self.assertEqual(
            data['files']['lib/ansible/module_utils/network/fw/sub/childB']['support'], ['another_level']
        )

        # default value for support isn't set by botmeta
        self.assertNotIn('support', data['files']['lib/ansible/module_utils/other'])

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
            data['files']['lib/ansible/module_utils/network']['supported_by'], ['network']
        )

        # subpath: supported_by key is inherited
        self.assertEqual(
            data['files']['lib/ansible/module_utils/network/fw']['supported_by'], ['network']
        )

        # subpath: supported_by key is overridden
        self.assertEqual(
            data['files']['lib/ansible/module_utils/network/iwfu.py']['supported_by'], ['community']
        )

        # subpath: supported_by key is overridden
        self.assertEqual(
            data['files']['lib/ansible/module_utils/network/fw/sub']['supported_by'], ['core']
        )

        # subpath: supported_by key is inherited
        self.assertEqual(
            data['files']['lib/ansible/module_utils/network/fw/sub/childA']['supported_by'], ['core']
        )

        # subpath: supported_by key is overridden
        self.assertEqual(
            data['files']['lib/ansible/module_utils/network/fw/sub/childB']['supported_by'], ['another_level']
        )

        # default value for supported_by isn't set by botmeta
        self.assertNotIn('supported_by', data['files']['lib/ansible/module_utils/other'])
