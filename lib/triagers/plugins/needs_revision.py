#!/usr/bin/env python

import json
import logging
import os
from pprint import pprint


def get_needs_revision_facts(triager, issuewrapper, meta, shippable=None):
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
    needs_testresult_notification = False
    shippable_test_results = None

    rmeta = {
        'committer_count': committer_count,
        'is_needs_revision': needs_revision,
        'is_needs_revision_msgs': needs_revision_msgs,
        'is_needs_rebase': needs_rebase,
        'is_needs_rebase_msgs': needs_rebase_msgs,
        'has_commit_mention': has_commit_mention,
        'has_commit_mention_notification': has_commit_mention_notification,
        'has_shippable': has_shippable,
        'shippable_test_results': shippable_test_results,
        'has_landscape': has_landscape,
        'has_travis': has_travis,
        'has_travis_notification': has_travis_notification,
        'needs_testresult_notification': needs_testresult_notification,
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

    # Scrape web data for debug purposes
    rfn = iw.repo_full_name
    www_summary = triager.gws.get_single_issue_summary(rfn, iw.number)
    www_reviews = triager.gws.scrape_pullrequest_review(rfn, iw.number)

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

        #current_hash = None
        #pending_reviews = []
        #hash_reviews = {}
        user_reviews = {}

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

        # This is a complicated algo ... sigh
        user_reviews = get_review_state(
            iw.reviews,
            iw.submitter,
            number=iw.number,
            www_validate=None,
            store=True
        )

        if user_reviews:
            change_requested = changes_requested_by(user_reviews)
            if change_requested:
                needs_revision = True
                needs_revision_msgs.append(
                    'outstanding reviews: %s' % ','.join(change_requested)
                )
        #import pprint; pprint.pprint(www_reviews)
        #import pprint; pprint.pprint(change_requested)
        #import epdb; epdb.st()

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

    # test failure comments
    # https://github.com/ansible/ansibullbot/issues/404
    if has_shippable and ci_state == 'failure':
        (shippable_test_results, needs_testresult_notification) = \
            needs_shippable_test_results_notification(shippable, ci_status, iw)

        '''
        # FIXME - make the return structure simpler.
        last_run = [x['target_url'] for x in ci_status][0]
        last_run = last_run.split('/')[-1]

        s_results = shippable.get_test_results(
            last_run,
            usecache=True,
            filter_paths=['/testresults.json'],
            filter_classes=['sanity']
        )

        if len(s_results) < 1:
            needs_testresult_notification = False
        else:
            shippable_test_results = s_results[0]['testresults']

            bpcs = iw.history.get_boilerplate_comments_content(
                bfilter='shippable_test_result'
            )
            if bpcs:
                # was this specific result shown?
                exp = [x['job_url'] for x in shippable_test_results]
                found = []
                for ex in exp:
                    for bp in bpcs:
                        if ex in bp:
                            if ex not in found:
                                found.append(ex)
                            break
                if len(found) == len(exp):
                    needs_testresult_notification = False
                else:
                    needs_testresult_notification = True
            else:
                needs_testresult_notification = True
        '''

    logging.info('mergeable_state is %s' % mstate)
    logging.info('needs_rebase is %s' % needs_rebase)
    logging.info('needs_revision is %s' % needs_revision)
    logging.info('ready_for_review is %s' % ready_for_review)

    rmeta = {
        'committer_count': committer_count,
        'is_needs_revision': needs_revision,
        'is_needs_revision_msgs': needs_revision_msgs,
        'is_needs_rebase': needs_rebase,
        'is_needs_rebase_msgs': needs_rebase_msgs,
        'has_shippable': has_shippable,
        'shippable_test_results': shippable_test_results,
        'has_landscape': has_landscape,
        'has_travis': has_travis,
        'has_travis_notification': has_travis_notification,
        'needs_testresult_notification': needs_testresult_notification,
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


def changes_requested_by(user_reviews):
    outstanding = []
    for k,v in user_reviews.items():
        if v == 'CHANGES_REQUESTED':
            if k not in outstanding:
                outstanding.append(k)
        elif v not in ['APPROVED', 'COMMENTED']:
            logging.error('breakpoint!')
            print('%s unhandled' % v)
            import epdb; epdb.st()
    return outstanding


def get_review_state(reviews, submitter, number=None, www_validate=None,
                     store=False):
    '''Calculate the final review state for each reviewer'''

    # final review state for each reviewer
    user_reviews = {}

    for review in reviews:
        actor = review['user']['login']
        state = review['state']

        if actor != submitter:

            if state in ['CHANGES_REQUESTED', 'APPROVED']:
                user_reviews[actor] = state

            elif state == 'COMMENTED':
                # comments do not override change requests
                if actor in user_reviews:
                    if user_reviews[actor] == 'CHANGES_REQUESTED':
                        pass
                else:
                    user_reviews[actor] = state

            elif state == 'DISMISSED':
                # a dismissed review 'magically' turns into a comment
                user_reviews[actor] = 'COMMENTED'

            else:
                logging.error('breakpoint!')
                print('%s not handled yet' % state)
                import epdb; epdb.st()
                pass

    if www_validate:

        # translation table for www scraped reviews
        TMAP = {
            'approved these changes': 'APPROVED',
            'left review comments': 'COMMENTED',
            'requested changes': 'CHANGES_REQUESTED',
        }

        translated = {}

        for k,v in www_validate['users'].iteritems():
            if v in TMAP:
                translated[k] = TMAP[v]
            else:
                logging.error('breakpoint!')
                print('no mapping for %s' % v)
                import epdb; epdb.st()

        if user_reviews != translated:
            pprint(translated)
            pprint(user_reviews)
            logging.error('breakpoint!')
            print('calculated != scraped')
            import epdb; epdb.st()

        if store and number:
            dfile = os.path.join('/tmp/reviews', '%s.json' % number)
            ddata = {
                'submitter': submitter,
                'api_reviews': reviews[:],
                'user_reviews': user_reviews.copy(),
                'www_reviews': www_validate.copy(),
                'www_translated': translated.copy(),
                'matches': user_reviews == translated
            }
            with open(dfile, 'wb') as f:
                f.write(json.dumps(ddata, indent=2, sort_keys=True))

    return user_reviews


def needs_shippable_test_results_notification(shippable, ci_status, iw):
    '''Does an issue need the test result comment?'''

    shippable_test_results = None
    needs_testresult_notification = False

    # find the last chronological run id
    last_run = [x['target_url'] for x in ci_status][0]
    last_run = last_run.split('/')[-1]

    # filter by the last run id
    shippable_test_results = shippable.get_test_results(
        last_run,
        usecache=True,
        filter_paths=['/testresults/ansible-test-.*.json'],
    )
    # always 1 element?
    if shippable_test_results:
        shippable_test_results = shippable_test_results[0]

    # no results means no notification required
    if len(shippable_test_results) < 1:
        needs_testresult_notification = False
    else:

        bpcs = iw.history.get_boilerplate_comments_content(
            bfilter='shippable_test_result'
        )
        if bpcs:
            # was this specific result shown?
            job_id = shippable_test_results['job_id']
            found = False
            for bp in bpcs:
                if job_id in bp:
                    found = True
                    break
            if found:
                needs_testresult_notification = False
            else:
                needs_testresult_notification = True
        else:
            needs_testresult_notification = True

    return (shippable_test_results, needs_testresult_notification)
