#!/usr/bin/env python

import logging


def get_notification_facts(issuewrapper, meta, botmeta=None):
    '''Build facts about mentions/pings'''
    iw = issuewrapper

    nfacts = {
        u'to_notify': [],
        u'to_assign': []
    }

    if botmeta and not botmeta.get(u'notifications', False):
        return nfacts

    if iw.is_pullrequest() and iw.merge_commits:
        return nfacts

    # who is assigned?
    current_assignees = iw.assignees

    # add people from files and from matches
    if iw.is_pullrequest() or meta.get(u'guessed_components') or meta.get(u'component_matches') or meta.get(u'module_match'):

        fassign = sorted(set(meta[u'component_maintainers'][:]))
        fnotify = sorted(set(meta[u'component_notifiers'][:]))

        if u'ansible' in fassign:
            fassign.remove(u'ansible')
        if u'ansible' in fnotify:
            fnotify.remove(u'ansible')

        for user in fnotify:
            if user == iw.submitter:
                continue
            if not iw.history.last_notified(user) and \
                    not iw.history.was_assigned(user) and \
                    not iw.history.was_subscribed(user) and \
                    not iw.history.last_comment(user):

                nfacts[u'to_notify'].append(user)

            else:
                logging.info(u'{} already notified'.format(user))

        for user in fassign:
            if user == iw.submitter:
                continue
            if user in nfacts[u'to_assign']:
                continue
            #if user not in current_assignees and iw.repo.repo.has_in_assignees(user):
            if user not in current_assignees and iw.repo.has_in_assignees(user):
                nfacts[u'to_assign'].append(user)

    # prevent duplication
    nfacts[u'to_assign'] = sorted(set(nfacts[u'to_assign']))
    nfacts[u'to_notify'] = sorted(
        set(nfacts[u'to_notify'])  # + nfacts[u'to_assign'])
    )

    return nfacts
