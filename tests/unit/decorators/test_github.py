#!/usr/bin/env python

import pytest
import six
six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock

from ansibullbot.decorators.github import get_rate_limit


class RequestsResponseMock:
    url = None
    cache = None
    def __init__(self, url):
        self.url = url
        self.cache = {}
    def json(self):
        result = self.cache.get(self.url, {})
        #print('\n RESULT: %s' % result)
        return result


def SleepMock(duration):
    pass


@mock.patch('ansibullbot.decorators.github.C.DEFAULT_GITHUB_USERNAME', 'bob')
@mock.patch('ansibullbot.decorators.github.C.DEFAULT_GITHUB_PASSWORD', '12345')
@mock.patch('ansibullbot.decorators.github.C.DEFAULT_GITHUB_TOKEN', 'abcde12345')
@mock.patch('ansibullbot.decorators.github.C.DEFAULT_GITHUB_URL', None)
@mock.patch('ansibullbot.decorators.github.time.sleep', SleepMock)
@mock.patch('ansibullbot.decorators.github.requests.get')
def test_get_rate_limit(mock_requests_get):

    '''Basic check of get_rate_limit api'''

    url = 'https://api.github.com/rate_limit'
    rr = RequestsResponseMock(url)
    rr.cache[url] = {
        'resources': {
            'core': {
                'limit': 5000,
                'remaining': 5000,
                'reset': None
            }
        }
    }
    mock_requests_get.return_value = rr

    limit = get_rate_limit()

    assert isinstance(limit, dict)
    assert u'resources' in limit
    assert u'core' in limit[u'resources']
    assert u'limit' in limit[u'resources'][u'core']
    assert u'remaining' in limit[u'resources'][u'core']
    assert u'reset' in limit[u'resources'][u'core']
    assert limit[u'resources'][u'core'][u'limit'] == 5000
    assert limit[u'resources'][u'core'][u'remaining'] == 5000
