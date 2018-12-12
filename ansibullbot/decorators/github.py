#!/usr/bin/env python

# https://github.com/octokit/octokit.net/issues/638#issuecomment-67795998

# FIXME
#   - [Errno -5] No address associated with hostname

import logging
import requests
import socket
import ssl
import sys
import time
import traceback

import six
from six.moves import http_client as httplib

from ansibullbot._text_compat import to_text
from ansibullbot.errors import RateLimitError

import ansibullbot.constants as C


def get_rate_limit():
    url = C.DEFAULT_GITHUB_URL
    if not url:
        url = 'https://api.github.com/rate_limit'
    else:
        url += '/rate_limit'
    username = C.DEFAULT_GITHUB_USERNAME
    password = C.DEFAULT_GITHUB_PASSWORD
    token = C.DEFAULT_GITHUB_TOKEN

    if token:
        success = False
        while not success:
            logging.debug(url)
            try:
                rr = requests.get(
                    url,
                    headers={'Authorization': 'token %s' % token}
                )
                response = rr.json()
                success = True
            except Exception:
                time.sleep(60)

    else:
        success = False
        while not success:
            logging.debug(url)
            try:
                rr = requests.get(
                    url,
                    auth=(username, password)
                )
                response = rr.json()
                success = True
            except Exception:
                time.sleep(60)

    response = rr.json()

    if 'resources' not in response or 'core' not in response.get('resources', {}):
        logging.warning('Unable to fetch rate limit %r', response.get('message'))
        return False

    return response


def get_reset_time(fn, args):
    '''Return the number of seconds until the rate limit resets'''

    # default to 62 minutes
    reset_time = 60 * 62

    rl = get_rate_limit()

    if rl:
        # The time at which the current rate limit window resets
        # in UTC epoch seconds. [ex. 1483405983]
        logging.debug('rate_limit: %s' % to_text(six))
        reset_time = rl['resources']['core']['reset'] - time.time()
        reset_time = int(reset_time)
        if reset_time < 1:
            reset_time = 0

        # always pad by 5s
        reset_time += 5

    logging.debug('get_reset_time [return]: %s(s)' % reset_time)
    return reset_time


def RateLimited(fn):

    def inner(*args, **kwargs):

        success = False
        count = 0
        while not success:
            count += 1
            rl = get_rate_limit()

            if rl:
                func_name = fn.__name__ if six.PY3 else fn.func_name
                logging.debug('ratelimited call #%s [%s] [%s] [%s]' %
                              (count,
                               type(args[0]),
                               func_name,
                               rl['resources']['core']['remaining']))

            if count > 10:
                logging.error('HIT 10 loop iteration on call, giving up')
                sys.exit(1)

            # default to 5 minute sleep
            stime = 5*60
            try:
                x = fn(*args, **kwargs)
                success = True
            except RateLimitError:
                stime = get_reset_time(fn, args)
            except socket.error as e:
                logging.warning('socket error: sleeping 2 minutes %s' % e)
                time.sleep(2*60)
            except ssl.SSLError as e:
                logging.warning('ssl error: sleeping 2 minutes %s' % e)
                time.sleep(2*60)
            except AttributeError as e:
                if "object has no attribute 'decoded_content'" in e.message:
                    stime = get_reset_time(fn, args)
                    msg = 'decoded_content error: sleeping %s minutes %s' \
                        % (stime / 60, e)
                    logging.warning(msg)
                    time.sleep(stime)
                else:
                    if C.DEFAULT_BREAKPOINTS:
                        logging.error('breakpoint!')
                        import epdb; epdb.st()
                    else:
                        raise Exception('unhandled message type')
            except Exception as e:
                logging.error(e)
                if hasattr(e, 'data') and e.data is not None and e.data.get('message'):
                    msg = e.data.get('message')
                    if 'blocked from content creation' in msg:
                        logging.warning('content creation rate limit exceeded')
                        stime = 2*60
                    elif 'Label does not exist' in msg:
                        return None
                    elif 'rate limit exceeded' in msg:
                        logging.warning('general rate limit exceeded')
                        stime = get_reset_time(fn, args)
                    elif isinstance(e, socket.error):
                        logging.warning('socket error')
                        stime = 5*60
                    elif 'Server Error' in msg:
                        logging.warning('server error')
                        stime = 2*60
                    elif 'Not Found' in msg:
                        logging.info('object not found')
                        #stime = 0
                        #success = True
                        return None
                    elif "object has no attribute 'decoded_content'" in msg:
                        # occurs most often when fetching file contents from
                        # the api such as the issue template
                        stime = get_reset_time(fn, args)
                    elif 'No handler found for uri' in msg:
                        # Not sure what is happening here ...
                        # No handler found for uri
                        # [/repos/ansible/ansible/issues/14171] and method [GET]
                        stime = 2*60
                    elif msg.lower() == 'issues are disabled for this repo':
                        return None
                    else:
                        if C.DEFAULT_BREAKPOINTS:
                            logging.error('breakpoint!')
                            import epdb; epdb.st()
                        else:
                            raise Exception('unhandled message type')
                elif isinstance(e, httplib.IncompleteRead):
                    # https://github.com/ansible/ansibullbot/issues/593
                    stime = 2*60
                elif isinstance(e, httplib.BadStatusLine):
                    # https://github.com/ansible/ansibullbot/issues/602
                    stime = 2*60
                elif getattr(e, 'status', None) == 500:
                    # https://github.com/ansible/ansibullbot/issues/1025
                    stime = 2*60
                elif getattr(e, 'status', None) == 502:
                    # https://sentry.io/red-hat-ansibullbot/ansibullbot/issues/804854465
                    stime = 2*60
                else:
                    if C.DEFAULT_BREAKPOINTS:
                        logging.error('breakpoint!')
                        import epdb; epdb.st()
                    else:
                        ex_type, ex, tb = sys.exc_info()
                        traceback.print_tb(tb)
                        raise

                logging.warning('sleeping %s minutes' % (stime/60))
                time.sleep(stime)

        return x

    return inner
