import pytest
import tempfile

from unittest.mock import patch, Mock

from ansibullbot.exceptions import RateLimitError
from ansibullbot.ghapiwrapper import GithubWrapper


response_mock = Mock()
response_mock.json.return_value = {
    'documentation_url': 'https://developer.github.com/v3/#rate-limiting',
    'message': 'API rate limit exceeded for user ID XXXXX.'
}
requests = Mock()
requests.get.side_effect = lambda url, headers: response_mock


@patch('ansibullbot.utils.github.C.DEFAULT_RATELIMIT', False)
@patch('ansibullbot.ghapiwrapper.requests', requests)
def test_get_request_rate_limited():
    GithubWrapper._connect = lambda *args: None
    gw = GithubWrapper(token=12345, cachedir=tempfile.mkdtemp())

    with pytest.raises(RateLimitError):
        gw.get_request('https://foo.bar.com/test')
