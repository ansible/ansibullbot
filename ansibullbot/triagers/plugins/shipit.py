import itertools
import logging
from fnmatch import fnmatch


def replace_ansible(maintainers, ansible_members, bots=[]):
    '''Replace -ansible- with the -humans- in the org'''
    newlist = []
    for m in maintainers:
        if m != 'ansible':
            newlist.append(m)
        else:
            newlist += ansible_members
    newlist = sorted(set(newlist))
    newlist = [x for x in newlist if x not in bots]
    return newlist


def is_approval(body):
    if not body:
        return False
    lines = [x.strip() for x in body.split()]
    return 'shipit' in lines or '+1' in lines or 'LGTM' in lines or 'rebuild_merge' in lines


def is_rebuild_merge(body):
    if not body:
        return False
    lines = [x.strip() for x in body.split()]
    return 'rebuild_merge' in lines


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
        return {'automerge': automerge, 'automerge_status': automerge_status}

    issue = issuewrapper
    is_supershipit = meta['supershipit']

    if not meta['shipit']:
        return create_ameta(False, 'automerge shipit test failed')

    # https://github.com/ansible/ansibullbot/issues/430
    if meta['is_backport']:
        return create_ameta(False, 'automerge backport test failed')

    if issue.wip:
        return create_ameta(False, 'automerge WIP test failed')

    if not issue.is_pullrequest():
        return create_ameta(False, 'automerge is_pullrequest test failed')

    if meta['merge_commits']:
        return create_ameta(False, 'automerge merge_commits test failed')

    if meta['has_commit_mention']:
        return create_ameta(False, 'automerge commit @mention test failed')

    if meta['is_needs_revision']:
        return create_ameta(False, 'automerge needs_revision test failed')

    if meta['is_needs_rebase']:
        return create_ameta(False, 'automerge needs_rebase test failed')

    if meta['is_needs_info']:
        return create_ameta(False, 'automerge needs_info test failed')

    if not meta['has_ci']:
        return create_ameta(False, 'automerge has_ci test failed')

    if not meta['mergeable']:
        return create_ameta(False, 'automerge mergeable test failed')

    if meta['ci_stale']:
        return create_ameta(False, 'automerge ci_stale test failed')

    # https://github.com/ansible/ansibullbot/issues/904
    if meta['ci_state'] != 'success':
        return create_ameta(False, 'automerge ci_state test failed')

    # component support is a list of the support levels for each file
    cs = [x['support'] for x in meta.get('component_matches', []) if not x['repo_filename'].endswith('/ignore.txt')]
    cs = sorted(set(cs))
    if cs not in [['community'], []]:
        return create_ameta(False, 'automerge community support test failed')

    # extra checks for anything not covered by a supershipit
    if not is_supershipit:

        if meta['is_new_module']:
            return create_ameta(False, 'automerge new_module test failed')

        if meta['is_new_directory']:
            return create_ameta(False, 'automerge is_new_directory test failed')

        if not meta['is_module']:
            return create_ameta(False, 'automerge is_module test failed')

        if not meta['module_match']:
            return create_ameta(False, 'automerge module_match test failed')

        for pr_file in issue.pr_files:

            thisfn = pr_file.filename
            if thisfn.startswith('lib/ansible/modules'):
                continue

            elif fnmatch(thisfn, 'test/sanity/*/*.txt'):
                if pr_file.additions or pr_file.status == 'added':
                    # new exception added, addition must be checked by an human
                    return create_ameta(False, 'automerge new file(s) test failed')
                if pr_file.deletions:
                    # new exception delete
                    continue
            elif thisfn.startswith('changelogs/fragments/') and thisfn.endswith(('.yml', '.yaml')):
                continue
            else:
                # other file modified, pull-request must be checked by an human
                return create_ameta(False, 'automerge !module file(s) test failed')

        if meta.get('component_support') != ['community']:
            return create_ameta(False, 'automerge community support test failed')

    return create_ameta(True, 'automerge tests passed')


def needs_community_review(meta):
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

    if not meta['has_ci']:
        return False

    if not meta['mergeable']:
        return False

    mm = meta.get('module_match', {})
    if not mm:
        return False

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
    if iw.wip:
        return rfacts
    if meta['shipit']:
        return rfacts
    if meta['is_needs_info']:
        return rfacts
    if meta['is_needs_revision']:
        return rfacts
    if meta['is_needs_rebase']:
        return rfacts

    supported_by = get_supported_by(meta)

    if supported_by == 'community':
        rfacts['community_review'] = True
    elif supported_by in ['core', 'network']:
        rfacts['core_review'] = True
    elif supported_by in ['curated', 'certified']:
        rfacts['committer_review'] = True
    else:
        raise Exception(f'unknown supported_by type: {supported_by}')

    return rfacts


def get_shipit_facts(issuewrapper, inmeta, botmeta_files, maintainer_team=[], botnames=[]):
    """ Count shipits by maintainers/community/other """

    # supershipit - maintainers with isolated commit access
    # maintainers - people who maintain this file/module
    # community - people who maintain file(s) in the same directory
    # other - anyone else who comments with shipit/+1/LGTM

    meta = inmeta.copy()
    iw = issuewrapper
    nmeta = {
        'shipit': False,
        'supershipit': False,
        'owner_pr': False,
        'shipit_ansible': False,
        'shipit_community': False,
        'shipit_count_other': False,
        'shipit_count_community': False,
        'shipit_count_maintainer': False,
        'shipit_count_ansible': False,
        'shipit_count_vtotal': False,
        'shipit_count_historical': False,
        'shipit_actors': None,
        'supershipit_actors': None,
        'community_usernames': [],
        'notify_community_shipit': False,
        'is_rebuild_merge': False,
    }

    if not iw.is_pullrequest():
        return nmeta

    # https://github.com/ansible/ansibullbot/issues/1147
    meta['component_matches'] = [
        x for x in meta.get('component_matches', [])
        if not x['repo_filename'].startswith('changelogs/fragments/')
    ]

    files = [f for f in iw.files if not f.startswith('changelogs/fragments/')]

    # https://github.com/ansible/ansibullbot/issues/1238
    meta['component_matches'] = [
        x for x in meta.get('component_matches', [])
        if not x['repo_filename'].startswith('test/sanity')
    ]
    files = [f for f in files if not (f.startswith('test/sanity') and f.endswith('ignore.txt'))]

    # make sure only deletions from ignore.txt are allowed
    for pr_file in iw.pr_files:
        if pr_file.filename.startswith('test/sanity') and pr_file.filename.endswith('ignore.txt'):
            if pr_file.additions > 0:
                logging.debug('failed shipit test for additions on %s' % pr_file.filename)
                return nmeta

    module_utils_files_owned = 0  # module_utils files for which submitter is maintainer
    if meta['is_module_util']:
        for f in files:
            if f.startswith('lib/ansible/module_utils') and f in botmeta_files:
                maintainers = botmeta_files[f].get('maintainers', [])
                if maintainers and (iw.submitter in maintainers):
                    module_utils_files_owned += 1

    modules_files_owned = 0
    if not meta['is_new_module']:
        for f in files:
            if f.startswith('lib/ansible/modules') and iw.submitter in meta['component_maintainers']:
                modules_files_owned += 1
    nmeta['owner_pr'] = modules_files_owned + module_utils_files_owned == len(files)

    # https://github.com/ansible/ansibullbot/issues/722
    if iw.wip:
        logging.debug('WIP PRs do not get shipits')
        return nmeta

    if meta['is_needs_revision'] or meta['is_needs_rebase']:
        logging.debug('PRs with needs_revision or needs_rebase label do not get shipits')
        return nmeta

    supershipiteers_byfile = {}
    supershipiteers_byuser = {}
    for cm in meta.get('component_matches', []):
        _ss = cm.get('supershipit', [])
        supershipiteers_byfile[cm['repo_filename']] = _ss[:]
        for ss in _ss:
            if ss not in supershipiteers_byuser:
                supershipiteers_byuser[ss] = []
            supershipiteers_byuser[ss].append(cm['repo_filename'])

    maintainers = meta.get('component_maintainers', [])
    maintainers = replace_ansible(maintainers, maintainer_team, bots=botnames)

    # community is the other maintainers in the same namespace
    community = meta.get('component_namespace_maintainers', [])
    community = [x for x in community if x != 'ansible' and
                 x not in maintainer_team and
                 x != 'DEPRECATED']

    # shipit tallies
    ansible_shipits = 0
    maintainer_shipits = 0
    community_shipits = 0
    other_shipits = 0
    shipit_actors = []
    shipit_actors_other = []
    supershipiteers_voted = set()
    rebuild_merge = False
    shipits_historical = set()

    for event in iw.history.history:
        if event['event'] not in ['commented', 'committed', 'review_approved', 'review_comment']:
            continue
        if event['actor'] in botnames:
            continue

        logging.info('check %s "%s" for shipit' % (event['actor'], event.get('body')))

        # commits reset the counters
        if event['event'] == 'committed':
            logging.info(event)
            ansible_shipits = 0
            maintainer_shipits = 0
            community_shipits = 0
            other_shipits = 0
            shipit_actors = []
            shipit_actors_other = []
            supershipiteers_voted = set()
            rebuild_merge = False
            logging.info('commit detected, resetting shipit tallies')
            continue

        actor = event['actor']
        body = event.get('body', '')
        body = body.strip()

        if not is_approval(body):
            continue

        # historical shipits (keep track of all of them, even if reset)
        shipits_historical.add(actor)

        if actor in maintainer_team and is_rebuild_merge(body):
            rebuild_merge = True
            logging.info('%s shipit [rebuild_merge]' % actor)
        else:
            logging.info('%s shipit' % actor)

        # super shipits
        if actor in supershipiteers_byuser:
            supershipiteers_voted.add(actor)

        # ansible shipits
        if actor in maintainer_team:
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
    if iw.submitter in maintainer_team:
        if iw.submitter not in shipit_actors:
            ansible_shipits += 1
            shipit_actors.append(iw.submitter)
        shipits_historical.add(iw.submitter)
    elif iw.submitter in maintainers:
        if iw.submitter not in shipit_actors:
            maintainer_shipits += 1
            shipit_actors.append(iw.submitter)
        shipits_historical.add(iw.submitter)
    elif iw.submitter in community:
        if iw.submitter not in shipit_actors:
            community_shipits += 1
            shipit_actors.append(iw.submitter)
        shipits_historical.add(iw.submitter)

    nmeta['shipit_count_other'] = other_shipits
    nmeta['shipit_count_community'] = community_shipits
    nmeta['shipit_count_maintainer'] = maintainer_shipits
    nmeta['shipit_count_ansible'] = ansible_shipits
    nmeta['shipit_actors'] = shipit_actors
    nmeta['shipit_actors_other'] = shipit_actors_other
    nmeta['community_usernames'] = sorted(community)
    nmeta['shipit_count_historical'] = list(shipits_historical)
    nmeta['shipit_count_htotal'] = len(list(shipits_historical))

    total = community_shipits + maintainer_shipits + ansible_shipits
    nmeta['shipit_count_vtotal'] = total + other_shipits

    if rebuild_merge:
        nmeta['is_rebuild_merge'] = True

    # include shipits from other people to push over the edge
    if total == 1 and other_shipits > 2:
        total += other_shipits

    if total > 1 or rebuild_merge:
        nmeta['shipit'] = True
    elif meta['is_new_module'] or \
            (len(maintainers) == 1 and maintainer_shipits == 1):
        # don't notify if there is no maintainer or if submitter is the only namespace maintainer
        if set(community) - {iw.submitter}:
            bpc = iw.history.get_boilerplate_comments()
            bpc = [x[0] for x in bpc]
            if 'community_shipit_notify' not in bpc:
                nmeta['notify_community_shipit'] = True

    logging.info('total shipits: %s' % total)

    # supershipit ...
    #   if a supershipiteer for each file exists and has blessed the PR
    #   on the current commit, then override all shipit tallies and get this PR merged
    if supershipiteers_voted:
        nmeta['supershipit_actors'] = list(supershipiteers_voted)
        cm_files = [x['repo_filename'] for x in meta['component_matches']]
        ss_files = set()
        for ssv in supershipiteers_voted:
            for fn in supershipiteers_byuser[ssv]:
                ss_files.add(fn)

        if sorted(set(cm_files)) == sorted(set(ss_files)):
            logging.info('supershipit enabled on %s' % iw.html_url)
            nmeta['supershipit'] = True
            nmeta['shipit'] = True
        else:
            for cm_file in sorted(cm_files):
                if cm_file not in ss_files:
                    logging.info('%s is not governed by supershipit' % cm_file)

    return nmeta


def get_supported_by(meta):
    # http://docs.ansible.com/ansible/modules_support.html
    # certified: maintained by the community and reviewed by Ansible core team.
    # community: maintained by the community at large.
    # core: maintained by the ansible core team.
    # network: maintained by the ansible network team.

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


def get_submitter_facts(issuewrapper, meta, emails_cache, component_matcher):
    '''Summary stats of submitter's commit history'''
    sfacts = {
        'submitter_previous_commits': 0,
        'submitter_previous_commits_for_pr_files': 0,
    }

    login = issuewrapper.submitter
    all_emails = itertools.chain(
        component_matcher.email_cache.items(),
        emails_cache.items(),
    )

    emails = {k for k, v in all_emails if v == login}

    email_map = \
        component_matcher.gitrepo.get_commits_by_email(emails)

    for value in list(email_map.values()):
        sfacts['submitter_previous_commits'] += value['commit_count']

    for filen in meta.get('component_filenames', ()):
        for email_v in list(email_map.values()):
            sfacts['submitter_previous_commits_for_pr_files'] += email_v['commit_count_byfile'].get(filen, 0)

    return sfacts
