def get_notification_facts(issuewrapper, meta, file_indexer):
    '''Build facts about mentions/pings'''
    iw = issuewrapper

    nfacts = {
        'to_notify': [],
        'to_assign': []
    }

    # who is assigned?
    current_assignees = iw.assignees

    # who can be assigned?
    valid_assignees = [x.login for x in iw.repo.assignees]

    # add people from filemap matches
    if iw.is_pullrequest() or meta.get('guessed_components'):

        if iw.is_pullrequest():
            (fnotify, fassign) = \
                file_indexer.get_filemap_users_for_files(iw.files)
        else:
            (fnotify, fassign) = \
                file_indexer.get_filemap_users_for_files(meta['guessed_components'])

        for user in fnotify:
            if user == iw.submitter:
                continue
            if user not in nfacts['to_notify']:
                if not iw.history.last_notified(user) and \
                        not iw.history.was_assigned(user) and \
                        not iw.history.was_subscribed(user) and \
                        not iw.history.last_comment(user):

                    nfacts['to_notify'].append(user)

        for user in fassign:
            if user == iw.submitter:
                continue
            if user in nfacts['to_assign']:
                continue
            if user not in current_assignees and user in valid_assignees:
                nfacts['to_assign'].append(user)

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
                    nfacts['to_assign'].append(maintainer)

                if maintainer in nfacts['to_notify']:
                    continue

                if not iw.history.last_notified(maintainer) and \
                        not iw.history.was_assigned(maintainer) and \
                        not iw.history.was_subscribed(maintainer) and \
                        not iw.history.last_comment(maintainer):
                    nfacts['to_notify'].append(maintainer)

    #import epdb; epdb.st()
    return nfacts
