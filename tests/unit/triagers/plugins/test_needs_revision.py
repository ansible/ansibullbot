#!/usr/bin/env python

import json
import six
from unittest import TestCase

six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock
import github

from tests.utils.issue_mock import IssueMock
from tests.utils.repo_mock import RepoMock
from tests.utils.helpers import get_issue
from ansibullbot.triagers.plugins.needs_revision import get_needs_revision_facts
from ansibullbot.wrappers.issuewrapper import IssueWrapper
from ansibullbot.wrappers.historywrapper import HistoryWrapper


class ModuleIndexerMock(object):

    def __init__(self, namespace_maintainers):
        self.namespace_maintainers = namespace_maintainers

    def get_maintainers_for_namespace(self, namespace):
        return self.namespace_maintainers


class AnsibleTriageMock(object):

    BOTNAMES = ['ansibot', 'gregdek', 'robynbergeron']

    @property
    def ansible_core_team(self):
        return ['bcoca']

class TestNeedsRevisionFacts(TestCase):

    def setUp(self):
        self.meta = {
            'is_new_module': False,
            'module_match': {
                'namespace': 'zypper',
                'maintainers': ['robinro'],
            }
        }

    def test_shipit_overrides_changes_requested_github_review(self):
        """
        Ansibot should ignore CHANGES_REQUESTED Github review when the author of the
        CHANGES_REQUESTED review used the shipit command.
        """
        datafile = 'tests/fixtures/needs_revision/0_issue.yml'
        statusfile = 'tests/fixtures/needs_revision/0_prstatus.json'
        with mock.patch.multiple(IssueWrapper,
                               mergeable_state=mock.PropertyMock(return_value='clean'),
                               pullrequest_filepath_exists=mock.Mock(return_value=True)):
            with get_issue(datafile, statusfile) as iw:
                iw._merge_commits = []
                iw._committer_emails = ['tsdmgz@domain.example']

                pullrequest = mock.Mock(spec_set=github.PullRequest.PullRequest)
                pullrequest.head.repo.__return_value__ = True
                iw._pr = pullrequest

                with open('tests/fixtures/needs_revision/0_reviews.json') as reviews:
                    iw._pr_reviews = json.load(reviews)
                    iw._history.merge_reviews(iw.reviews)

                facts = get_needs_revision_facts(AnsibleTriageMock(), iw, self.meta)

                self.assertFalse(facts['is_needs_revision'])
                self.assertFalse(facts['stale_reviews'])
