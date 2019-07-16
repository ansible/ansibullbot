#!/usr/bin/env python


def get_cross_reference_facts(issuewrapper, meta):

    iw = issuewrapper

    crfacts = {
        u'has_pr': False,
        u'has_issue': False
    }

    cross_refs = [x for x in iw.events if x['event'] == 'cross-referenced']

    urls = set()
    for cr in cross_refs:
        urls.add(cr['source']['issue']['html_url'])

    pulls = [x for x in urls if '/pull/' in x]
    issues = [x for x in urls if '/pull/' not in x]

    if iw.is_issue() and pulls:
        crfacts[u'has_pr'] = True
    elif iw.is_pullrequest() and issues:
        crfacts[u'has_issue'] = True

    return crfacts
