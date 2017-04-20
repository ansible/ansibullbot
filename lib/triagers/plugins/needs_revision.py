#!/usr/bin/env python

import datetime
import json
import logging
import os
from pprint import pprint

from lib.utils.shippable_api import ShippableRuns
from lib.wrappers.historywrapper import ShippableHistory


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
        'www_reviews': None,
        'www_summary': None,
        'ready_for_review': ready_for_review,
        'has_shippable_yaml': has_shippable_yaml,
        'has_shippable_yaml_notification': has_shippable_yaml_notification,
        'has_remote_repo': has_remote_repo
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

    if has_travis:
        needs_rebase = True
        needs_rebase_msgs.append('travis-ci found in status')

        # 'has_travis_notification': has_travis_notification,
        if 'travis_notify' in iw.history.get_boilerplate_comments():
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
        if 'no_shippable_yaml' in iw.history.get_boilerplate_comments():
            has_shippable_yaml_notification = True
        else:
            has_shippable_yaml_notification = False

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
        'www_summary': www_summary,
        'www_reviews': www_reviews,
        'ready_for_review': ready_for_review,
        'has_shippable_yaml': has_shippable_yaml,
        'has_shippable_yaml_notification': has_shippable_yaml_notification,
        'has_remote_repo': has_remote_repo
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


#def get_shippable_run_facts(shippable, ci_status, iw):
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
    last_run = [x['target_url'] for x in ci_status][0]
    last_run = last_run.split('/')[-1]

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

        bpcs = iw.history.get_boilerplate_comments_content(
            bfilter='shippable_test_result'
        )
        if bpcs:
            # was this specific result shown?
            job_ids = [x['job_id'] for x in shippable_test_results]
            job_ids = sorted(set(job_ids))
            found = []
            for bp in bpcs:
                for job_id in [x for x in job_ids if x not in found]:
                    if job_id in bp and job_id not in found:
                        found.append(job_id)
            if len(found) == len(job_ids):
                needs_testresult_notification = False
            else:
                needs_testresult_notification = True
        else:
            needs_testresult_notification = True

    rmeta = {
        'shippable_test_results': shippable_test_results,
        'ci_verified': ci_verified,
        'needs_testresult_notification': needs_testresult_notification
    }

    return rmeta
