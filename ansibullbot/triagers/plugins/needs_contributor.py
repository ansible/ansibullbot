#!/usr/bin/env python


def get_needs_contributor_facts(triager, issuewrapper, meta):
    needs_contributor = False

    for event in issuewrapper.history.history:
        if event[u'actor'] in triager.BOTNAMES:
            continue

        if event[u'event'] == u'labeled':
            if event[u'label'] in [u'needs_contributor', u'waiting_on_contributor']:
                needs_contributor = True
                continue

        if event[u'event'] == u'unlabeled':
            if event[u'label'] == [u'needs_contributor', u'waiting_on_contributor']:
                needs_contributor = False
                continue

        if event[u'event'] == u'commented':
            if u'!needs_contributor' in event[u'body']:
                needs_contributor = False
                continue

            if u'needs_contributor' in event[u'body'] and u'!needs_contributor' not in event[u'body']:
                needs_contributor = True
                continue

    return {u'is_needs_contributor': needs_contributor}
