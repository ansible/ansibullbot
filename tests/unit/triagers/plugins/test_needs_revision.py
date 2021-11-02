import datetime
import json
from unittest import TestCase, mock

import github

from tests.utils.helpers import get_issue
from ansibullbot.triagers.plugins.needs_revision import _changes_requested_by, get_needs_revision_facts, _get_review_state
from ansibullbot.wrappers.issuewrapper import IssueWrapper

class ComponentMatcherMock:

    expected_results = []

    def match(self, issuewrapper):
        return self.expected_results


class ModuleIndexerMock:

    def __init__(self, namespace_maintainers):
        self.namespace_maintainers = namespace_maintainers

    def get_maintainers_for_namespace(self, namespace):
        return self.namespace_maintainers


class CIMock:
    def __init__(self):
        self.state = None

    def get_last_full_run_date(*args, **kwargs):
        return None


class TestNeedsRevisionFacts(TestCase):

    def setUp(self):
        self.meta = {
            'is_new_module': False,
            'module_match': {
                'namespace': 'zypper',
                'maintainers': ['robinro'],
            }
        }

    #@unittest.skip('disabled')
    def test_shipit_overrides_changes_requested_github_review(self):
        """
        Ansibot should ignore CHANGES_REQUESTED Github review when the author of the
        CHANGES_REQUESTED review used the shipit command.
        """
        datafile = 'tests/fixtures/needs_revision/0_issue.yml'
        statusfile = 'tests/fixtures/needs_revision/0_prstatus.json'
        with mock.patch.multiple(IssueWrapper,
                                mergeable_state=mock.PropertyMock(return_value='clean')):
            with get_issue(datafile, statusfile) as iw:
                iw._merge_commits = []
                iw._committer_emails = ['tsdmgz@domain.example']

                pullrequest = mock.Mock(spec_set=github.PullRequest.PullRequest)
                pullrequest.head.repo.__return_value__ = True
                iw._pr = pullrequest

                with open('tests/fixtures/needs_revision/0_reviews.json') as reviews:
                    iw._pr_reviews = json.load(reviews)
                    iw._history.merge_reviews(iw.reviews)

                self.meta['component_maintainers'] = ['robinro']
                facts = get_needs_revision_facts(iw, self.meta, CIMock(), ['bcoca'], ['ansibot'])

                self.assertFalse(facts['is_needs_revision'])
                self.assertFalse(facts['stale_reviews'])

    def test_shipit_removes_needs_revision(self):
        """
        Ansibot should remove needs_revision if the same user that set it gave shipit afterwards.
        https://github.com/ansible/ansibullbot/issues/994
        """
        datafile = 'tests/fixtures/needs_revision/1_issue.yml'
        statusfile = 'tests/fixtures/needs_revision/0_prstatus.json'
        with mock.patch.multiple(IssueWrapper,
                                mergeable_state=mock.PropertyMock(return_value='clean')):
            with get_issue(datafile, statusfile) as iw:
                iw._merge_commits = []
                iw._committer_emails = ['tsdmgz@domain.example']

                pullrequest = mock.Mock(spec_set=github.PullRequest.PullRequest)
                pullrequest.head.repo.__return_value__ = True
                iw._pr = pullrequest

                with open('tests/fixtures/needs_revision/1_reviews.json') as reviews:
                    iw._pr_reviews = json.load(reviews)
                    iw._history.merge_reviews(iw.reviews)

                self.meta['component_maintainers'] = ['mkrizek']
                facts = get_needs_revision_facts(iw, self.meta, CIMock(), ['bcoca'], ['ansibot'])

                self.assertFalse(facts['is_needs_revision'])

    def test_shipit_removes_needs_revision_multiple_users(self):
        """
        Ansibot should remove needs_revision if the same user that set it gave shipit afterwards.
        https://github.com/ansible/ansibullbot/issues/994
        """
        datafile = 'tests/fixtures/needs_revision/2_issue.yml'
        statusfile = 'tests/fixtures/needs_revision/0_prstatus.json'
        with mock.patch.multiple(IssueWrapper,
                                mergeable_state=mock.PropertyMock(return_value='clean')):
            with get_issue(datafile, statusfile) as iw:
                iw._merge_commits = []
                iw._committer_emails = ['tsdmgz@domain.example']

                pullrequest = mock.Mock(spec_set=github.PullRequest.PullRequest)
                pullrequest.head.repo.__return_value__ = True
                iw._pr = pullrequest

                with open('tests/fixtures/needs_revision/1_reviews.json') as reviews:
                    iw._pr_reviews = json.load(reviews)
                    iw._history.merge_reviews(iw.reviews)

                self.meta['component_maintainers'] = ['mkrizek', 'jctanner']
                facts = get_needs_revision_facts(iw, self.meta, CIMock(), ['bcoca'], ['ansibot'])

                self.assertTrue(facts['is_needs_revision'])


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
        for review in reviews:
            review['commit_id'] = '569597fac8175e6c63cbb415080ce42f9992a0c9'
        submitter = 'submitter'

        filtered = _get_review_state(reviews, submitter)

        self.assertEqual(filtered['reviewer0']['state'], 'COMMENTED')
        self.assertEqual(filtered['reviewer1']['state'], 'CHANGES_REQUESTED')
        self.assertEqual(filtered['reviewer2']['state'], 'COMMENTED')
        self.assertEqual(filtered['reviewer3']['state'], 'CHANGES_REQUESTED')
        self.assertEqual(filtered['reviewer4']['state'], 'CHANGES_REQUESTED')

        shipits = {
            'reviewer1': self.make_time('2017-02-04T00:00:00Z'),  # newer, overrides CHANGES_REQUESTED review
            'reviewer3': self.make_time('2017-04-01T00:00:00Z'),  # older, doesn't override CHANGES_REQUESTED review
        }

        last_commit = 'dce73fdee311d5e74a7d59fd301320943f69d49f'
        requested_by = _changes_requested_by(filtered, shipits, last_commit, ready_for_review=None)
        self.assertEqual(sorted(requested_by), ['reviewer3', 'reviewer4'])

    def test_review_older_than_ready_for_review(self):
        """Check that:
        - CHANGES_REQUESTED review older than ready_for_review comment wrote by submitter
        => review is ignored
        """
        reviews = [
            # oldest first
            {'user': {'login': 'reviewer0'}, 'submitted_at': '2017-01-01T00:00:00Z', 'state': 'CHANGES_REQUESTED',
             'commit_id': '569597fac8175e6c63cbb415080ce42f9992a0c9'},
        ]
        submitter = 'submitter'

        filtered = _get_review_state(reviews, submitter)

        self.assertEqual(filtered['reviewer0']['state'], 'CHANGES_REQUESTED')

        shipits = {}
        last_commit = 'dce73fdee311d5e74a7d59fd301320943f69d49f'
        ready_for_review = self.make_time('2017-02-02T00:00:00Z')

        requested_by = _changes_requested_by(filtered, shipits, last_commit, ready_for_review)
        self.assertFalse(requested_by)  # CHANGES_REQUESTED review ignored

    def test_ready_for_review_older_than_review(self):
        """Check that:
        - CHANGES_REQUESTED review younger than ready_for_review comment wrote by submitter
        => review isn't ignored
        """
        reviews = [
            # oldest first
            {'user': {'login': 'reviewer0'}, 'submitted_at': '2017-02-02T00:00:00Z', 'state': 'CHANGES_REQUESTED',
             'commit_id': '569597fac8175e6c63cbb415080ce42f9992a0c9'},
        ]
        submitter = 'submitter'

        filtered = _get_review_state(reviews, submitter)

        self.assertEqual(filtered['reviewer0']['state'], 'CHANGES_REQUESTED')

        shipits = {}
        last_commit = 'dce73fdee311d5e74a7d59fd301320943f69d49f'
        ready_for_review = self.make_time('2017-01-01T00:00:00Z')

        requested_by = _changes_requested_by(filtered, shipits, last_commit, ready_for_review)
        self.assertEqual(requested_by, ['reviewer0'])  # HANGES_REQUESTED review isn't ignored

    def test_review_older_than_ready_for_review_PR_not_updated(self):
        """Check that:
        - CHANGES_REQUESTED review older than ready_for_review comment wrote by submitter
        - but submitter didn't update the pull request
        => review isn't ignored
        """
        last_commit = 'dce73fdee311d5e74a7d59fd301320943f69d49f'
        reviews = [
            # oldest first
            {'user': {'login': 'reviewer0'}, 'submitted_at': '2017-01-01T00:00:00Z', 'state': 'CHANGES_REQUESTED',
             'commit_id': last_commit},
        ]
        submitter = 'submitter'

        filtered = _get_review_state(reviews, submitter)

        self.assertEqual(filtered['reviewer0']['state'], 'CHANGES_REQUESTED')

        shipits = {}
        ready_for_review = self.make_time('2017-02-02T00:00:00Z')

        requested_by = _changes_requested_by(filtered, shipits, last_commit, ready_for_review)
        self.assertEqual(requested_by, ['reviewer0'])  # HANGES_REQUESTED review isn't ignored

    @staticmethod
    def make_time(data):
        return datetime.datetime.strptime(data, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)
