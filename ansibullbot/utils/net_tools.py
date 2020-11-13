import logging

import requests
from tenacity import retry, stop_after_attempt, wait_fixed, RetryError, TryAgain


def fetch(url, verb='get', **kwargs):
    """return response or None in case of failure, try twice"""
    @retry(stop=stop_after_attempt(2), wait=wait_fixed(2))
    def _inner_fetch(verb='get'):
        logging.info(u'%s %s' % (verb, url))
        http_method = getattr(requests, verb)
        resp = http_method(url, **kwargs)
        logging.info(u'status code: %s' % resp.status_code)
        logging.info(u'reason: %s' % resp.reason)

        if resp.status_code not in [200, 302, 400]:
            logging.error(u'status code: %s' % resp.status_code)
            raise TryAgain

        return resp

    try:
        logging.debug(u'%s' % url)
        return _inner_fetch(verb=verb)
    except RetryError as e:
        logging.error(e)


def check_response(response):
    if response and response.status_code == 404:
        raise Exception(u'%s 404' % response.url)
