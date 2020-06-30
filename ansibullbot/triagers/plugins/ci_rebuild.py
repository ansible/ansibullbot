import pytz

from ansibullbot.utils.timetools import strip_time_safely


def status_to_date_and_runid(status, keepstate=False):
    """convert pr status to a tuple of date and runid"""

    # https://github.com/ansible/ansibullbot/issues/934
    if not status.get(u'context', u'') == u'Shippable':
        return None

    created_at = status.get(u'created_at')
    target = status.get(u'target_url')
    if target.endswith(u'/summary'):
        target = target.split(u'/')[-2]
    else:
        target = target.split(u'/')[-1]

    try:
        int(target)
    except ValueError:
        # strip new id out of the description
        runid = status[u'description']
        runid = runid.split()[1]
        if runid.isdigit():
            target = runid

    ts = pytz.utc.localize(strip_time_safely(created_at))

    if keepstate:
        return ts, target, status[u'state']
    else:
        return ts, target


def get_ci_facts(iw):
    cifacts = {
        u'ci_run_number': None
    }

    if not iw.is_pullrequest():
        return cifacts

    pr_status = [x for x in iw.pullrequest_status]
    ci_run_ids = []
    for x in pr_status:
        date_and_runid = status_to_date_and_runid(x)
        if date_and_runid is not None:
            ci_run_ids.append(date_and_runid)

    if not ci_run_ids:
        return cifacts

    ci_run_ids.sort(key=lambda x: x[0])
    last_run = ci_run_ids[-1][1]

    return {'ci_run_number': last_run}


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
def get_rebuild_merge_facts(iw, meta, core_team):
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

    pr_status = []
    for x in iw.pullrequest_status:
        date_and_runid = status_to_date_and_runid(x, keepstate=True)
        if date_and_runid is not None:
            pr_status.append(date_and_runid)

    if not pr_status:
        return rbmerge_meta

    pr_status.sort(key=lambda x: x[0])

    if pr_status[-1][-1] != u'pending' and pr_status[-1][0] < last_command:
        rbmerge_meta[u'needs_rebuild'] = True
        rbmerge_meta[u'needs_rebuild_all'] = True

    if pr_status[-1][-1] == u'success' and pr_status[-1][0] > last_command:
        rbmerge_meta[u'admin_merge'] = True

    return rbmerge_meta


# https://github.com/ansible/ansibullbot/issues/1161
def get_rebuild_command_facts(iw, meta):
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

    pr_status = []
    for x in iw.pullrequest_status:
        date_and_runid = status_to_date_and_runid(x, keepstate=True)
        if date_and_runid is not None:
            pr_status.append(date_and_runid)

    if not pr_status:
        return rbmerge_meta

    pr_status.sort(key=lambda x: x[0])

    if pr_status[-1][-1] != u'pending' and pr_status[-1][0] < last_command:
        rbmerge_meta[u'needs_rebuild'] = True
        rbmerge_meta[meta_key] = True

    return rbmerge_meta
