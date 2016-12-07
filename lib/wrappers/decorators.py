#!/usr/bin/env python

# https://github.com/octokit/octokit.net/issues/638#issuecomment-67795998

import time
import logging
import functools

from functools import wraps
from inspect import getargspec

def RateLimited(fn):
    argspec = getargspec(fn)

    def inner(*args, **kwargs):

        success = False
        count = 0
        while not success:
            count += 1
            logging.info('rl\'ed call #%s' % count)
            sminutes = 5
            try:
                x = fn(*args, **kwargs)
                success = True
            except Exception as e:
                # e.status == 403 == blocked from content creation
                print(e)
                if hasattr(e, 'data') and e.data.get('message'):
                    if 'blocked from content creation' in e.data['message']:
                        sminutes = 2
                    elif 'rate limit exceeded' in e.data['message']:
                        sminutes = 61
                    else:
                        import epdb; epdb.st()
                else:
                    import epdb; epdb.st()

                logging.info('sleeping %s minutes' % sminutes)
                time.sleep(sminutes*60)

        return x

    return inner


