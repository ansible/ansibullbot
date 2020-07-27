#!/usr/bin/env python

import datetime
import json
import six
import unittest
from unittest import TestCase

six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

import github
import pytz

from tests.utils.issue_mock import IssueMock
from tests.utils.repo_mock import RepoMock
from tests.utils.helpers import get_issue
from ansibullbot.triagers.plugins.needs_revision import _changes_requested_by, get_needs_revision_facts, _get_review_state
from ansibullbot.wrappers.issuewrapper import IssueWrapper
from ansibullbot.wrappers.historywrapper import HistoryWrapper

class ComponentMatcherMock(object):

    expected_results = []

    def match(self, issuewrapper):
        return self.expected_results


class ModuleIndexerMock(object):

    def __init__(self, namespace_maintainers):
        self.namespace_maintainers = namespace_maintainers

    def get_maintainers_for_namespace(self, namespace):
        return self.namespace_maintainers


class AnsibleTriageMock(object):

    BOTNAMES = [u'ansibot', u'gregdek', u'robynbergeron']

    @property
    def ansible_core_team(self):
        return [u'bcoca']


class ShippableCIMock(object):
    def __init__(self):
        self.required_file = u'shippable.yml'
        self.state_context = u'Shippable'

    def get_last_full_run_date(*args, **kwargs):
        return None


class TestNeedsRevisionFacts(TestCase):

    def setUp(self):
        self.meta = {
            u'is_new_module': False,
            u'module_match': {
                u'namespace': u'zypper',
                u'maintainers': [u'robinro'],
            }
        }

    #@unittest.skip('disabled')
    def test_shipit_overrides_changes_requested_github_review(self):
        """
        Ansibot should ignore CHANGES_REQUESTED Github review when the author of the
        CHANGES_REQUESTED review used the shipit command.
        """
        datafile = u'tests/fixtures/needs_revision/0_issue.yml'
        statusfile = u'tests/fixtures/needs_revision/0_prstatus.json'
        with mock.patch.multiple(IssueWrapper,
                               mergeable_state=mock.PropertyMock(return_value='clean'),
                               pullrequest_filepath_exists=mock.Mock(return_value=True)):
            with get_issue(datafile, statusfile) as iw:
                iw._merge_commits = []
                iw._committer_emails = [u'tsdmgz@domain.example']

                pullrequest = mock.Mock(spec_set=github.PullRequest.PullRequest)
                pullrequest.head.repo.__return_value__ = True
                iw._pr = pullrequest

                with open(u'tests/fixtures/needs_revision/0_reviews.json') as reviews:
                    iw._pr_reviews = json.load(reviews)
                    iw._history.merge_reviews(iw.reviews)

                self.meta[u'component_maintainers'] = [u'robinro']
                facts = get_needs_revision_facts(AnsibleTriageMock(), iw, self.meta, ShippableCIMock())

                self.assertFalse(facts[u'is_needs_revision'])
                self.assertFalse(facts[u'stale_reviews'])

    def test_shipit_removes_needs_revision(self):
        """
        Ansibot should remove needs_revision if the same user that set it gave shipit afterwards.
        https://github.com/ansible/ansibullbot/issues/994
        """
        datafile = u'tests/fixtures/needs_revision/1_issue.yml'
        statusfile = u'tests/fixtures/needs_revision/0_prstatus.json'
        with mock.patch.multiple(IssueWrapper,
                               mergeable_state=mock.PropertyMock(return_value='clean'),
                               pullrequest_filepath_exists=mock.Mock(return_value=True)):
            with get_issue(datafile, statusfile) as iw:
                iw._merge_commits = []
                iw._committer_emails = [u'tsdmgz@domain.example']

                pullrequest = mock.Mock(spec_set=github.PullRequest.PullRequest)
                pullrequest.head.repo.__return_value__ = True
                iw._pr = pullrequest

                with open(u'tests/fixtures/needs_revision/1_reviews.json') as reviews:
                    iw._pr_reviews = json.load(reviews)
                    iw._history.merge_reviews(iw.reviews)

                self.meta[u'component_maintainers'] = [u'mkrizek']
                facts = get_needs_revision_facts(AnsibleTriageMock(), iw, self.meta, ShippableCIMock())

                self.assertFalse(facts[u'is_needs_revision'])

    def test_shipit_removes_needs_revision_multiple_users(self):
        """
        Ansibot should remove needs_revision if the same user that set it gave shipit afterwards.
        https://github.com/ansible/ansibullbot/issues/994
        """
        datafile = u'tests/fixtures/needs_revision/2_issue.yml'
        statusfile = u'tests/fixtures/needs_revision/0_prstatus.json'
        with mock.patch.multiple(IssueWrapper,
                               mergeable_state=mock.PropertyMock(return_value='clean'),
                               pullrequest_filepath_exists=mock.Mock(return_value=True)):
            with get_issue(datafile, statusfile) as iw:
                iw._merge_commits = []
                iw._committer_emails = [u'tsdmgz@domain.example']

                pullrequest = mock.Mock(spec_set=github.PullRequest.PullRequest)
                pullrequest.head.repo.__return_value__ = True
                iw._pr = pullrequest

                with open(u'tests/fixtures/needs_revision/1_reviews.json') as reviews:
                    iw._pr_reviews = json.load(reviews)
                    iw._history.merge_reviews(iw.reviews)

                self.meta[u'component_maintainers'] = [u'mkrizek', u'jctanner']
                facts = get_needs_revision_facts(AnsibleTriageMock(), iw, self.meta, ShippableCIMock())

                self.assertTrue(facts[u'is_needs_revision'])


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
            {u'user': {u'login': u'reviewer0'}, u'submitted_at': u'2017-01-01T00:00:00Z', u'state': u'COMMENTED'},

            {u'user': {u'login': u'reviewer1'}, u'submitted_at': u'2017-02-01T00:00:00Z', u'state': u'COMMENTED'},
            {u'user': {u'login': u'reviewer1'}, u'submitted_at': u'2017-02-02T00:00:00Z', u'state': u'CHANGES_REQUESTED'},
            {u'user': {u'login': u'reviewer1'}, u'submitted_at': u'2017-02-03T00:00:00Z', u'state': u'COMMENTED'},

            {u'user': {u'login': u'reviewer2'}, u'submitted_at': u'2017-03-01T00:00:00Z', u'state': u'CHANGES_REQUESTED'},
            {u'user': {u'login': u'reviewer2'}, u'submitted_at': u'2017-03-02T00:00:00Z', u'state': u'APPROVED'},
            {u'user': {u'login': u'reviewer2'}, u'submitted_at': u'2017-03-03T00:00:00Z', u'state': u'COMMENTED'},

            {u'user': {u'login': u'reviewer3'}, u'submitted_at': u'2017-04-02T00:00:00Z', u'state': u'APPROVED'},
            {u'user': {u'login': u'reviewer3'}, u'submitted_at': u'2017-04-03T00:00:00Z', u'state': u'CHANGES_REQUESTED'},

            {u'user': {u'login': u'reviewer4'}, u'submitted_at': u'2017-05-01T00:00:00Z', u'state': u'CHANGES_REQUESTED'},
        ]
        for review in reviews:
            review[u'commit_id'] = u'569597fac8175e6c63cbb415080ce42f9992a0c9'
        submitter = u'submitter'

        filtered = _get_review_state(reviews, submitter)

        self.assertEqual(filtered[u'reviewer0'][u'state'], u'COMMENTED')
        self.assertEqual(filtered[u'reviewer1'][u'state'], u'CHANGES_REQUESTED')
        self.assertEqual(filtered[u'reviewer2'][u'state'], u'COMMENTED')
        self.assertEqual(filtered[u'reviewer3'][u'state'], u'CHANGES_REQUESTED')
        self.assertEqual(filtered[u'reviewer4'][u'state'], u'CHANGES_REQUESTED')

        shipits = {
            u'reviewer1': self.make_time(u'2017-02-04T00:00:00Z'),  # newer, overrides CHANGES_REQUESTED review
            u'reviewer3': self.make_time(u'2017-04-01T00:00:00Z'),  # older, doesn't override CHANGES_REQUESTED review
        }

        last_commit = u'dce73fdee311d5e74a7d59fd301320943f69d49f'
        requested_by = _changes_requested_by(filtered, shipits, last_commit, ready_for_review=None)
        self.assertEqual(sorted(requested_by), [u'reviewer3', u'reviewer4'])

    def test_review_older_than_ready_for_review(self):
        """Check that:
        - CHANGES_REQUESTED review older than ready_for_review comment wrote by submitter
        => review is ignored
        """
        reviews = [
            # oldest first
            {u'user': {u'login': u'reviewer0'}, u'submitted_at': u'2017-01-01T00:00:00Z', u'state': u'CHANGES_REQUESTED',
             u'commit_id': u'569597fac8175e6c63cbb415080ce42f9992a0c9'},
        ]
        submitter = u'submitter'

        filtered = _get_review_state(reviews, submitter)

        self.assertEqual(filtered[u'reviewer0'][u'state'], u'CHANGES_REQUESTED')

        shipits = {}
        last_commit = u'dce73fdee311d5e74a7d59fd301320943f69d49f'
        ready_for_review = self.make_time(u'2017-02-02T00:00:00Z')

        requested_by = _changes_requested_by(filtered, shipits, last_commit, ready_for_review)
        self.assertFalse(requested_by)  # CHANGES_REQUESTED review ignored

    def test_ready_for_review_older_than_review(self):
        """Check that:
        - CHANGES_REQUESTED review younger than ready_for_review comment wrote by submitter
        => review isn't ignored
        """
        reviews = [
            # oldest first
            {u'user': {u'login': u'reviewer0'}, u'submitted_at': u'2017-02-02T00:00:00Z', u'state': u'CHANGES_REQUESTED',
             u'commit_id': u'569597fac8175e6c63cbb415080ce42f9992a0c9'},
        ]
        submitter = u'submitter'

        filtered = _get_review_state(reviews, submitter)

        self.assertEqual(filtered[u'reviewer0'][u'state'], u'CHANGES_REQUESTED')

        shipits = {}
        last_commit = u'dce73fdee311d5e74a7d59fd301320943f69d49f'
        ready_for_review = self.make_time(u'2017-01-01T00:00:00Z')

        requested_by = _changes_requested_by(filtered, shipits, last_commit, ready_for_review)
        self.assertEqual(requested_by, [u'reviewer0'])  # HANGES_REQUESTED review isn't ignored

    def test_review_older_than_ready_for_review_PR_not_updated(self):
        """Check that:
        - CHANGES_REQUESTED review older than ready_for_review comment wrote by submitter
        - but submitter didn't update the pull request
        => review isn't ignored
        """
        last_commit = u'dce73fdee311d5e74a7d59fd301320943f69d49f'
        reviews = [
            # oldest first
            {u'user': {u'login': u'reviewer0'}, u'submitted_at': u'2017-01-01T00:00:00Z', u'state': u'CHANGES_REQUESTED',
             u'commit_id': last_commit},
        ]
        submitter = u'submitter'

        filtered = _get_review_state(reviews, submitter)

        self.assertEqual(filtered[u'reviewer0'][u'state'], u'CHANGES_REQUESTED')

        shipits = {}
        ready_for_review = self.make_time(u'2017-02-02T00:00:00Z')

        requested_by = _changes_requested_by(filtered, shipits, last_commit, ready_for_review)
        self.assertEqual(requested_by, [u'reviewer0'])  # HANGES_REQUESTED review isn't ignored

    @staticmethod
    def make_time(data):
        time = datetime.datetime.strptime(data, u'%Y-%m-%dT%H:%M:%SZ')
        return pytz.utc.localize(time)
