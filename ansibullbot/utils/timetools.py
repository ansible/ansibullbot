#!/usr/bin/env python

import datetime
import logging
from github import GithubObject


def timeobj_from_timestamp(timestamp):
    """Parse a timestamp with pygithub"""
    dt = GithubObject.GithubObject._makeDatetimeAttribute(timestamp)
    return dt.value


def strip_time_safely(tstring):
    """Try various formats to strip the time from a string"""
    res = None
    tsformats = [
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S'
    ]
    for idx,tsformat in enumerate(tsformats):
        try:
            res = datetime.datetime.strptime(tstring, tsformat)
            break
        except Exception:
            pass
    if res is None:
        logging.error('{} could not be stripped'.format(tstring))
        raise Exception('{} could not be stripped'.format(tstring))
    return res
