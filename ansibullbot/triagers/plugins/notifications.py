#!/usr/bin/env python

import logging


def get_notification_facts(issuewrapper, meta, botmeta=None):
    '''Build facts about mentions/pings'''
    iw = issuewrapper

    nfacts = {
        'to_notify': [],
        'to_assign': []
    }

    if botmeta and not botmeta.get('notifications', False):
        return nfacts

    if iw.is_pullrequest() and iw.merge_commits:
        return nfacts

    # who is assigned?
    current_assignees = iw.assignees

    # add people from files and from matches
    if iw.is_pullrequest() or meta.get('guessed_components') or meta.get('component_matches') or meta.get('module_match'):

        fassign = sorted(set(meta['component_maintainers'][:]))
        fnotify = sorted(set(meta['component_notifiers'][:]))

        if 'ansible' in fassign:
            fassign.remove('ansible')
        if 'ansible' in fnotify:
            fnotify.remove('ansible')

        for user in fnotify:
            if user == iw.submitter:
                continue
            if not iw.history.last_notified(user) and \
                    not iw.history.was_assigned(user) and \
                    not iw.history.was_subscribed(user) and \
                    not iw.history.last_comment(user):

                nfacts['to_notify'].append(user)

            else:
                logging.info(f'{user} already notified')

        for user in fassign:
            if user == iw.submitter:
                continue
            if user in nfacts['to_assign']:
                continue
            #if user not in current_assignees and iw.repo.repo.has_in_assignees(user):
            if user not in current_assignees and iw.repo.has_in_assignees(user):
                nfacts['to_assign'].append(user)

    # prevent duplication
    nfacts['to_assign'] = sorted(set(nfacts['to_assign']))
    nfacts['to_notify'] = sorted(
        set(nfacts['to_notify'])  # + nfacts[u'to_assign'])
    )

    return nfacts
