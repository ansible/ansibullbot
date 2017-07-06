#!/usr/bin/env python

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
            data['files']['files']['lib/ansible/cli/vault.py']['maintainers'],
            ['larry', 'curly', 'moe', 'jeff']
        )
