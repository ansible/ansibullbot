#!/usr/bin/env python


import pytest
import tempfile

import six
six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
from six.moves import mock
import tempfile

from ansibullbot.errors import RateLimitError
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper


class GithubMock(object):
    def get_rate_limit(self):
        return None


class RequestsResponseMock(object):
    def json(self):
        data = {
            u'documentation_url': u'https://developer.github.com/v3/#rate-limiting',
            u'message': u'API rate limit exceeded for user ID XXXXX.'
        }
        return data


class RequestsMockRateLimited(object):
    def get(self, url, headers=None):
        rr = RequestsResponseMock()
        return rr


@mock.patch('ansibullbot.decorators.github.C.DEFAULT_RATELIMIT', False)
@mock.patch('ansibullbot.decorators.github.C.DEFAULT_BREAKPOINTS', False)
@mock.patch('ansibullbot.wrappers.ghapiwrapper.requests', RequestsMockRateLimited())
def test_get_request_rate_limited():

    cachedir = tempfile.mkdtemp()    

    gh = GithubMock()
    gw = GithubWrapper(gh, token=12345, cachedir=cachedir)

    with pytest.raises(RateLimitError):
        rdata = gw.get_request(u'https://foo.bar.com/test')
