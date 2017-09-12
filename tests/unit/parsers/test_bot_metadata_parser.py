#!/usr/bin/env python

import inspect
import os
import shutil
import unittest

from ansibullbot.parsers.botmetadata import BotMetadataParser

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
        assert 'lib/ansible/cli/galaxy/' in data['files']
        assert 'lib/ansible/cli/vault.py' in data['files']
        assert 'lib/ansible/parsing/vault/' in data['files']
        assert 'lib/ansible/foobar/' in data['files']

        self.assertEqual(
            data['files']['lib/ansible/foobar/']['labels'],
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

        self.assertEqual(dict, type(data['files']['packaging/']))

class TestBotMetadataParserFileExample1(TestBotMetaIndexerBase):
    def runTest(self):
        fn = 'metadata_1.yml'
        fn = os.path.join(os.path.dirname(__file__), fn)
        with open(fn, 'rb') as f:
            data = f.read()

        pdata = BotMetadataParser.parse_yaml(data)
