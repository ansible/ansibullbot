def get_ci_facts(iw, shippable):
    cifacts = {
        u'ci_run_number': None
    }

    if not iw.is_pullrequest():
        return cifacts

    last_run = shippable.get_processed_last_run(iw.pullrequest_status)

    return {'ci_run_number': last_run[u'last_run_id']}


def get_rebuild_facts(iw, meta, force=False):
    rbmeta = {
        u'needs_rebuild': False,
        u'needs_rebuild_all': False,
    }

    if not iw.is_pullrequest():
        return rbmeta

    if not force:
        if not meta[u'ci_stale']:
            return rbmeta

        if meta[u'is_needs_revision']:
            return rbmeta

        if meta[u'is_needs_rebase']:
            return rbmeta

        if not meta[u'has_shippable']:
            return rbmeta

        if not meta[u'shipit']:
            return rbmeta

    rbmeta[u'needs_rebuild'] = True
    rbmeta[u'needs_rebuild_all'] = True

    return rbmeta


def _get_last_command(iw, command, username):
    # FIXME move this into historywrapper
    commands = iw.history.get_commands(username, [command], timestamps=True)

    if not commands:
        return

    # set timestamp for last time command was used
    commands.sort(key=lambda x: x[0])
    last_command = commands[-1][0]

    return last_command


# https://github.com/ansible/ansibullbot/issues/640
def get_rebuild_merge_facts(iw, meta, core_team, shippable):
    rbmerge_meta = {
        u'needs_rebuild': meta.get(u'needs_rebuild', False),
        u'needs_rebuild_all': meta.get(u'needs_rebuild_all', False),
        u'admin_merge': False
    }

    if not iw.is_pullrequest():
        return rbmerge_meta

    if rbmerge_meta[u'needs_rebuild'] and rbmerge_meta[u'needs_rebuild_all']:
        return rbmerge_meta

    if meta[u'is_needs_revision']:
        return rbmerge_meta

    if meta[u'is_needs_rebase']:
        return rbmerge_meta

    last_command = _get_last_command(iw, u'rebuild_merge', core_team)

    if last_command is None:
        return rbmerge_meta

    # new commits should reset everything
    lc = iw.history.last_commit_date
    if lc and lc > last_command:
        return rbmerge_meta

    last_run = shippable.get_processed_last_run(iw.pullrequest_status)

    if last_run[u'state'] != u'pending' and last_run[u'created_at'] < last_command:
        rbmerge_meta[u'needs_rebuild'] = True
        rbmerge_meta[u'needs_rebuild_all'] = True

    if last_run[u'state'] == u'success' and last_run[u'created_at'] > last_command:
        rbmerge_meta[u'admin_merge'] = True

    return rbmerge_meta


# https://github.com/ansible/ansibullbot/issues/1161
def get_rebuild_command_facts(iw, meta, shippable):
    rbmerge_meta = {
        u'needs_rebuild': meta.get(u'needs_rebuild', False),
        u'needs_rebuild_all': meta.get(u'needs_rebuild_all', False),
        u'needs_rebuild_failed': meta.get(u'needs_rebuild_failed', False),
    }

    if not iw.is_pullrequest():
        return rbmerge_meta

    if rbmerge_meta[u'needs_rebuild'] and (rbmerge_meta[u'needs_rebuild_all'] or rbmerge_meta[u'needs_rebuild_failed']):
        return rbmerge_meta

    last_rebuild_failed_command = _get_last_command(iw, u'/rebuild_failed', None)
    last_rebuild_command = _get_last_command(iw, u'/rebuild', None)

    if last_rebuild_command is None and last_rebuild_failed_command is None:
        return rbmerge_meta
    elif last_rebuild_command is None and last_rebuild_failed_command is not None:
        last_command = last_rebuild_failed_command
        meta_key = u'needs_rebuild_failed'
    elif last_rebuild_command is not None and last_rebuild_failed_command is None:
        last_command = last_rebuild_command
        meta_key = u'needs_rebuild_all'
    else:
        if last_rebuild_command >= last_rebuild_failed_command:
            last_command = last_rebuild_command
            meta_key = u'needs_rebuild_all'
        else:
            last_command = last_rebuild_failed_command
            meta_key = u'needs_rebuild_failed'

    # new commits should reset everything
    lc = iw.history.last_commit_date
    if lc and lc > last_command:
        return rbmerge_meta

    last_run = shippable.get_processed_last_run(iw.pullrequest_status)

    if last_run[u'state'] != u'pending' and last_run[u'created_at'] < last_command:
        rbmerge_meta[u'needs_rebuild'] = True
        rbmerge_meta[meta_key] = True

    return rbmerge_meta
