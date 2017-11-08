#!/usr/bin/env python

import logging
from fnmatch import fnmatch
from ansibullbot.utils.moduletools import ModuleIndexer

import ansibullbot.constants as C


def is_approval(body):
    return 'shipit' in body or '+1' in body or 'LGTM' in body


def automergeable(meta, issuewrapper):
    '''Can this be automerged?'''

    # AUTOMERGE
    # * New module, existing namespace: require a "shipit" from some
    #   other maintainer in the namespace. (Ideally, identify a maintainer
    #   for the entire namespace.)
    # * New module, new namespace: require discussion with the creator
    #   of the namespace, which will likely be a vendor.
    # * And all new modules, of course, go in as "preview" mode.

    issue = issuewrapper

    # https://github.com/ansible/ansibullbot/issues/430
    if meta['is_backport']:
        return False

    if issue.wip:
        return False

    if not issue.is_pullrequest():
        return False

    if meta['is_new_directory']:
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

    if meta['ci_stale']:
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

    #metadata = mm.get('metadata') or {}
    #supported_by = metadata.get('supported_by')
    #if supported_by != 'community':
    if meta['component_support'] != ['community']:
        return False

    # expensive call done earlier in processing
    if not meta['notify_community_shipit']:
        return False

    return True


def get_review_facts(issuewrapper, meta):
    # Thanks @jpeck-resilient for this new module. When this module
    # receives 'shipit' comments from two community members and any
    # 'needs_revision' comments have been resolved, we will mark for
    # inclusion

    # pr is a module
    # pr owned by community or is new
    # pr owned by ansible

    rfacts = {
        'core_review': False,
        'community_review': False,
        'committer_review': False,
    }

    iw = issuewrapper
    if not iw.is_pullrequest():
        return rfacts
    if meta['shipit']:
        return rfacts
    if meta['is_needs_info']:
        return rfacts
    if meta['is_needs_revision']:
        return rfacts
    if meta['is_needs_rebase']:
        return rfacts
    if not meta['is_module']:
        return rfacts

    supported_by = get_supported_by(iw, meta)

    if supported_by == 'community':
        rfacts['community_review'] = True
    elif supported_by in ['core', 'network']:
        rfacts['core_review'] = True
    elif supported_by in ['curated', 'certified']:
        rfacts['committer_review'] = True
    else:
        if C.DEFAULT_BREAKPOINTS:
            logging.error('breakpoint!')
            import epdb; epdb.st()
        else:
            raise Exception('unknown supported_by type: {}'.format(supported_by))

    return rfacts


def get_shipit_facts(issuewrapper, meta, module_indexer, core_team=[], botnames=[]):
    """ Count shipits by maintainers/community/other """

    # maintainers - people who maintain this file/module
    # community - people who maintain file(s) in the same directory
    # other - anyone else who comments with shipit/+1/LGTM

    iw = issuewrapper
    nmeta = {
        'shipit': False,
        'owner_pr': False,
        'shipit_ansible': False,
        'shipit_community': False,
        'shipit_count_other': False,
        'shipit_count_community': False,
        'shipit_count_maintainer': False,
        'shipit_count_ansible': False,
        'shipit_actors': None,
        'community_usernames': [],
        'notify_community_shipit': False,
    }

    if not iw.is_pullrequest():
        return nmeta

    module_utils_files_owned = 0  # module_utils files for which submitter is maintainer
    if meta['is_module_util']:
        for f in iw.files:
            if f.startswith('lib/ansible/module_utils') and f in module_indexer.botmeta['files']:
                maintainers = module_indexer.botmeta['files'][f].get('maintainers', [])
                if maintainers and (iw.submitter in maintainers):
                    module_utils_files_owned += 1
        if module_utils_files_owned == len(iw.files):
            nmeta['owner_pr'] = True
            return nmeta

    if not meta['module_match']:
        return nmeta

    # https://github.com/ansible/ansibullbot/issues/722
    if iw.wip:
        logging.debug('WIP PRs do not get shipits')
        return nmeta

    if meta['is_needs_revision'] or meta['is_needs_rebase']:
        logging.debug('PRs with needs_revision or needs_rebase label do not get shipits')
        return nmeta

    #maintainers = meta['module_match']['maintainers']
    maintainers = meta.get('component_maintainers', [])
    maintainers = \
        ModuleIndexer.replace_ansible(
            maintainers,
            core_team,
            bots=botnames
        )

    modules_files_owned = 0
    if not meta['is_new_module']:
        for f in iw.files:
            if f.startswith('lib/ansible/modules') and iw.submitter in module_indexer.modules[f]['maintainers']:
                modules_files_owned += 1
    nmeta['owner_pr'] = modules_files_owned + module_utils_files_owned == len(iw.files)

    # community is the other maintainers in the same namespace

    #mnamespace = meta['module_match']['namespace']
    #community = \
    #    module_indexer.get_maintainers_for_namespace(mnamespace)

    community = meta.get('component_namespace_maintainers', [])
    community = [x for x in community if x != 'ansible' and
                 x not in core_team and
                 x != 'DEPRECATED']

    # shipit tallies
    ansible_shipits = 0
    maintainer_shipits = 0
    community_shipits = 0
    other_shipits = 0
    shipit_actors = []
    shipit_actors_other = []

    for event in iw.history.history:

        if event['event'] not in ['commented', 'committed', 'review_approved', 'review_comment']:
            continue
        if event['actor'] in botnames:
            continue

        # commits reset the counters
        if event['event'] == 'committed':
            ansible_shipits = 0
            maintainer_shipits = 0
            community_shipits = 0
            other_shipits = 0
            shipit_actors = []
            shipit_actors_other = []
            continue

        actor = event['actor']
        body = event.get('body', '')
        body = body.strip()
        if not is_approval(body):
            continue
        logging.info('%s shipit' % actor)

        # ansible shipits
        if actor in core_team:
            if actor not in shipit_actors:
                ansible_shipits += 1
                shipit_actors.append(actor)
            continue

        # maintainer shipits
        if actor in maintainers:
            if actor not in shipit_actors:
                maintainer_shipits += 1
                shipit_actors.append(actor)
            continue

        # community shipits
        if actor in community:
            if actor not in shipit_actors:
                community_shipits += 1
                shipit_actors.append(actor)
            continue

        # other shipits
        if actor not in shipit_actors_other:
            other_shipits += 1
            shipit_actors_other.append(actor)
        continue

    # submitters should count if they are core team/maintainers/community
    if iw.submitter in core_team:
        if iw.submitter not in shipit_actors:
            ansible_shipits += 1
            shipit_actors.append(iw.submitter)
    elif iw.submitter in maintainers:
        if iw.submitter not in shipit_actors:
            maintainer_shipits += 1
            shipit_actors.append(iw.submitter)
    elif iw.submitter in community:
        if iw.submitter not in shipit_actors:
            community_shipits += 1
            shipit_actors.append(iw.submitter)

    nmeta['shipit_count_other'] = other_shipits
    nmeta['shipit_count_community'] = community_shipits
    nmeta['shipit_count_maintainer'] = maintainer_shipits
    nmeta['shipit_count_ansible'] = ansible_shipits
    nmeta['shipit_actors'] = shipit_actors
    nmeta['shipit_actors_other'] = shipit_actors_other
    nmeta['community_usernames'] = sorted(community)

    total = community_shipits + maintainer_shipits + ansible_shipits

    # include shipits from other people to push over the edge
    if total == 1 and other_shipits > 2:
        total += other_shipits

    if total > 1:
        nmeta['shipit'] = True
    elif meta['is_new_module'] or \
            (len(maintainers) == 1 and maintainer_shipits == 1):
        # don't notify if there is no maintainer or if submitter is the only namespace maintainer
        if set(community) - {iw.submitter}:
            bpc = iw.history.get_boilerplate_comments()
            if 'community_shipit_notify' not in bpc:
                nmeta['notify_community_shipit'] = True

    logging.info('total shipits: %s' % total)

    return nmeta


def get_supported_by(issuewrapper, meta):

    # http://docs.ansible.com/ansible/modules_support.html
    # certified: maintained by the community and reviewed by Ansible core team.
    # community: maintained by the community at large.
    # core: maintained by the ansible core team.
    # network: maintained by the ansible network team.

    '''
    supported_by = 'core'
    mmatch = meta.get('module_match')
    if mmatch:
        mmeta = mmatch.get('metadata', {})
        if mmeta:
            supported_by = mmeta.get('supported_by', 'core')
    if meta['is_new_module']:
        supported_by = 'community'
    '''

    supported_by = 'core'
    if not meta.get('component_support'):
        return supported_by
    if len(meta.get('component_support', [])) == 1 and meta['component_support'][0]:
        return meta['component_support'][0]
    elif None in meta.get('component_support', []):
        supported_by = 'community'
    elif 'core' in meta.get('component_support', []):
        supported_by = 'core'
    elif 'network' in meta.get('component_support', []):
        supported_by = 'network'
    elif 'certified' in meta.get('component_support', []):
        supported_by = 'certified'

    return supported_by
