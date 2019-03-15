#!/usr/bin/env python

import copy
import shutil
import tempfile
import textwrap
import unittest

import six
six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from tests.utils.issue_mock import IssueMock
from tests.utils.helpers import get_issue
from tests.utils.module_indexer_mock import create_indexer
from ansibullbot.triagers.plugins.component_matching import get_component_match_facts
from ansibullbot.triagers.plugins.shipit import get_automerge_facts
from ansibullbot.wrappers.issuewrapper import IssueWrapper


class ComponentMatcherMock(object):

    strategies = []
    expected_results = []

    def match(self, issuewrapper):
        return self.expected_results


class HistoryWrapperMock(object):
    history = None
    def __init__(self):
        self.history = []


class IssueWrapperMock(object):
    _is_pullrequest = False
    _pr_files = []
    _wip = False
    _history = None
    _submitter = 'bob'

    def __init__(self, org, repo, number):
        self._history = HistoryWrapperMock()
        self.org = org
        self.repo = repo
        self.number = number

    def is_pullrequest(self):
        return self._is_pullrequest

    def add_comment(self, user, body):
        payload = {'actor': user, 'event': 'commented', 'body': body}
        self.history.history.append(payload)

    def add_file(self, filename, content):
        mf = MockFile(filename, content=content)
        self._pr_files.append(mf)

    @property
    def wip(self):
        return self._wip

    @property
    def files(self):
        return [x.filename for x in self._pr_files]

    @property
    def history(self):
        return self._history

    @property
    def submitter(self):
        return self._submitter

    @property
    def html_url(self):
        if self.is_pullrequest():
            return 'https://github.com/%s/%s/pulls/%s' % (self.org, self.repo, self.number)
        else:
            return 'https://github.com/%s/%s/issues/%s' % (self.org, self.repo, self.number)


class ModuleIndexerMock(object):

    def __init__(self, namespace_maintainers):
        self.namespace_maintainers = namespace_maintainers

    def get_maintainers_for_namespace(self, namespace):
        return self.namespace_maintainers


class FileIndexerMock(object):

    files = []

    def find_component_matches_by_file(self, filenames):
        return []

    def isnewdir(self, path):
        return False

    def get_component_labels(self, files, valid_labels=None):
        return []


class MockFile(object):
    def __init__(self, name, content=u''):
        self.filename = name
        self.content = content


class MockRepo(object):
    def __init__(self, repo_path):
        self.repo_path = repo_path


class TestAutomergeFacts(unittest.TestCase):

    def test_automerge_if_shipit(self):
        # if shipit and other tests pass, automerge should be True
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW._is_pullrequest = True
        IW.add_comment('jane', 'shipit')
        MI = ModuleIndexerMock([])
        meta = {
            u'ci_stale': False,
            u'ci_state': u'success',
            u'has_shippable': True,
            u'has_travis': False,
            u'is_new_directory': False,
            u'is_module': True,
            u'is_module_util': False,
            u'is_new_module': False,
            u'is_needs_info': False,
            u'is_needs_rebase': False,
            u'is_needs_revision': False,
            u'is_backport': False,
            u'mergeable': True,
            u'merge_commits': False,
            u'has_commit_mention': False,
            u'shipit': True,
            u'supershipit': True,
            u'component_matches': [
                {
                    u'repo_filename': u'foo',
                    u'supershipit': [u'jane', u'doe'],
                }
            ],
            u'component_support': [u'community']
        }
        meta[u'module_match'] = meta[u'component_matches'][:]
        amfacts = get_automerge_facts(IW, meta)
        assert amfacts[u'automerge']
        assert u'automerge_status' in amfacts

    def test_not_automerge_if_not_shipit(self):
        # if not shipit, automerge should be False
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW._is_pullrequest = True
        IW.add_comment('jane', 'shipit')
        MI = ModuleIndexerMock([])
        meta = {
            u'ci_stale': False,
            u'ci_state': u'success',
            u'has_shippable': True,
            u'has_travis': False,
            u'is_new_directory': False,
            u'is_module': True,
            u'is_module_util': False,
            u'is_new_module': False,
            u'is_needs_info': False,
            u'is_needs_rebase': False,
            u'is_needs_revision': False,
            u'is_backport': False,
            u'mergeable': True,
            u'merge_commits': False,
            u'has_commit_mention': False,
            u'shipit': False,
            u'supershipit': False,
            u'component_matches': [
                {
                    u'repo_filename': u'foo',
                    u'supershipit': [u'jane', u'doe'],
                }
            ],
            u'component_support': [u'community']
        }
        meta[u'module_match'] = meta[u'component_matches'][:]
        amfacts = get_automerge_facts(IW, meta)
        assert not amfacts[u'automerge']
        assert u'automerge_status' in amfacts
