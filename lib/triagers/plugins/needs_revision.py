#!/usr/bin/env python

import logging


def get_needs_revision_facts(triager, issuewrapper, meta):
    # Thanks @adityacs for this PR. This PR requires revisions, either
    # because it fails to build or by reviewer request. Please make the
    # suggested revisions. When you are done, please comment with text
    # 'ready_for_review' and we will put this PR back into review.

    # a "dirty" mergeable_state can exist with "successfull" ci_state.

    # short alias
    iw = issuewrapper

    committer_count = None
    needs_revision = False
    needs_revision_msgs = []
    merge_commits = []
    has_merge_commit_notification = False
    needs_rebase = False
    needs_rebase_msgs = []
    has_shippable = False
    has_landscape = False
    has_travis = False
    has_travis_notification = False
    ci_state = None
    mstate = None
    change_requested = None
    #hreviews = None
    #reviews = None
    ready_for_review = None
    has_commit_mention = False
    has_commit_mention_notification = False

    rmeta = {
        'committer_count': committer_count,
        'is_needs_revision': needs_revision,
        'is_needs_revision_msgs': needs_revision_msgs,
        'is_needs_rebase': needs_rebase,
        'is_needs_rebase_msgs': needs_rebase_msgs,
        'has_commit_mention': has_commit_mention,
        'has_commit_mention_notification': has_commit_mention_notification,
        'has_shippable': has_shippable,
        'has_landscape': has_landscape,
        'has_travis': has_travis,
        'has_travis_notification': has_travis_notification,
        'merge_commits': merge_commits,
        'has_merge_commit_notification': has_merge_commit_notification,
        'mergeable': None,
        'mergeable_state': mstate,
        'change_requested': change_requested,
        'ci_state': ci_state,
        'reviews': None,
        'www_reviews': None,
        'www_summary': None,
        'ready_for_review': ready_for_review
    }

    if not iw.is_pullrequest():
        return rmeta

    maintainers = [x for x in triager.ansible_core_team
                   if x not in triager.BOTNAMES]
    if meta.get('module_match'):
        maintainers += meta['module_match'].get('maintainers', [])

    # get the exact state from shippable ...
    #   success/pending/failure/... ?
    ci_status = iw.pullrequest_status

    # code quality hooks
    if [x for x in ci_status if 'landscape.io' in x['target_url']]:
        has_landscape = True

    ci_states = [x['state'] for x in ci_status
                 if 'shippable.com' in x['target_url']]
    if not ci_states:
        ci_state = None
    else:
        ci_state = ci_states[0]
    logging.info('ci_state == %s' % ci_state)

    # clean/unstable/dirty/unknown
    mstate = iw.mergeable_state
    if not mstate:
        mstate = 'unknown'
    logging.info('mergeable_state == %s' % mstate)

    # clean/unstable/dirty/unknown
    if mstate != 'clean':

        if ci_state == 'failure':
            needs_revision = True
            needs_revision_msgs.append('ci failure')

        if mstate == 'dirty':
            needs_revision = True
            needs_rebase = True
            needs_revision_msgs.append('mergeable state is dirty')
            needs_rebase_msgs.append('mergeable state is dirty')

        elif mstate == 'unknown':
            # if tests are still running, this needs to be ignored.
            if ci_state not in ['pending']:
                needs_revision = True
                needs_revision_msgs.append('mergeable state is unknown')
                needs_rebase = True
                needs_rebase_msgs.append('mergeable state is unknown')

        elif mstate == 'unstable':
            # reduce the label churn
            if ci_state == 'pending' and 'needs_revision' in iw.labels:
                needs_revision = True
                needs_rebase_msgs.append('keep label till test finished')

    else:

        current_hash = None
        #pending_reviews = []
        hash_reviews = {}

        for event in iw.history.history:

            if event['actor'] in triager.BOTNAMES:
                continue

            if event['actor'] in maintainers and \
                    event['actor'] != iw.submitter:

                if event['event'] == 'labeled':
                    if event['label'] == 'needs_revision':
                        needs_revision = True
                        needs_revision_msgs.append(
                            '[%s] labeled' % event['actor']
                        )
                        continue

                if event['event'] == 'unlabeled':
                    if event['label'] == 'needs_revision':
                        needs_revision = False
                        needs_revision_msgs.append(
                            '[%s] unlabeled' % event['actor']
                        )
                        continue

                if event['event'] == 'commented':
                    if '!needs_revision' in event['body']:
                        needs_revision = False
                        needs_revision_msgs.append(
                            '[%s] !needs_revision' % event['actor']
                        )
                        continue

                if event['event'] == 'commented':
                    if 'needs_revision' in event['body'] and \
                            '!needs_revision' not in event['body']:
                        needs_revision = True
                        needs_revision_msgs.append(
                            '[%s] needs_revision' % event['actor']
                        )
                        continue

            if event['actor'] == iw.submitter:
                if event['event'] == 'commented':
                    if 'ready_for_review' in event['body']:
                        ready_for_review = True
                        needs_revision = False
                        needs_revision_msgs.append(
                            '[%s] ready_for_review' % event['actor']
                        )
                        continue
                    if 'shipit' in event['body'].lower():
                        ready_for_review = True
                        needs_revision = False
                        needs_revision_msgs.append(
                            '[%s] shipit' % event['actor']
                        )
                        continue

            if event['event'].startswith('review_'):

                if 'commit_id' in event:

                    if event['commit_id'] not in hash_reviews:
                        hash_reviews[event['commit_id']] = []

                    if not current_hash:
                        current_hash = event['commit_id']
                    else:
                        if event['commit_id'] != current_hash:
                            current_hash = event['commit_id']
                            #pending_reviews = []

                else:
                    # https://github.com/ansible/ansible/pull/20680
                    # FIXME - not sure why this happens.
                    continue

                if event['event'] == 'review_changes_requested':
                    #pending_reviews.append(event['actor'])
                    hash_reviews[event['commit_id']].append(event['actor'])
                    needs_revision = True
                    needs_revision_msgs.append(
                        '[%s] changes requested' % event['actor']
                    )
                    continue

                if event['event'] == 'review_approved':
                    #if event['actor'] in pending_reviews:
                    #    pending_reviews.remove(event['actor'])

                    if event['actor'] in hash_reviews[event['commit_id']]:
                        hash_reviews[event['commit_id']].remove(
                            event['actor']
                        )

                    needs_revision = False
                    needs_revision_msgs.append(
                        '[%s] approved changes' % event['actor']
                    )
                    continue

                if event['event'] == 'review_dismissed':
                    #if event['actor'] in pending_reviews:
                    #    pending_reviews.remove(event['actor'])

                    if event['actor'] in hash_reviews[event['commit_id']]:
                        hash_reviews[event['commit_id']].remove(
                            event['actor']
                        )

                    needs_revision = False
                    needs_revision_msgs.append(
                        '[%s] dismissed review' % event['actor']
                    )
                    continue

        # reviews on missing commits can be disgarded
        outstanding = []
        current_shas = [x.sha for x in iw.commits]
        for k,v in hash_reviews.items():
            if not v:
                continue
            if k in current_shas:
                #outstanding.append((k,v))
                outstanding += v
        outstanding = sorted(set(outstanding))
        #import epdb; epdb.st()

        '''
        if pending_reviews:
            #change_requested = pending_reviews
            change_requested = outstanding
            needs_revision = True
            needs_revision_msgs.append(
                'reviews pending: %s' % ','.join(pending_reviews)
            )
        '''

        if outstanding:
            needs_revision = True
            needs_revision_msgs.append(
                'outstanding reviews: %s' % ','.join(outstanding)
            )

    # Merge commits are bad, force a rebase
    if iw.merge_commits:
        needs_rebase = True

        for mc in iw.merge_commits:
            merge_commits.append(mc.html_url)
            needs_rebase_msgs.append('merge commit %s' % mc.commit.sha)

        bpc = iw.history.get_boilerplate_comments()
        if 'merge_commit_notify' not in bpc:
            has_merge_commit_notification = False
        else:
            mc_comments = iw.history.search_user_comments(
                triager.BOTNAMES,
                'boilerplate: merge_commit_notify'
            )
            last_mc_comment = mc_comments[-1]
            mc_missing = []
            for mc in iw.merge_commits:
                if mc.html_url not in last_mc_comment:
                    mc_missing.append(mc)
            if mc_missing:
                has_merge_commit_notification = False
            else:
                has_merge_commit_notification = True

    # Count committers
    committer_count = len(sorted(set(iw.committer_emails)))

    if ci_status:
        for x in ci_status:
            if 'travis-ci.org' in x['target_url']:
                has_travis = True
                continue
            if 'shippable.com' in x['target_url']:
                has_shippable = True
                continue

    # we don't like @you in the commit messages
    # https://github.com/ansible/ansibullbot/issues/375
    for x in iw.commits:
        words = x.commit.message.split()
        if not words:
            continue
        if [x for x in words if x.startswith('@') and not x.endswith('@')]:
            has_commit_mention = True
            needs_revision = True
            needs_revision_msgs.append('@ in commit message')
            break
    # make sure they're notified about the problem
    if has_commit_mention:
        if 'commit_msg_mentions' in iw.history.get_boilerplate_comments():
            has_commit_mention_notification = True
        #import epdb; epdb.st()

    if has_travis:
        needs_rebase = True
        needs_rebase_msgs.append('travis-ci found in status')

        # 'has_travis_notification': has_travis_notification,
        if 'travis_notify' in iw.history.get_boilerplate_comments():
            has_travis_notification = True
        else:
            has_travis_notification = False

    logging.info('mergeable_state is %s' % mstate)
    logging.info('needs_rebase is %s' % needs_rebase)
    logging.info('needs_revision is %s' % needs_revision)
    logging.info('ready_for_review is %s' % ready_for_review)

    # Scrape web data for debug purposes
    rfn = iw.repo_full_name
    www_summary = triager.gws.get_single_issue_summary(rfn, iw.number)
    www_reviews = triager.gws.scrape_pullrequest_review(rfn, iw.number)

    rmeta = {
        'committer_count': committer_count,
        'is_needs_revision': needs_revision,
        'is_needs_revision_msgs': needs_revision_msgs,
        'is_needs_rebase': needs_rebase,
        'is_needs_rebase_msgs': needs_rebase_msgs,
        'has_shippable': has_shippable,
        'has_landscape': has_landscape,
        'has_travis': has_travis,
        'has_travis_notification': has_travis_notification,
        'has_commit_mention': has_commit_mention,
        'has_commit_mention_notification': has_commit_mention_notification,
        'merge_commits': merge_commits,
        'has_merge_commit_notification': has_merge_commit_notification,
        'mergeable': iw.pullrequest.mergeable,
        'mergeable_state': mstate,
        'change_requested': change_requested,
        'ci_state': ci_state,
        'reviews': iw.reviews,
        'www_summary': www_summary,
        'www_reviews': www_reviews,
        'ready_for_review': ready_for_review
    }

    return rmeta
