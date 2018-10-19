#!/usr/bin/env python

import itertools
import logging
from fnmatch import fnmatch
from ansibullbot.utils.moduletools import ModuleIndexer

import ansibullbot.constants as C


def is_approval(body):
    if not body:
        return False
    lines = [x.strip() for x in body.split()]
    return u'shipit' in lines or u'+1' in lines or u'LGTM' in lines


def get_automerge_facts(issuewrapper, meta):
    '''Can this be automerged? If not, why?'''

    # AUTOMERGE
    # * New module, existing namespace: require a "shipit" from some
    #   other maintainer in the namespace. (Ideally, identify a maintainer
    #   for the entire namespace.)
    # * New module, new namespace: require discussion with the creator
    #   of the namespace, which will likely be a vendor.
    # * And all new modules, of course, go in as "preview" mode.

    def create_ameta(automerge, automerge_status):
        return {u'automerge': automerge, u'automerge_status': automerge_status}

    issue = issuewrapper

    if not meta[u'shipit']:
        return create_ameta(False, u'automerge shipit test failed')

    # https://github.com/ansible/ansibullbot/issues/430
    if meta[u'is_backport']:
        return create_ameta(False, u'automerge backport test failed')

    if issue.wip:
        return create_ameta(False, u'automerge WIP test failed')

    if not issue.is_pullrequest():
        return create_ameta(False, u'automerge is_pullrequest test failed')

    if meta[u'is_new_directory']:
        return create_ameta(False, u'automerge is_new_directory test failed')

    if meta[u'merge_commits']:
        return create_ameta(False, u'automerge merge_commits test failed')

    if meta[u'has_commit_mention']:
        return create_ameta(False, u'automerge commit @mention test failed')

    if meta[u'is_needs_revision']:
        return create_ameta(False, u'automerge needs_revision test failed')

    if meta[u'is_needs_rebase']:
        return create_ameta(False, u'automerge needs_rebase test failed')

    if meta[u'is_needs_info']:
        return create_ameta(False, u'automerge needs_info test failed')

    if not meta[u'has_shippable']:
        return create_ameta(False, u'automerge has_shippable test failed')

    if meta[u'has_travis']:
        return create_ameta(False, u'automerge has_travis test failed')

    if not meta[u'mergeable']:
        return create_ameta(False, u'automerge mergeable test failed')

    if meta[u'is_new_module']:
        return create_ameta(False, u'automerge new_module test failed')

    if not meta[u'is_module']:
        return create_ameta(False, u'automerge is_module test failed')

    if not meta[u'module_match']:
        return create_ameta(False, u'automerge module_match test failed')

    if meta[u'ci_stale']:
        return create_ameta(False, u'automerge ci_stale test failed')

    # https://github.com/ansible/ansibullbot/issues/904
    if meta[u'ci_state'] != u'success':
        return create_ameta(False, u'automerge ci_state test failed')

    for pr_file in issue.pr_files:

        thisfn = pr_file.filename
        if thisfn.startswith(u'lib/ansible/modules'):
            continue

        elif fnmatch(thisfn, u'test/sanity/*/*.txt'):
            if pr_file.additions or pr_file.status == u'added':
                # new exception added, addition must be checked by an human
                return create_ameta(False, u'automerge new file(s) test failed')
            if pr_file.deletions:
                # new exception delete
                continue
        elif fnmatch(thisfn, u'changelogs/fragments/*') and pr_file.status == u'added':
            # ignore new changelog fragment
            continue
        else:
            # other file modified, pull-request must be checked by an human
            return create_ameta(False, u'automerge !module file(s) test failed')

    if meta.get(u'component_support') != [u'community']:
        return create_ameta(False, u'automerge community support test failed')

    return create_ameta(True, u'automerge tests passed')


def needs_community_review(meta, issue):
    '''Notify community for more shipits?'''

    if not meta[u'is_new_module']:
        return False

    if meta[u'shipit']:
        return False

    if meta[u'is_needs_revision']:
        return False

    if meta[u'is_needs_rebase']:
        return False

    if meta[u'is_needs_info']:
        return False

    if meta[u'ci_state'] == u'pending':
        return False

    if not meta[u'has_shippable']:
        return False

    if meta[u'has_travis']:
        return False

    if not meta[u'mergeable']:
        return False

    mm = meta.get(u'module_match', {})
    if not mm:
        return False

    #metadata = mm.get('metadata') or {}
    #supported_by = metadata.get('supported_by')
    #if supported_by != 'community':
    if meta[u'component_support'] != [u'community']:
        return False

    # expensive call done earlier in processing
    if not meta[u'notify_community_shipit']:
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
        u'core_review': False,
        u'community_review': False,
        u'committer_review': False,
    }

    iw = issuewrapper
    if not iw.is_pullrequest():
        return rfacts
    if meta[u'shipit']:
        return rfacts
    if meta[u'is_needs_info']:
        return rfacts
    if meta[u'is_needs_revision']:
        return rfacts
    if meta[u'is_needs_rebase']:
        return rfacts

    supported_by = get_supported_by(iw, meta)

    if supported_by == u'community':
        rfacts[u'community_review'] = True
    elif supported_by in [u'core', u'network']:
        rfacts[u'core_review'] = True
    elif supported_by in [u'curated', u'certified']:
        rfacts[u'committer_review'] = True
    else:
        if C.DEFAULT_BREAKPOINTS:
            logging.error(u'breakpoint!')
            import epdb; epdb.st()
        else:
            raise Exception(u'unknown supported_by type: {}'.format(supported_by))

    return rfacts


def get_shipit_facts(issuewrapper, meta, module_indexer, core_team=[], botnames=[]):
    """ Count shipits by maintainers/community/other """

    # maintainers - people who maintain this file/module
    # community - people who maintain file(s) in the same directory
    # other - anyone else who comments with shipit/+1/LGTM

    iw = issuewrapper
    nmeta = {
        u'shipit': False,
        u'owner_pr': False,
        u'shipit_ansible': False,
        u'shipit_community': False,
        u'shipit_count_other': False,
        u'shipit_count_community': False,
        u'shipit_count_maintainer': False,
        u'shipit_count_ansible': False,
        u'shipit_count_vtotal': False,
        u'shipit_actors': None,
        u'community_usernames': [],
        u'notify_community_shipit': False,
    }

    if not iw.is_pullrequest():
        return nmeta

    module_utils_files_owned = 0  # module_utils files for which submitter is maintainer
    if meta[u'is_module_util']:
        for f in iw.files:
            if f.startswith(u'lib/ansible/module_utils') and f in module_indexer.botmeta[u'files']:
                maintainers = module_indexer.botmeta[u'files'][f].get(u'maintainers', [])
                if maintainers and (iw.submitter in maintainers):
                    module_utils_files_owned += 1

    modules_files_owned = 0
    if not meta[u'is_new_module']:
        for f in iw.files:
            if f.startswith(u'lib/ansible/modules') and iw.submitter in meta[u'component_maintainers']:
                modules_files_owned += 1
    nmeta[u'owner_pr'] = modules_files_owned + module_utils_files_owned == len(iw.files)

    #if not meta['module_match']:
    #    return nmeta

    # https://github.com/ansible/ansibullbot/issues/722
    if iw.wip:
        logging.debug(u'WIP PRs do not get shipits')
        return nmeta

    if meta[u'is_needs_revision'] or meta[u'is_needs_rebase']:
        logging.debug(u'PRs with needs_revision or needs_rebase label do not get shipits')
        return nmeta

    maintainers = meta.get(u'component_maintainers', [])
    maintainers = \
        ModuleIndexer.replace_ansible(
            maintainers,
            core_team,
            bots=botnames
        )

    # community is the other maintainers in the same namespace
    community = meta.get(u'component_namespace_maintainers', [])
    community = [x for x in community if x != u'ansible' and
                 x not in core_team and
                 x != u'DEPRECATED']

    # shipit tallies
    ansible_shipits = 0
    maintainer_shipits = 0
    community_shipits = 0
    other_shipits = 0
    shipit_actors = []
    shipit_actors_other = []

    for event in iw.history.history:

        if event[u'event'] not in [u'commented', u'committed', u'review_approved', u'review_comment']:
            continue
        if event[u'actor'] in botnames:
            continue

        # commits reset the counters
        if event[u'event'] == u'committed':
            ansible_shipits = 0
            maintainer_shipits = 0
            community_shipits = 0
            other_shipits = 0
            shipit_actors = []
            shipit_actors_other = []
            continue

        actor = event[u'actor']
        body = event.get(u'body', u'')
        body = body.strip()
        if not is_approval(body):
            continue
        logging.info(u'%s shipit' % actor)

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

    nmeta[u'shipit_count_other'] = other_shipits
    nmeta[u'shipit_count_community'] = community_shipits
    nmeta[u'shipit_count_maintainer'] = maintainer_shipits
    nmeta[u'shipit_count_ansible'] = ansible_shipits
    nmeta[u'shipit_actors'] = shipit_actors
    nmeta[u'shipit_actors_other'] = shipit_actors_other
    nmeta[u'community_usernames'] = sorted(community)

    total = community_shipits + maintainer_shipits + ansible_shipits
    nmeta[u'shipit_count_vtotal'] = total + other_shipits

    # include shipits from other people to push over the edge
    if total == 1 and other_shipits > 2:
        total += other_shipits

    if total > 1:
        nmeta[u'shipit'] = True
    elif meta[u'is_new_module'] or \
            (len(maintainers) == 1 and maintainer_shipits == 1):
        # don't notify if there is no maintainer or if submitter is the only namespace maintainer
        if set(community) - {iw.submitter}:
            bpc = iw.history.get_boilerplate_comments()
            bpc = [x[0] for x in bpc]
            if u'community_shipit_notify' not in bpc:
                nmeta[u'notify_community_shipit'] = True

    logging.info(u'total shipits: %s' % total)

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

    supported_by = u'core'
    if not meta.get(u'component_support'):
        return supported_by
    if len(meta.get(u'component_support', [])) == 1 and meta[u'component_support'][0]:
        return meta[u'component_support'][0]
    elif None in meta.get(u'component_support', []):
        supported_by = u'community'
    elif u'core' in meta.get(u'component_support', []):
        supported_by = u'core'
    elif u'network' in meta.get(u'component_support', []):
        supported_by = u'network'
    elif u'certified' in meta.get(u'component_support', []):
        supported_by = u'certified'

    return supported_by


def get_submitter_facts(issuewrapper, meta, module_indexer, component_matcher):
    '''Summary stats of submitter's commit history'''
    sfacts = {
        u'submitter_previous_commits': 0,
        u'submitter_previous_commits_for_pr_files': 0,
    }

    login = issuewrapper.submitter
    all_emails = itertools.chain(
        component_matcher.email_cache.items(),
        module_indexer.emails_cache.items(),
    )

    emails = set(k for k, v in all_emails if v == login)

    email_map = \
        component_matcher.gitrepo.get_commits_by_email(emails)

    for value in list(email_map.values()):
        sfacts[u'submitter_previous_commits'] += value[u'commit_count']

    for filen in meta.get(u'component_filenames', ()):
        for email_v in list(email_map.values()):
            sfacts[u'submitter_previous_commits_for_pr_files'] += email_v[u'commit_count_byfile'].get(filen, 0)

    return sfacts
