#!/usr/bin/env python

import datetime
import json
import six
from unittest import TestCase

six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

import github
import pytz

from tests.utils.issue_mock import IssueMock
from tests.utils.repo_mock import RepoMock
from tests.utils.helpers import get_issue
from ansibullbot.triagers.plugins.needs_revision import changes_requested_by, get_needs_revision_facts, get_review_state
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


class TestReviewMethods(TestCase):
    def test_reviews(self):
        """Check that:
        - COMMENTED review aren't ignored (reviewer0)
        - a COMMENTED review doesn't override an older CHANGES_REQUESTED review (reviewer1)
        - a COMMENTED review overrides an older APPROVED review (reviewer2)
        - a CHANGES_REQUESTED review overrides an older APPROVED review (reviewer3)
        """
        reviews = [
            # oldest first
            {'user': {'login': 'reviewer0'}, 'submitted_at': '2017-01-01T00:00:00Z', 'state': 'COMMENTED'},

            {'user': {'login': 'reviewer1'}, 'submitted_at': '2017-02-01T00:00:00Z', 'state': 'COMMENTED'},
            {'user': {'login': 'reviewer1'}, 'submitted_at': '2017-02-02T00:00:00Z', 'state': 'CHANGES_REQUESTED'},
            {'user': {'login': 'reviewer1'}, 'submitted_at': '2017-02-03T00:00:00Z', 'state': 'COMMENTED'},

            {'user': {'login': 'reviewer2'}, 'submitted_at': '2017-03-01T00:00:00Z', 'state': 'CHANGES_REQUESTED'},
            {'user': {'login': 'reviewer2'}, 'submitted_at': '2017-03-02T00:00:00Z', 'state': 'APPROVED'},
            {'user': {'login': 'reviewer2'}, 'submitted_at': '2017-03-03T00:00:00Z', 'state': 'COMMENTED'},

            {'user': {'login': 'reviewer3'}, 'submitted_at': '2017-04-02T00:00:00Z', 'state': 'APPROVED'},
            {'user': {'login': 'reviewer3'}, 'submitted_at': '2017-04-03T00:00:00Z', 'state': 'CHANGES_REQUESTED'},

            {'user': {'login': 'reviewer4'}, 'submitted_at': '2017-05-01T00:00:00Z', 'state': 'CHANGES_REQUESTED'},
        ]
        submitter = 'submitter'

        filtered = get_review_state(reviews, submitter)

        self.assertEqual(filtered['reviewer0']['state'], 'COMMENTED')
        self.assertEqual(filtered['reviewer1']['state'], 'CHANGES_REQUESTED')
        self.assertEqual(filtered['reviewer2']['state'], 'COMMENTED')
        self.assertEqual(filtered['reviewer3']['state'], 'CHANGES_REQUESTED')
        self.assertEqual(filtered['reviewer4']['state'], 'CHANGES_REQUESTED')

        shipits = {
            'reviewer1': self.make_time('2017-02-04T00:00:00Z'),  # newer, overrides CHANGES_REQUESTED review
            'reviewer3': self.make_time('2017-04-01T00:00:00Z'),  # older, doesn't override CHANGES_REQUESTED review
        }
        requested_by = changes_requested_by(filtered, shipits)
        self.assertEqual(sorted(requested_by), ['reviewer3', 'reviewer4'])

    @staticmethod
    def make_time(data):
        time = datetime.datetime.strptime(data, '%Y-%m-%dT%H:%M:%SZ')
        return pytz.utc.localize(time)
