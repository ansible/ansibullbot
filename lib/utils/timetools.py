#!/usr/bin/env python

from github import GithubObject

def timeobj_from_timestamp(timestamp):    
    """Parse a timestamp with pygithub"""
    import epdb; epdb.st()
    dt = GithubObject.GithubObject._makeDatetimeAttribute(timestamp)
    return dt.value

