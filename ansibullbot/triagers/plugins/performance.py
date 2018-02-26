#!/usr/bin/env python

def get_performance_facts(issuewrapper, meta):
    iw = issuewrapper

    pfacts = {
        'is_performance': False
    }

    body = iw.body.lower()
    title = iw.title.lower()

    # TODO search in comments too?
    for data in (body, title):
        if 'performance' in data:
            pfacts['is_performance'] = True
            break

    return pfacts
