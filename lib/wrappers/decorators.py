#!/usr/bin/env python

# https://github.com/octokit/octokit.net/issues/638#issuecomment-67795998

# FIXME
#   - [Errno -5] No address associated with hostname

import time
import logging
import socket


def get_reset_time(args):
    obj = args[0]
    if isinstance(obj, lib.wrappers.ghapiwrapper.GithubWrapper):
        import epdb; epdb.st()
    else:
        import epdb; epdb.st()


def RateLimited(fn):
    #argspec = getargspec(fn)

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
            except socket.error:
                logging.warning('socket error: sleeping 2 minutes')
                time.sleep(2*60)
            except Exception as e:
                # e.status == 403 == blocked from content creation
                print(e)
                if hasattr(e, 'data') and e.data.get('message'):
                    if 'blocked from content creation' in e.data['message']:
                        logging.warning('content creation rate limit exceeded')
                        sminutes = 2
                    elif 'rate limit exceeded' in e.data['message']:
                        reset_time = get_reset_time(args)
                        import epdb; epdb.st()
                        logging.warning('general rate limit exceeded')
                        sminutes = 61
                    elif isinstance(e, socket.error):
                        logging.warning('socket error')
                        sminutes = 5
                    elif 'Server Error' in e.data.get('message'):
                        logging.warning('server error')
                        sminutes = 2
                    else:
                        import epdb; epdb.st()
                else:
                    import epdb; epdb.st()

                logging.warning('sleeping %s minutes' % sminutes)
                time.sleep(sminutes*60)

        return x

    return inner
