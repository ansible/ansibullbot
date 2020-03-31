#!/usr/bin/env python

import datetime
import pytz


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

    # pytz.utc.localize(dts)
    ts = datetime.datetime.strptime(created_at, u'%Y-%m-%dT%H:%M:%SZ')
    ts = pytz.utc.localize(ts)

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

        if meta[u'has_travis']:
            return rbmeta

        if not meta[u'has_shippable']:
            return rbmeta

        if not meta[u'shipit']:
            return rbmeta

    rbmeta[u'needs_rebuild_all'] = True

    return rbmeta


# https://github.com/ansible/ansibullbot/issues/640
def get_rebuild_merge_facts(iw, meta, core_team):

    rbcommand = u'rebuild_merge'

    rbmerge_meta = {
        u'needs_rebuild': meta.get(u'needs_rebuild', False),
        u'admin_merge': False
    }

    if not iw.is_pullrequest():
        return rbmerge_meta

    if meta[u'needs_rebuild']:
        return rbmerge_meta

    if meta[u'is_needs_revision']:
        return rbmerge_meta

    if meta[u'is_needs_rebase']:
        return rbmerge_meta

    rbmerge_commands = iw.history.get_commands(core_team, [rbcommand], timestamps=True)

    # if no rbcommands, skip further processing
    if not rbmerge_commands:
        return rbmerge_meta

    # set timestamp for last time command was used
    rbmerge_commands.sort(key=lambda x: x[0])
    last_command = rbmerge_commands[-1][0]

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
        rbmerge_meta[u'needs_rebuild_all'] = True

    if pr_status[-1][-1] == u'success' and pr_status[-1][0] > last_command:
        rbmerge_meta[u'admin_merge'] = True

    return rbmerge_meta


# https://github.com/ansible/ansibullbot/issues/1161
def get_rebuild_command_facts(iw, meta, core_team, shippable):
    rbcommand = u'/rebuild'

    rbmerge_meta = {
        u'needs_rebuild': meta.get(u'needs_rebuild', False),
        u'needs_rebuild_failed': meta.get(u'needs_rebuild_failed', False),
    }

    if not iw.is_pullrequest():
        return rbmerge_meta

    if meta[u'needs_rebuild']:
        return rbmerge_meta

    # just core team ...
    #rbmerge_commands = iw.history.get_commands(core_team, [rbcommand], timestamps=True)

    # everyone ...
    rbmerge_commands = iw.history.get_commands(None, [rbcommand], timestamps=True)

    # if no rbcommands, skip further processing
    if not rbmerge_commands:
        return rbmerge_meta

    # set timestamp for last time command was used
    rbmerge_commands.sort(key=lambda x: x[0])
    last_command = rbmerge_commands[-1][0]

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
        rbmerge_meta[u'needs_rebuild_failed'] = True

    return rbmerge_meta
