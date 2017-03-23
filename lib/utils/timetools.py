#!/usr/bin/env python

import logging
from github import GithubObject

def timeobj_from_timestamp(timestamp):
    """Parse a timestamp with pygithub"""
    #logging.error('breakpoint!')
    #import epdb; epdb.st()
    dt = GithubObject.GithubObject._makeDatetimeAttribute(timestamp)
    return dt.value

