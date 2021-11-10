def get_ci_facts(iw, ci):
    cifacts = {
        'ci_run_number': None
    }

    if not iw.is_pullrequest():
        return cifacts

    if ci.last_run is None:
        return cifacts

    return {'ci_run_number': ci.last_run['run_id']}


def get_rebuild_facts(iw, meta, force=False):
    rbmeta = {
        'needs_rebuild': False,
        'needs_rebuild_all': False,
    }

    if not iw.is_pullrequest():
        return rbmeta

    if not force:
        if not meta['ci_stale']:
            return rbmeta

        if meta['is_needs_revision']:
            return rbmeta

        if meta['is_needs_rebase']:
            return rbmeta

        if not meta['has_ci']:
            return rbmeta

        if not meta['shipit']:
            return rbmeta

    rbmeta['needs_rebuild'] = True
    rbmeta['needs_rebuild_all'] = True

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
def get_rebuild_merge_facts(iw, meta, maintainer_team, ci):
    rbmerge_meta = {
        'needs_rebuild': meta.get('needs_rebuild', False),
        'needs_rebuild_all': meta.get('needs_rebuild_all', False),
        'admin_merge': False
    }

    if not iw.is_pullrequest():
        return rbmerge_meta

    if rbmerge_meta['needs_rebuild'] and rbmerge_meta['needs_rebuild_all']:
        return rbmerge_meta

    if meta['is_needs_revision']:
        return rbmerge_meta

    if meta['is_needs_rebase']:
        return rbmerge_meta

    last_command = _get_last_command(iw, 'rebuild_merge', maintainer_team)

    if last_command is None:
        return rbmerge_meta

    # new commits should reset everything
    lc = iw.history.last_commit_date
    if lc and lc > last_command:
        return rbmerge_meta

    if ci.last_run is None:
        return rbmerge_meta

    ci_updated_at = ci.last_run.get('updated_at', ci.last_run.get('created_at'))

    if ci.last_run['state'] != 'pending' and ci_updated_at < last_command:
        rbmerge_meta['needs_rebuild'] = True
        rbmerge_meta['needs_rebuild_all'] = True

    if ci.last_run['state'] == 'success' and ci_updated_at > last_command:
        rbmerge_meta['admin_merge'] = True

    return rbmerge_meta


# https://github.com/ansible/ansibullbot/issues/1161
def get_rebuild_command_facts(iw, meta, ci):
    rbmerge_meta = {
        'needs_rebuild': meta.get('needs_rebuild', False),
        'needs_rebuild_all': meta.get('needs_rebuild_all', False),
        'needs_rebuild_failed': meta.get('needs_rebuild_failed', False),
    }

    if not iw.is_pullrequest():
        return rbmerge_meta

    if rbmerge_meta['needs_rebuild'] and (rbmerge_meta['needs_rebuild_all'] or rbmerge_meta['needs_rebuild_failed']):
        return rbmerge_meta

    last_rebuild_failed_command = _get_last_command(iw, '/rebuild_failed', None)
    last_rebuild_command = _get_last_command(iw, '/rebuild', None)

    if last_rebuild_command is None and last_rebuild_failed_command is None:
        return rbmerge_meta
    elif last_rebuild_command is None and last_rebuild_failed_command is not None:
        last_command = last_rebuild_failed_command
        meta_key = 'needs_rebuild_failed'
    elif last_rebuild_command is not None and last_rebuild_failed_command is None:
        last_command = last_rebuild_command
        meta_key = 'needs_rebuild_all'
    else:
        if last_rebuild_command >= last_rebuild_failed_command:
            last_command = last_rebuild_command
            meta_key = 'needs_rebuild_all'
        else:
            last_command = last_rebuild_failed_command
            meta_key = 'needs_rebuild_failed'

    # new commits should reset everything
    lc = iw.history.last_commit_date
    if lc and lc > last_command:
        return rbmerge_meta

    if ci.last_run is None:
        return rbmerge_meta

    ci_updated_at = ci.last_run.get('updated_at', ci.last_run.get('created_at'))

    if ci.last_run['state'] != 'pending' and ci_updated_at < last_command:
        rbmerge_meta['needs_rebuild'] = True
        rbmerge_meta[meta_key] = True

    return rbmerge_meta
