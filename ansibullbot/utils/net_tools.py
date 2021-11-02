import logging
import time

import requests


# FIXME should we only retry 5xx?
_DONT_RETRY_STATUSES = [
    200,  # OK
    204,  # No Content
    302,  # Found (Moved temporarily)
    400,  # Bad request
    404,  # Not Found
    409,  # Conflict
]


def fetch(url, verb='get', **kwargs):
    """return response or None in case of failure, try twice"""
    for i in range(2):
        logging.info('%s %s' % (verb, url))
        http_method = getattr(requests, verb)
        resp = http_method(url, **kwargs)
        logging.info('status code: %s' % resp.status_code)
        logging.info('reason: %s' % resp.reason)

        if resp.status_code not in _DONT_RETRY_STATUSES:
            logging.error('status code: %s' % resp.status_code)
            time.sleep(2)
            continue

        return resp
