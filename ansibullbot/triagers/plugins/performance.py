#!/usr/bin/env python


def get_performance_facts(issuewrapper, meta):
    iw = issuewrapper

    pfacts = {
        u'is_performance': False
    }

    body = u''
    try:
        body = iw.body.lower()
    except AttributeError:
        pass

    title = u''
    try:
        title = iw.title.lower()
    except AttributeError:
        pass

    # TODO search in comments too?
    for data in (body, title):
        if u'performance' in data:
            pfacts[u'is_performance'] = True
            break

    return pfacts
