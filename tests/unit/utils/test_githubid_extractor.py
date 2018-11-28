#!/usr/bin/env python

import unittest
from ansibullbot.utils.moduletools import ModuleIndexer


class ModuleIndexerMock(object):
    def __init__(self, *args, **kwargs):
        self.emails_cache = {}


class TestGitHubIdExtractor(unittest.TestCase):

    def setUp(self):
        self.indexer = ModuleIndexerMock()
        self.extract = ModuleIndexer.extract_github_id.__get__(self.indexer, ModuleIndexer)

    def test_extract(self):
        authors = [
            (None, []),  # Testing for None, which should return an empty list,
            (u'#- "Hai Cao <t-haicao@microsoft.com>"', []),  # Commented out author line should return an empty list
            (u'First-Name Last (@k0-mIg)', [u'k0-mIg']),  # expected format
            (u'Ansible Core Team', [u'ansible']),  # special case
            (u'Ansible core Team', [u'ansible']),  # special case
            (u'First Last (@firstlast) 2016, Another Last (@another) 2014', [u'firstlast', u'another']),  # multiple ids
            (u'First Last @ Corp Team (@first-corp, @corp-team, @user)',[u'first-corp', u'corp-team', u'user']),  # multiple ids
            (u'First Last @github', [u'github']),  # without parentheses
            (u'First Last (github)', [u'github']),  # without at sign
            (u'First Last (github.com/Github)', [u'Github']),  # prefixed
        ]

        for line, githubids in authors:
            self.assertEqual(set(githubids), set(self.extract(line)))

    def test_notfound(self):
        authors = [
            u'firstname lastname',
            u'First Last (name@domain.example)',
        ]

        for line in authors:
            self.assertFalse(self.extract(line))

    def test_extract_email(self):
        self.indexer.emails_cache = {
            u'first@last.example': u'github',
            u'last@domain.example': u'github2',
        }

        authors = [
            (u'First-Name Last (first@last.example)', [u'github']),  # known email
            (u'First-Name Last <first@last.example>', [u'github']),  # known email
            (u'First-Name Last (first@last.example), Surname Name (last@domain.example)', [u'github', u'github2']),  # known emails
            (u'First-Name Last <first@last.example>, Surname Name <last@domain.example>', [u'github', u'github2'])
        ]

        for line, githubids in authors:
            self.assertEqual(set(githubids), set(self.extract(line)))
