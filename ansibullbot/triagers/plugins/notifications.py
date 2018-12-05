#!/usr/bin/env python

import logging


def get_notification_facts(issuewrapper, meta):
    '''Build facts about mentions/pings'''
    iw = issuewrapper

    nfacts = {
        u'to_notify': [],
        u'to_assign': []
    }

    if iw.is_pullrequest() and iw.merge_commits:
        return nfacts

    # who is assigned?
    current_assignees = iw.assignees

    # add people from files and from matches
    if iw.is_pullrequest() or meta.get(u'guessed_components') or meta.get(u'component_matches') or meta.get(u'module_match'):

        '''
        fnotify = []
        fassign = []

        # this needs to be refactored to handle component matches primarily
        if meta.get('component_matches'):
            for cm in meta['component_matches']:
                fnotify += cm.get('owners', [])
                fnotify += cm.get('notify', [])

        # add module maintainers
        if meta.get('module_match'):
            maintainers = meta.get('module_match', {}).get('maintainers', [])

            # do nothing if not maintained
            if maintainers:

                # don't ping us...
                if 'ansible' in maintainers:
                    maintainers.remove('ansible')

                for maintainer in maintainers:

                    # don't notify maintainers of their own issues ... duh
                    if maintainer == iw.submitter:
                        continue

                    if maintainer in valid_assignees and \
                            maintainer not in current_assignees:
                        fassign.append(maintainer)

                    if maintainer in nfacts['to_notify']:
                        continue

                    fnotify.append(maintainer)

        # if component_matches exist, the files were already inspected
        if iw.is_pullrequest() and not meta.get('component_matches'):
            (fnotify, fassign) = \
                file_indexer.get_filemap_users_for_files(iw.files)
        # FIXME: not sure where "guessed" came from
        elif meta.get('guessed_components'):
            (_fnotify, _fassign) = \
                file_indexer.get_filemap_users_for_files(meta['guessed_components'])
            fnotify += _fnotify
            fassign += _fassign

        fassign = sorted(set(fassign))
        fnotify = sorted(set(fnotify))
        '''

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
            if user not in current_assignees and iw.repo.repo.has_in_assignees(user):
                nfacts[u'to_assign'].append(user)

    # prevent duplication
    nfacts[u'to_assign'] = sorted(set(nfacts[u'to_assign']))
    nfacts[u'to_notify'] = sorted(
        set(nfacts[u'to_notify'])  # + nfacts[u'to_assign'])
    )

    return nfacts
