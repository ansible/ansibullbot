#!/usr/bin/env python

import datetime
import json
import os
#import tempfile

import six
six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from backports import tempfile

from ansibullbot.wrappers.defaultwrapper import DefaultWrapper


class GithubIssueMock:
    number = 1
    url = u'https://github.com/ansible/ansible/issues/1'
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


class FileIndexerMock:
    pass


@mock.patch('ansibullbot.decorators.github.C.DEFAULT_RATELIMIT', False)
@mock.patch('ansibullbot.decorators.github.C.DEFAULT_BREAKPOINTS', False)
def test_get_events():

    '''Check basic event fetching and caching'''

    with tempfile.TemporaryDirectory() as cachedir:

        github = GithubWrapperMock()
        repo = GithubRepoWrapperMock()
        issue = GithubIssueMock()
        fi = FileIndexerMock()

        github.cache[u'https://github.com/ansible/ansible/issues/1/events'] = [
            {'event': 'labeled', 'created_at': datetime.datetime.now().isoformat()},
            {'event': 'unlabeled', 'created_at': datetime.datetime.now().isoformat()},
            {'event': 'comment', 'created_at': datetime.datetime.now().isoformat()}
        ]

        github.cache[u'https://github.com/ansible/ansible/issues/1/timeline'] = []

        dw = DefaultWrapper(
            github=github,
            repo=repo,
            issue=issue,
            cachedir=cachedir,
            file_indexer=fi
        )

        events = dw.get_events()

        assert len(events) == 3
        assert os.path.exists(os.path.join(cachedir, 'issues', '1', 'events_meta.json'))
        assert os.path.exists(os.path.join(cachedir, 'issues', '1', 'events_data.json'))
        assert os.path.exists(os.path.join(cachedir, 'issues', '1', 'timeline_meta.json'))
        assert os.path.exists(os.path.join(cachedir, 'issues', '1', 'timeline_data.json'))


@mock.patch('ansibullbot.decorators.github.C.DEFAULT_RATELIMIT', False)
@mock.patch('ansibullbot.decorators.github.C.DEFAULT_BREAKPOINTS', False)
def test_get_events_bad_cache_invalidate():

    '''Prevent bad data from leaking into events'''

    with tempfile.TemporaryDirectory() as cachedir:

        github = GithubWrapperMock()
        repo = GithubRepoWrapperMock()
        issue = GithubIssueMock()
        fi = FileIndexerMock()

        github.cache[u'https://github.com/ansible/ansible/issues/1/events'] = [
            {'event': 'labeled', 'created_at': datetime.datetime.now().isoformat()},
            {'event': 'unlabeled', 'created_at': datetime.datetime.now().isoformat()},
            {'event': 'comment', 'created_at': datetime.datetime.now().isoformat()}
        ]

        github.cache[u'https://github.com/ansible/ansible/issues/1/timeline'] = []

        events_meta_cache = os.path.join(cachedir, 'issues', '1', 'events_meta.json')
        events_data_cache = os.path.join(cachedir, 'issues', '1', 'events_data.json')

        os.makedirs(os.path.dirname(events_meta_cache))


        # set a meta file that matches the timestamp for the issue so the cache is used
        with open(events_meta_cache, 'w') as f:
            f.write(json.dumps({
                u'updated_at': issue.updated_at.isoformat(),
                u'url': u'https://github.com/ansible/ansible/issues/1/events'
            }))

        # create a bad event to make sure the cache is invalidated and refetched
        bad_events = github.cache[u'https://github.com/ansible/ansible/issues/1/events'][:]
        bad_events[0] = u'documentation_url'
        with open(events_data_cache, 'w') as f:
            f.write(json.dumps(bad_events))

        dw = DefaultWrapper(
            github=github,
            repo=repo,
            issue=issue,
            cachedir=cachedir,
            file_indexer=fi
        )

        events = dw.get_events()

        assert len(events) == 3
