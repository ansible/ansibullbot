import pytest
import tempfile

from unittest import mock

from ansibullbot.errors import RateLimitError
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper


class GithubMock:
    def get_rate_limit(self):
        return None


class RequestsResponseMock:
    def json(self):
        data = {
            'documentation_url': 'https://developer.github.com/v3/#rate-limiting',
            'message': 'API rate limit exceeded for user ID XXXXX.'
        }
        return data


class RequestsMockRateLimited:
    def get(self, url, headers=None):
        rr = RequestsResponseMock()
        return rr


@mock.patch('ansibullbot.decorators.github.C.DEFAULT_RATELIMIT', False)
@mock.patch('ansibullbot.wrappers.ghapiwrapper.requests', RequestsMockRateLimited())
def test_get_request_rate_limited():

    cachedir = tempfile.mkdtemp()

    gh = GithubMock()
    gw = GithubWrapper(gh, token=12345, cachedir=cachedir)

    with pytest.raises(RateLimitError):
        rdata = gw.get_request('https://foo.bar.com/test')
