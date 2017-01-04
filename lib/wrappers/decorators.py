#!/usr/bin/env python

# https://github.com/octokit/octokit.net/issues/638#issuecomment-67795998

# FIXME
#   - [Errno -5] No address associated with hostname

import time
import logging
import os
import requests
import socket
import sys

from github.RateLimit import RateLimit


def get_rate_limit(fn, args):
    username = os.environ.get('GITHUB_USERNAME')
    password = os.environ.get('GITHUB_PASSWORD')
    token = os.environ.get('GITHUB_TOKEN')

    if token:
        logging.error('token auth not yet implemented here!')
        sys.exit(1)
    else:
        rr = requests.get(
            'https://api.github.com/rate_limit',
            auth=(username, password)
        )
    return rr.json()


def get_rate_limit_old(fn, args):
    '''Return the number of seconds until the rate limit resets'''

    # These are circular imports so they need to be deferred
    try:
        from lib.triagers.triagev3 import TriageV3
        from lib.wrappers.ghapiwrapper import GithubWrapper
        from lib.wrappers.ghapiwrapper import RepoWrapper
        from lib.wrappers.historywrapper import HistoryWrapper
        from lib.wrappers.issuewrapper import IssueWrapper
        from lib.wrappers.pullrequestwrapper import PullrequestWrapper
    except ImportError as e:
        logging.error(str(e))
        sys.exit(1)

    # all of these have a get_rate_limit function
    safe_classes = (
        TriageV3,
        GithubWrapper,
        RepoWrapper,
        IssueWrapper,
        PullrequestWrapper,
        HistoryWrapper
    )

    rl = None
    obj = args[0]

    if isinstance(obj, safe_classes):
        rl = obj.get_rate_limit()
    else:
        logging.error('Unhandled ratelimit object type')
        import epdb; epdb.st()

    if rl:
        if isinstance(rl, dict):
            pass
        elif isinstance(rl, RateLimit):
                rl = rl.raw_data
        else:
            logging.error('rl object is uknown type')
            import epdb; epdb.st()

    return rl


def get_reset_time(fn, args):
    '''Return the number of seconds until the rate limit resets'''

    # default to 62 minutes
    reset_time = 60 * 62

    rl = get_rate_limit(fn, args)

    if rl:
        # The time at which the current rate limit window resets
        # in UTC epoch seconds. [ex. 1483405983]
        logging.debug('rate_limit: %s' % str(rl))
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

            #import epdb; epdb.st()
            rl = get_rate_limit(fn, args)

            logging.debug('ratelimited call #%s [%s] [%s] [%s]' %
                          (count,
                           str(type(args[0])),
                           fn.func_name,
                           rl['resources']['core']['remaining']))

            if count > 10:
                logging.error('HIT 10 loop iteration on call, giving up')
                sys.exit(1)

            # default to 5 minute sleep
            stime = 5*60
            try:
                x = fn(*args, **kwargs)
                success = True
            except socket.error as e:
                logging.warning('socket error: sleeping 2 minutes %s' % e)
                time.sleep(2*60)
            except Exception as e:
                print(e)
                if hasattr(e, 'data') and e.data.get('message'):
                    if 'blocked from content creation' in e.data['message']:
                        logging.warning('content creation rate limit exceeded')
                        stime = 2*60
                    elif 'Label does not exist' in e.data['message']:
                        return x
                    elif 'rate limit exceeded' in e.data['message']:
                        logging.warning('general rate limit exceeded')
                        stime = get_reset_time(fn, args)
                    elif isinstance(e, socket.error):
                        logging.warning('socket error')
                        stime = 5*60
                    elif 'Server Error' in e.data.get('message'):
                        logging.warning('server error')
                        stime = 2*60
                    else:
                        import epdb; epdb.st()
                else:
                    import epdb; epdb.st()

                #import epdb; epdb.st()
                logging.warning('sleeping %s minutes' % (stime/60))
                time.sleep(stime)

        return x

    return inner
