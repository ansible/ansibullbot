#!/usr/bin/env python

import datetime
import logging
import os
import pytz

from ansibullbot.triagers.plugins.shipit import is_approval
from ansibullbot.utils.shippable_api import has_commentable_data
from ansibullbot.utils.shippable_api import ShippableRuns
from ansibullbot.wrappers.historywrapper import ShippableHistory


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
    ci_stale = None
    mstate = None
    change_requested = None
    ready_for_review = None
    has_commit_mention = False
    has_commit_mention_notification = False

    has_shippable_yaml = None
    has_shippable_yaml_notification = None

    has_remote_repo = None

    user_reviews = None
    stale_reviews = {}

    # https://github.com/ansible/ansibullbot/issues/302
    has_multiple_modules = False
    needs_multiple_new_modules_notification = False

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
        'ci_stale': ci_stale,
        'reviews': None,
        #'www_reviews': None,
        #'www_summary': None,
        'ready_for_review': ready_for_review,
        'has_shippable_yaml': has_shippable_yaml,
        'has_shippable_yaml_notification': has_shippable_yaml_notification,
        'has_remote_repo': has_remote_repo,
        'stale_reviews': stale_reviews,
        'has_multiple_modules': has_multiple_modules,
        'needs_multiple_new_modules_notification': needs_multiple_new_modules_notification
    }

    if not iw.is_pullrequest():
        return rmeta

    bpcs = iw.history.get_boilerplate_comments()
    bpcs = [x[0] for x in bpcs]

    # Scrape web data for debug purposes
    #rfn = iw.repo_full_name
    #www_summary = triager.gws.get_single_issue_summary(rfn, iw.number)
    #www_reviews = triager.gws.scrape_pullrequest_review(rfn, iw.number)

    maintainers = [x for x in triager.ansible_core_team
                   if x not in triager.BOTNAMES]

    #if meta.get('module_match'):
    #    maintainers += meta['module_match'].get('maintainers', [])
    maintainers += meta.get('component_maintainers', [])

    # get the exact state from shippable ...
    #   success/pending/failure/... ?
    ci_status = iw.pullrequest_status

    # code quality hooks
    if [x for x in ci_status if isinstance(x, dict) and
            'landscape.io' in x['target_url']]:
        has_landscape = True

    ci_states = [x['state'] for x in ci_status
                 if isinstance(x, dict) and 'shippable.com' in x['target_url']]

    if not ci_states:
        ci_state = None
    else:
        ci_state = ci_states[0]
    logging.info('ci_state == %s' % ci_state)

    # https://github.com/ansible/ansibullbot/issues/458
    ci_dates = [x['created_at'] for x in ci_status]
    ci_dates = sorted(set(ci_dates))
    if ci_dates:
        last_ci_date = ci_dates[-1]
        last_ci_date = datetime.datetime.strptime(last_ci_date, '%Y-%m-%dT%H:%M:%SZ')
        ci_delta = (datetime.datetime.now() - last_ci_date).days
        if ci_delta > 7:
            ci_stale = True
        else:
            ci_stale = False
    else:
        ci_stale = False

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
        shipits = {}  # key: actor, value: created_at

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

                    if is_approval(event['body']):
                        shipits[event['actor']] = event['created_at']

                    if '!needs_revision' in event['body']:
                        needs_revision = False
                        needs_revision_msgs.append(
                            '[%s] !needs_revision' % event['actor']
                        )
                        continue

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
                        if ready_for_review is None or event['created_at'] > ready_for_review:
                            ready_for_review = event['created_at']
                        needs_revision = False
                        needs_revision_msgs.append(
                            '[%s] ready_for_review' % event['actor']
                        )
                        continue
                    if 'shipit' in event['body'].lower():
                        #ready_for_review = True
                        if ready_for_review is None or event['created_at'] > ready_for_review:
                            ready_for_review = event['created_at']
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
            store=True
        )

        if user_reviews:
            last_commit = iw.commits[-1].sha
            change_requested = changes_requested_by(user_reviews, shipits, last_commit, ready_for_review)
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

        if 'merge_commit_notify' not in bpcs:
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
        if 'commit_msg_mentions' in bpcs:
            has_commit_mention_notification = True

    if has_travis:
        needs_rebase = True
        needs_rebase_msgs.append('travis-ci found in status')

        # 'has_travis_notification': has_travis_notification,
        if 'travis_notify' in bpcs:
            has_travis_notification = True
        else:
            has_travis_notification = False

    # keep track of who deleted their repo/branch
    if iw.pullrequest.head.repo:
        has_remote_repo = True
    else:
        has_remote_repo = False

    # https://github.com/ansible/ansibullbot/issues/406
    has_shippable_yaml = iw.pullrequest_filepath_exists('shippable.yml')
    if not has_shippable_yaml:
        needs_rebase = True
        needs_rebase_msgs.append('missing shippable.yml')
        if 'no_shippable_yaml' in bpcs:
            has_shippable_yaml_notification = True
        else:
            has_shippable_yaml_notification = False

    # stale reviews
    if user_reviews:

        now = pytz.utc.localize(datetime.datetime.now())
        commits = [x for x in iw.history.history if x['event'] == 'committed']
        lc_date = commits[-1]['created_at']

        stale_reviews = {}
        for actor, review in user_reviews.items():
            if review['state'] != 'CHANGES_REQUESTED':
                continue
            lrd = None
            for x in iw.history.history:
                if x['actor'] != actor:
                    continue
                if x['event'] == 'review_changes_requested':
                    if not lrd or lrd < x['created_at']:
                        lrd = x['created_at']
                elif x['event'] == 'commented' and is_approval(x['body']):
                    if lrd and lrd < x['created_at']:
                        lrd = None

            if lrd:

                age = (now - lc_date).days
                delta = (lc_date - lrd).days
                if (lc_date > lrd) and (age > 7):
                    stale_reviews[actor] = {
                        'age': age,
                        'delta': delta,
                        'review_date': lrd.isoformat(),
                        'commit_date': lc_date.isoformat()
                    }

    # https://github.com/ansible/ansibullbot/issues/302
    if len(iw.new_modules) > 1:
        has_multiple_modules = True
        if 'multiple_module_notify' not in bpcs:
            needs_multiple_new_modules_notification = True
        needs_revision = True
        needs_revision_msgs.append('multiple new modules')

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
        'ci_stale': ci_stale,
        'reviews': iw.reviews,
        #'www_summary': www_summary,
        #'www_reviews': www_reviews,
        'ready_for_review_date': ready_for_review,
        'ready_for_review': bool(ready_for_review),
        'has_shippable_yaml': has_shippable_yaml,
        'has_shippable_yaml_notification': has_shippable_yaml_notification,
        'has_remote_repo': has_remote_repo,
        'stale_reviews': stale_reviews,
        'has_multiple_modules': has_multiple_modules,
        'needs_multiple_new_modules_notification': needs_multiple_new_modules_notification
    }
    if rmeta['ready_for_review_date']:
        rmeta['ready_for_review_date'] = rmeta['ready_for_review_date'].isoformat()

    return rmeta


def changes_requested_by(user_reviews, shipits, last_commit, ready_for_review):
    outstanding = set()
    for actor, review in user_reviews.items():
        if review['state'] == 'CHANGES_REQUESTED':
            if actor in shipits:
                review_time = datetime.datetime.strptime(review['submitted_at'], '%Y-%m-%dT%H:%M:%SZ')
                review_time = pytz.utc.localize(review_time)
                shipit_time = shipits[actor]
                if review_time < shipit_time:
                    # ignore review older than shipit
                    # https://github.com/ansible/ansibullbot/issues/671
                    continue

            if ready_for_review:
                review_time = datetime.datetime.strptime(review['submitted_at'], '%Y-%m-%dT%H:%M:%SZ')
                review_time = pytz.utc.localize(review_time)
                if review['commit_id'] != last_commit and review_time < ready_for_review:
                    # ignore review older than ready_for_review comment wrote by submitter
                    # but only if the pull request has been updated (meaning the
                    # last commit isn't the reviewed commit).
                    continue

            outstanding.add(actor)
        elif review['state'] not in ['APPROVED', 'COMMENTED']:
            logging.error('breakpoint!')
            print('%s unhandled' % review['state'])
            import epdb; epdb.st()
    return list(outstanding)


def get_review_state(reviews, submitter, number=None, store=False):
    '''Calculate the final review state for each reviewer'''

    # final review state for each reviewer
    user_reviews = {}

    for review in reviews:
        actor = review['user']['login']

        if actor != submitter:

            if actor not in user_reviews:
                user_reviews[actor] = {}

            state = review['state']
            submitted_at = review['submitted_at']
            commit_id = review['commit_id']

            if state in ['CHANGES_REQUESTED', 'APPROVED']:
                user_reviews[actor]['state'] = state
                user_reviews[actor]['submitted_at'] = submitted_at
                user_reviews[actor]['commit_id'] = commit_id

            elif state == 'COMMENTED':
                # comments do not override change requests
                if user_reviews[actor].get('state') != 'CHANGES_REQUESTED':
                    user_reviews[actor]['state'] = state
                    user_reviews[actor]['submitted_at'] = submitted_at
                    user_reviews[actor]['commit_id'] = commit_id

            elif state == 'DISMISSED':
                # a dismissed review 'magically' turns into a comment
                user_reviews[actor]['state'] = 'COMMENTED'
                user_reviews[actor]['submitted_at'] = submitted_at
                user_reviews[actor]['commit_id'] = commit_id

            elif state == 'PENDING':
                pass

            else:
                logging.error('breakpoint!')
                print('%s not handled yet' % state)
                import epdb; epdb.st()
                pass

    return user_reviews


def get_shippable_run_facts(iw, meta, shippable=None):
    '''Does an issue need the test result comment?'''

    # https://github.com/ansible/ansibullbot/issues/312
    # https://github.com/ansible/ansibullbot/issues/404
    # https://github.com/ansible/ansibullbot/issues/418

    rmeta = {
        'shippable_test_results': None,
        'ci_verified': None,
        'needs_testresult_notification': None
    }

    # should only be here if the run state is failed ...
    if not meta['has_shippable']:
        return rmeta
    if meta['ci_state'] != 'failure':
        return rmeta

    if not shippable:
        spath = os.path.expanduser('~/.ansibullbot/cache/shippable.runs')
        shippable = ShippableRuns(cachedir=spath, writecache=True)

    ci_status = iw.pullrequest_status
    ci_verified = None
    shippable_test_results = None
    needs_testresult_notification = False

    # find the last chronological run id
    #   https://app.shippable.com/github/ansible/ansible/runs/21001/summary
    #   https://app.shippable.com/github/ansible/ansible/runs/21001
    last_run = [x['target_url'] for x in ci_status][0]
    last_run = last_run.split('/')
    if last_run[-1] == 'summary':
        last_run = last_run[-2]
    else:
        last_run = last_run[-1]

    # filter by the last run id
    (run_data, commitSha, shippable_test_results, ci_verified) = \
        shippable.get_test_results(
            last_run,
            usecache=True,
            filter_paths=['/testresults/ansible-test-.*.json'],
    )

    # do validation so that we're not stepping on toes
    if 'ci_verified' in iw.labels and not ci_verified:

        sh = ShippableHistory(iw, shippable, ci_status)
        vinfo = sh.info_for_last_ci_verified_run()

        if vinfo:
            if last_run == vinfo['run_id']:
                ci_verified = True
            else:
                #logging.error('breakpoint!')
                #import epdb; epdb.st()
                pass

    # no results means no notification required
    if len(shippable_test_results) < 1:
        needs_testresult_notification = False
    else:

        s_bpcs = iw.history.get_boilerplate_comments_content(
            bfilter='shippable_test_result'
        )

        if s_bpcs:
            # was this specific result shown?
            job_ids = [x['job_id'] for x in shippable_test_results]
            job_ids = sorted(set(job_ids))
            found = []
            for bp in s_bpcs:
                for job_id in [x for x in job_ids if x not in found]:
                    if job_id in bp and job_id not in found:
                        found.append(job_id)
            if len(found) == len(job_ids):
                needs_testresult_notification = False
            else:
                needs_testresult_notification = True
        else:
            needs_testresult_notification = True

    # https://github.com/ansible/ansibullbot/issues/421
    if rmeta['needs_testresult_notification']:
        hcd = has_commentable_data(shippable_test_results)
        rmeta['needs_testresult_notification'] = hcd

    rmeta = {
        'shippable_test_results': shippable_test_results,
        'ci_verified': ci_verified,
        'needs_testresult_notification': needs_testresult_notification
    }

    return rmeta
