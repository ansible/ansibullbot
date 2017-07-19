#!/usr/bin/env python

import logging
from fnmatch import fnmatch
from ansibullbot.utils.moduletools import ModuleIndexer


def automergeable(meta, issuewrapper):
    '''Can this be automerged?'''
    issue = issuewrapper

    # https://github.com/ansible/ansibullbot/issues/430
    if meta['is_backport']:
        return False

    if issue.wip:
        return False

    if meta['merge_commits']:
        return False

    if meta['has_commit_mention']:
        return False

    if meta['is_needs_revision']:
        return False

    if meta['is_needs_rebase']:
        return False

    if meta['is_needs_info']:
        return False

    if not meta['has_shippable']:
        return False

    if meta['has_travis']:
        return False

    if not meta['mergeable']:
        return False

    if meta['is_new_module']:
        return False

    if not meta['is_module']:
        return False

    if not meta['module_match']:
        return False

    for pr_file in issue.pr_files:
        matched_filename = meta['module_match'].get('repo_filename')
        if matched_filename and pr_file.filename == matched_filename:
            continue
        elif fnmatch(pr_file.filename, 'test/sanity/*/*.txt'):
            if pr_file.additions or pr_file.status == 'added':
                # new exception added, addition must be checked by an human
                return False
            if pr_file.deletions:
                # new exception delete
                continue
        else:
            # other file modified, pull-request must be checked by an human
            return False

    metadata = meta['module_match']['metadata']
    supported_by = metadata.get('supported_by')
    if supported_by != 'community':
        return False

    return True


def needs_community_review(meta, issue):
    '''Notify community for more shipits?'''

    if not meta['is_new_module']:
        return False

    if meta['shipit']:
        return False

    if meta['is_needs_revision']:
        return False

    if meta['is_needs_rebase']:
        return False

    if meta['is_needs_info']:
        return False

    if meta['ci_state'] == 'pending':
        return False

    if not meta['has_shippable']:
        return False

    if meta['has_travis']:
        return False

    if not meta['mergeable']:
        return False

    mm = meta.get('module_match', {})
    if not mm:
        return False

    metadata = mm.get('metadata') or {}
    supported_by = metadata.get('supported_by')

    if supported_by != 'community':
        return False

    # expensive call done earlier in processing
    if not meta['notify_community_shipit']:
        return False

    return True


def get_shipit_facts(issuewrapper, meta, module_indexer, core_team=[], botnames=[]):
    # shipit/+1/LGTM in comment.body from maintainer

    # AUTOMERGE
    # * New module, existing namespace: require a "shipit" from some
    #   other maintainer in the namespace. (Ideally, identify a maintainer
    #   for the entire namespace.)
    # * New module, new namespace: require discussion with the creator
    #   of the namespace, which will likely be a vendor.
    # * And all new modules, of course, go in as "preview" mode.

    iw = issuewrapper
    nmeta = {
        'shipit': False,
        'owner_pr': False,
        'shipit_ansible': False,
        'shipit_community': False,
        'shipit_count_community': False,
        'shipit_count_maintainer': False,
        'shipit_count_ansible': False,
        'shipit_actors': None,
        'community_usernames': [],
        'notify_community_shipit': False,
    }

    if not iw.is_pullrequest():
        return nmeta
    if not meta['module_match']:
        return nmeta

    maintainers = meta['module_match']['maintainers']
    maintainers = \
        ModuleIndexer.replace_ansible(
            maintainers,
            core_team,
            bots=botnames
        )

    if not meta['is_new_module'] and iw.submitter in maintainers:
        nmeta['owner_pr'] = True

    # community is the other maintainers in the same namespace
    mnamespace = meta['module_match']['namespace']
    community = \
        module_indexer.get_maintainers_for_namespace(mnamespace)
    community = [x for x in community if x != 'ansible' and
                 x not in core_team and
                 x != 'DEPRECATED']

    # shipit tallies
    ansible_shipits = 0
    maintainer_shipits = 0
    community_shipits = 0
    shipit_actors = []

    for event in iw.history.history:

        if event['event'] not in ['commented', 'committed']:
            continue
        if event['actor'] in botnames:
            continue

        # commits reset the counters
        if event['event'] == 'committed':
            ansible_shipits = 0
            maintainer_shipits = 0
            community_shipits = 0
            shipit_actors = []
            continue

        actor = event['actor']
        body = event['body']

        # ansible shipits
        if actor in core_team:
            if 'shipit' in body or '+1' in body or 'LGTM' in body:
                logging.info('%s shipit' % actor)
                if actor not in shipit_actors:
                    ansible_shipits += 1
                    shipit_actors.append(actor)
                continue

        # maintainer shipits
        if actor in maintainers:
            if 'shipit' in body or '+1' in body or 'LGTM' in body:
                logging.info('%s shipit' % actor)
                if actor not in shipit_actors:
                    maintainer_shipits += 1
                    shipit_actors.append(actor)
                continue

        # community shipits
        if actor in community:
            if 'shipit' in body or '+1' in body or 'LGTM' in body:
                logging.info('%s shipit' % actor)
                if actor not in shipit_actors:
                    community_shipits += 1
                    shipit_actors.append(actor)
                continue

    # submitters should count if they are maintainers/community
    if iw.submitter in maintainers:
        if iw.submitter not in shipit_actors:
            maintainer_shipits += 1
            shipit_actors.append(iw.submitter)
    elif iw.submitter in community:
        if iw.submitter not in shipit_actors:
            community_shipits += 1
            shipit_actors.append(iw.submitter)

    nmeta['shipit_count_community'] = community_shipits
    nmeta['shipit_count_maintainer'] = maintainer_shipits
    nmeta['shipit_count_ansible'] = ansible_shipits
    nmeta['shipit_actors'] = shipit_actors
    nmeta['community_usernames'] = sorted(community)

    if (community_shipits + maintainer_shipits + ansible_shipits) > 1:
        nmeta['shipit'] = True
    elif meta['is_new_module'] or \
            (len(maintainers) == 1 and maintainer_shipits == 1):
        if community:
            bpc = iw.history.get_boilerplate_comments()
            if 'community_shipit_notify' not in bpc:
                nmeta['notify_community_shipit'] = True

    logging.info(
        'total shipits: %s' %
        (community_shipits + maintainer_shipits + ansible_shipits)
    )

    return nmeta
