#!/usr/bin/env python

import unittest
from ansibullbot.utils.moduletools import ModuleIndexer


class ModuleIndexerMock(object):
    def __init__(self, *args, **kwargs):
        self.emailmap = {}


class TestGitHubIdExtractor(unittest.TestCase):

    def setUp(self):
        self.indexer = ModuleIndexerMock()
        self.extract = ModuleIndexer.extract_github_id.__get__(self.indexer, ModuleIndexer)

    def test_extract(self):
        authors = [
            ('First-Name Last (@k0-mIg)', ['k0-mIg']),  # expected format
            ('Ansible Core Team', ['ansible']),  # special case
            ('Ansible core Team', ['ansible']),  # special case
            ('First Last (@firstlast) 2016, Another Last (@another) 2014', ['firstlast', 'another']),  # multiple ids
            ('First Last @ Corp Team (@first-corp, @corp-team, @user)',['first-corp', 'corp-team', 'user']),  # multiple ids
            ('First Last @github', ['github']),  # without parentheses
            ('First Last (github)', ['github']),  # without at sign
            ('First Last (github.com/Github)', ['Github']),  # prefixed
        ]

        for line, githubids in authors:
            self.assertEqual(set(githubids), set(self.extract(line)))

    def test_notfound(self):
        authors = [
            'firstname lastname',
            'First Last (name@domain.example)',
        ]

        for line in authors:
            self.assertFalse(self.extract(line))

    def test_extract_email(self):
        self.indexer.emailmap = {
            'first@last.example': 'github',
            'last@domain.example': 'github2',
        }

        authors = [
            ('First-Name Last (first@last.example)', ['github']),  # known email
            ('First-Name Last <first@last.example>', ['github']),  # known email
            ('First-Name Last (first@last.example), Surname Name (last@domain.example)', ['github', 'github2']),  # known emails
        ]

        for line, githubids in authors:
            self.assertEqual(set(githubids), set(self.extract(line)))
