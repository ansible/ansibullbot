import datetime
import json
import os
import tempfile

from unittest import mock

from ansibullbot.issuewrapper import IssueWrapper


class GithubIssueMock:
    number = 1
    url = 'https://github.com/ansible/ansible/issues/1'
    updated_at = datetime.datetime.now()


class GithubWrapperMock:

    cache = {}

    def get_request(self, url):
        print(url)
        return self._get_request(url)

    def _get_request(self, url):
        return self.cache.get(url, [])


class GithubRepoMock:
    full_name = 'ansible/ansible'


class GithubRepoWrapperMock:
    def __init__(self):
        self.repo = GithubRepoMock()


@mock.patch('ansibullbot.utils.github.C.DEFAULT_RATELIMIT', False)
def test_get_events():
    '''Check basic event fetching and caching'''
    with tempfile.TemporaryDirectory() as cachedir:
        github = GithubWrapperMock()
        repo = GithubRepoWrapperMock()
        issue = GithubIssueMock()

        github.cache['https://github.com/ansible/ansible/issues/1/timeline'] = [
            {'event': 'labeled', 'created_at':  '2020-05-31T10:02:20Z'},
            {'event': 'unlabeled', 'created_at':  '2020-05-31T10:02:20Z'},
            {'event': 'comment', 'created_at':  '2020-05-31T10:02:20Z'}
        ]

        iw = IssueWrapper(
            github=github,
            repo=repo,
            issue=issue,
            cachedir=cachedir,
            gitrepo=repo,
        )

        events = iw.events

        assert len(events) == 3
        assert os.path.exists(os.path.join(cachedir, 'issues', '1', 'timeline_meta.json'))
        assert os.path.exists(os.path.join(cachedir, 'issues', '1', 'timeline_data.json'))


@mock.patch('ansibullbot.utils.github.C.DEFAULT_RATELIMIT', False)
def test_get_events_bad_cache_invalidate():
    '''Prevent bad data from leaking into events'''
    with tempfile.TemporaryDirectory() as cachedir:
        github = GithubWrapperMock()
        repo = GithubRepoWrapperMock()
        issue = GithubIssueMock()

        github.cache['https://github.com/ansible/ansible/issues/1/timeline'] = [
            {'event': 'labeled', 'created_at': '2020-05-31T10:02:20Z'},
            {'event': 'unlabeled', 'created_at': '2020-05-31T10:02:20Z'},
            {'event': 'comment', 'created_at': '2020-05-31T10:02:20Z'}
        ]

        events_meta_cache = os.path.join(cachedir, 'issues', '1', 'timeline_meta.json')
        events_data_cache = os.path.join(cachedir, 'issues', '1', 'timeline_data.json')

        os.makedirs(os.path.dirname(events_meta_cache))


        # set a meta file that matches the timestamp for the issue so the cache is used
        with open(events_meta_cache, 'w') as f:
            f.write(json.dumps({
                'updated_at': '2020-05-31T10:02:20Z',
                'url': 'https://github.com/ansible/ansible/issues/1/timeline',
            }))

        # create a bad event to make sure the cache is invalidated and refetched
        bad_events = github.cache['https://github.com/ansible/ansible/issues/1/timeline'][:]
        bad_events[0] = 'documentation_url'
        with open(events_data_cache, 'w') as f:
            f.write(json.dumps(bad_events))

        iw = IssueWrapper(
            github=github,
            repo=repo,
            issue=issue,
            cachedir=cachedir,
            gitrepo=repo
        )

        events = iw.events

        assert len(events) == 3
