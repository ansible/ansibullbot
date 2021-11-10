from unittest.mock import patch

from ansibullbot.utils.github import get_rate_limit


class RequestsResponseMock:
    url = None
    cache = None
    def __init__(self, url):
        self.url = url
        self.cache = {}
    def json(self):
        result = self.cache.get(self.url, {})
        return result


def SleepMock(duration):
    pass


@patch('ansibullbot.utils.github.C.DEFAULT_GITHUB_USERNAME', 'bob')
@patch('ansibullbot.utils.github.C.DEFAULT_GITHUB_PASSWORD', '12345')
@patch('ansibullbot.utils.github.C.DEFAULT_GITHUB_TOKEN', 'abcde12345')
@patch('ansibullbot.utils.github.C.DEFAULT_GITHUB_URL', None)
@patch('ansibullbot.utils.github.time.sleep', SleepMock)
@patch('ansibullbot.utils.github.requests.get')
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
    assert 'resources' in limit
    assert 'core' in limit['resources']
    assert 'limit' in limit['resources']['core']
    assert 'remaining' in limit['resources']['core']
    assert 'reset' in limit['resources']['core']
    assert limit['resources']['core']['limit'] == 5000
    assert limit['resources']['core']['remaining'] == 5000
