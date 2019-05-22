#!/usr/bin/env python

import datetime
import logging
import os

import pytz

from ansibullbot._text_compat import to_text
from ansibullbot.triagers.plugins.shipit import is_approval
from ansibullbot.utils.shippable_api import has_commentable_data
from ansibullbot.utils.shippable_api import ShippableRuns
from ansibullbot.wrappers.historywrapper import ShippableHistory
from ansibullbot.utils.shippable_api import ShippableNoData

import ansibullbot.constants as C


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
    has_zuul = False
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
        u'committer_count': committer_count,
        u'is_needs_revision': needs_revision,
        u'is_needs_revision_msgs': needs_revision_msgs,
        u'is_needs_rebase': needs_rebase,
        u'is_needs_rebase_msgs': needs_rebase_msgs,
        u'has_commit_mention': has_commit_mention,
        u'has_commit_mention_notification': has_commit_mention_notification,
        u'has_shippable': has_shippable,
        u'has_landscape': has_landscape,
        u'has_travis': has_travis,
        u'has_travis_notification': has_travis_notification,
        u'has_zuul': has_zuul,
        u'merge_commits': merge_commits,
        u'has_merge_commit_notification': has_merge_commit_notification,
        u'mergeable': None,
        u'mergeable_state': mstate,
        u'change_requested': change_requested,
        u'ci_state': ci_state,
        u'ci_stale': ci_stale,
        u'reviews': None,
        #'www_reviews': None,
        #'www_summary': None,
        u'ready_for_review': ready_for_review,
        u'has_shippable_yaml': has_shippable_yaml,
        u'has_shippable_yaml_notification': has_shippable_yaml_notification,
        u'has_remote_repo': has_remote_repo,
        u'stale_reviews': stale_reviews,
        u'has_multiple_modules': has_multiple_modules,
        u'needs_multiple_new_modules_notification': needs_multiple_new_modules_notification
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
    maintainers += meta.get(u'component_maintainers', [])

    # get the exact state from shippable ...
    #   success/pending/failure/... ?
    ci_status = iw.pullrequest_status

    # check if this has shippable and or travis
    if ci_status:
        for x in ci_status:
            if u'travis-ci.org' in x[u'target_url']:
                has_travis = True
                continue
            if x.get('context') == 'Shippable':
                has_shippable = True
                continue

    # code quality hooks
    if [x for x in ci_status if isinstance(x, dict) and
            u'landscape.io' in x[u'target_url']]:
        has_landscape = True

    if [x for x in ci_status if isinstance(x, dict) and
            u'zuul' in x[u'target_url']]:
        has_zuul = True

    ci_states = [x[u'state'] for x in ci_status
                 if isinstance(x, dict) and x.get('context') == 'Shippable']

    if not ci_states:
        ci_state = None
    else:
        ci_state = ci_states[0]
    logging.info(u'ci_state == %s' % ci_state)

    # decide if the CI run is "stale"
    if not has_shippable:
        ci_stale = True
    else:
        # https://github.com/ansible/ansibullbot/issues/935
        shippable_states = [x for x in ci_status
                            if isinstance(x, dict) and x.get('context') == 'Shippable']
        ci_date = get_last_shippable_full_run_date(shippable_states, shippable)

        # https://github.com/ansible/ansibullbot/issues/458
        if ci_date:
            ci_date = datetime.datetime.strptime(ci_date, u'%Y-%m-%dT%H:%M:%S.%fZ')
            ci_delta = (datetime.datetime.now() - ci_date).days
            if ci_delta > 7:
                ci_stale = True
            else:
                ci_stale = False
        else:
            ci_stale = False

    # clean/unstable/dirty/unknown
    mstate = iw.mergeable_state
    if not mstate:
        mstate = u'unknown'
    logging.info(u'mergeable_state == %s' % mstate)

    # clean/unstable/dirty/unknown
    if mstate != u'clean':

        if ci_state == u'failure':
            needs_revision = True
            needs_revision_msgs.append(u'ci failure')

        if mstate == u'dirty':
            needs_revision = True
            needs_rebase = True
            needs_revision_msgs.append(u'mergeable state is dirty')
            needs_rebase_msgs.append(u'mergeable state is dirty')

        elif mstate == u'unknown':
            # if tests are still running, this needs to be ignored.
            if ci_state not in [u'pending']:
                needs_revision = True
                needs_revision_msgs.append(u'mergeable state is unknown')
                needs_rebase = True
                needs_rebase_msgs.append(u'mergeable state is unknown')

        elif mstate == u'unstable':
            # reduce the label churn
            if ci_state == u'pending' and u'needs_revision' in iw.labels:
                needs_revision = True
                needs_rebase_msgs.append(u'keep label till test finished')

    else:

        #current_hash = None
        #pending_reviews = []
        #hash_reviews = {}
        user_reviews = {}
        shipits = {}  # key: actor, value: created_at

        has_set_needs_revision = set()

        for event in iw.history.history:

            if event[u'actor'] in triager.BOTNAMES:
                continue

            if event[u'actor'] in maintainers and \
                    event[u'actor'] != iw.submitter:

                if event[u'event'] == u'labeled':
                    if event[u'label'] == u'needs_revision':
                        needs_revision = True
                        needs_revision_msgs.append(
                            u'[%s] labeled' % event[u'actor']
                        )
                        has_set_needs_revision.add(event[u'actor'])
                        continue

                if event[u'event'] == u'unlabeled':
                    if event[u'label'] == u'needs_revision':
                        needs_revision = False
                        needs_revision_msgs.append(
                            u'[%s] unlabeled' % event[u'actor']
                        )
                        continue

                if event[u'event'] == u'commented':

                    if is_approval(event[u'body']):
                        shipits[event[u'actor']] = event[u'created_at']

                    if u'!needs_revision' in event[u'body']:
                        needs_revision = False
                        needs_revision_msgs.append(
                            u'[%s] !needs_revision' % event[u'actor']
                        )
                        continue

                    if u'needs_revision' in event[u'body'] and \
                            u'!needs_revision' not in event[u'body']:
                        needs_revision = True
                        needs_revision_msgs.append(
                            u'[%s] needs_revision' % event[u'actor']
                        )
                        has_set_needs_revision.add(event[u'actor'])
                        continue

                    if u'shipit' in event[u'body'].lower():
                        if event[u'actor'] in has_set_needs_revision:
                            has_set_needs_revision.remove(event[u'actor'])
                            if not has_set_needs_revision:
                                needs_revision = False
                                continue

            if event[u'actor'] == iw.submitter:
                if event[u'event'] == u'commented':
                    if u'ready_for_review' in event[u'body']:
                        if ready_for_review is None or event[u'created_at'] > ready_for_review:
                            ready_for_review = event[u'created_at']
                        needs_revision = False
                        needs_revision_msgs.append(
                            u'[%s] ready_for_review' % event[u'actor']
                        )
                        continue
                    if u'shipit' in event[u'body'].lower():
                        #ready_for_review = True
                        if ready_for_review is None or event[u'created_at'] > ready_for_review:
                            ready_for_review = event[u'created_at']
                        needs_revision = False
                        needs_revision_msgs.append(
                            u'[%s] shipit' % event[u'actor']
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
                    u'outstanding reviews: %s' % u','.join(change_requested)
                )

    # Merge commits are bad, force a rebase
    if iw.merge_commits:
        needs_rebase = True

        for mc in iw.merge_commits:
            merge_commits.append(mc.html_url)
            needs_rebase_msgs.append(u'merge commit %s' % mc.commit.sha)

        if u'merge_commit_notify' not in bpcs:
            has_merge_commit_notification = False
        else:
            mc_comments = iw.history.search_user_comments(
                triager.BOTNAMES,
                u'boilerplate: merge_commit_notify'
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

    # we don't like @you in the commit messages
    # https://github.com/ansible/ansibullbot/issues/375
    for x in iw.commits:
        words = x.commit.message.split()
        if not words:
            continue
        if [x for x in words if x.startswith(u'@') and not x.endswith(u'@')]:
            has_commit_mention = True
            needs_revision = True
            needs_revision_msgs.append(u'@ in commit message')
            break

    # make sure they're notified about the problem
    if has_commit_mention:
        if u'commit_msg_mentions' in bpcs:
            has_commit_mention_notification = True

    if has_travis:
        needs_rebase = True
        needs_rebase_msgs.append(u'travis-ci found in status')

        # 'has_travis_notification': has_travis_notification,
        if u'travis_notify' in bpcs:
            has_travis_notification = True
        else:
            has_travis_notification = False

    # keep track of who deleted their repo/branch
    if iw.pullrequest.head.repo:
        has_remote_repo = True
    else:
        has_remote_repo = False

    # https://github.com/ansible/ansibullbot/issues/406
    has_shippable_yaml = iw.pullrequest_filepath_exists(u'shippable.yml')
    if not has_shippable_yaml:
        needs_rebase = True
        needs_rebase_msgs.append(u'missing shippable.yml')
        if u'no_shippable_yaml' in bpcs:
            has_shippable_yaml_notification = True
        else:
            has_shippable_yaml_notification = False

    # stale reviews
    if user_reviews:

        now = pytz.utc.localize(datetime.datetime.now())
        commits = [x for x in iw.history.history if x[u'event'] == u'committed']
        lc_date = commits[-1][u'created_at']

        stale_reviews = {}
        for actor, review in user_reviews.items():
            if review[u'state'] != u'CHANGES_REQUESTED':
                continue
            lrd = None
            for x in iw.history.history:
                if x[u'actor'] != actor:
                    continue
                if x[u'event'] == u'review_changes_requested':
                    if not lrd or lrd < x[u'created_at']:
                        lrd = x[u'created_at']
                elif x[u'event'] == u'commented' and is_approval(x[u'body']):
                    if lrd and lrd < x[u'created_at']:
                        lrd = None

            if lrd:

                age = (now - lc_date).days
                delta = (lc_date - lrd).days
                if (lc_date > lrd) and (age > 7):
                    stale_reviews[actor] = {
                        u'age': age,
                        u'delta': delta,
                        u'review_date': lrd.isoformat(),
                        u'commit_date': lc_date.isoformat()
                    }

    # https://github.com/ansible/ansibullbot/issues/302
    if len(iw.new_modules) > 1:
        has_multiple_modules = True
        if u'multiple_module_notify' not in bpcs:
            needs_multiple_new_modules_notification = True
        needs_revision = True
        needs_revision_msgs.append(u'multiple new modules')

    logging.info(u'mergeable_state is %s' % mstate)
    logging.info(u'needs_rebase is %s' % needs_rebase)
    logging.info(u'needs_revision is %s' % needs_revision)
    logging.info(u'ready_for_review is %s' % ready_for_review)

    rmeta = {
        u'committer_count': committer_count,
        u'is_needs_revision': needs_revision,
        u'is_needs_revision_msgs': needs_revision_msgs,
        u'is_needs_rebase': needs_rebase,
        u'is_needs_rebase_msgs': needs_rebase_msgs,
        u'has_shippable': has_shippable,
        u'has_landscape': has_landscape,
        u'has_travis': has_travis,
        u'has_travis_notification': has_travis_notification,
        u'has_commit_mention': has_commit_mention,
        u'has_commit_mention_notification': has_commit_mention_notification,
        u'merge_commits': merge_commits,
        u'has_merge_commit_notification': has_merge_commit_notification,
        u'mergeable': iw.pullrequest.mergeable,
        u'mergeable_state': mstate,
        u'change_requested': change_requested,
        u'ci_state': ci_state,
        u'ci_stale': ci_stale,
        u'reviews': iw.reviews,
        #'www_summary': www_summary,
        #'www_reviews': www_reviews,
        u'ready_for_review_date': ready_for_review,
        u'ready_for_review': bool(ready_for_review),
        u'has_shippable_yaml': has_shippable_yaml,
        u'has_shippable_yaml_notification': has_shippable_yaml_notification,
        u'has_remote_repo': has_remote_repo,
        u'stale_reviews': stale_reviews,
        u'has_multiple_modules': has_multiple_modules,
        u'needs_multiple_new_modules_notification': needs_multiple_new_modules_notification
    }
    if rmeta[u'ready_for_review_date']:
        rmeta[u'ready_for_review_date'] = rmeta[u'ready_for_review_date'].isoformat()

    return rmeta


def changes_requested_by(user_reviews, shipits, last_commit, ready_for_review):
    outstanding = set()
    for actor, review in user_reviews.items():
        if review[u'state'] == u'CHANGES_REQUESTED':
            if actor in shipits:
                review_time = datetime.datetime.strptime(review[u'submitted_at'], u'%Y-%m-%dT%H:%M:%SZ')
                review_time = pytz.utc.localize(review_time)
                shipit_time = shipits[actor]
                if review_time < shipit_time:
                    # ignore review older than shipit
                    # https://github.com/ansible/ansibullbot/issues/671
                    continue

            if ready_for_review:
                review_time = datetime.datetime.strptime(review[u'submitted_at'], u'%Y-%m-%dT%H:%M:%SZ')
                review_time = pytz.utc.localize(review_time)
                if review[u'commit_id'] != last_commit and review_time < ready_for_review:
                    # ignore review older than ready_for_review comment wrote by submitter
                    # but only if the pull request has been updated (meaning the
                    # last commit isn't the reviewed commit).
                    continue

            outstanding.add(actor)
        elif review[u'state'] not in [u'APPROVED', u'COMMENTED']:
            logging.error(u'%s unhandled' % review[u'state'])
            if C.DEFAULT_BREAKPOINTS:
                logging.error(u'breakpoint!')
                import epdb; epdb.st()
    return list(outstanding)


def get_review_state(reviews, submitter, number=None, store=False):
    '''Calculate the final review state for each reviewer'''

    # final review state for each reviewer
    user_reviews = {}

    for review in reviews:
        actor = review[u'user'][u'login']

        if actor != submitter:

            if actor not in user_reviews:
                user_reviews[actor] = {}

            state = review[u'state']
            submitted_at = review[u'submitted_at']
            if u'commit_id' in review:
                commit_id = review[u'commit_id']
            else:
                commit_id = None

            if state in [u'CHANGES_REQUESTED', u'APPROVED']:
                user_reviews[actor][u'state'] = state
                user_reviews[actor][u'submitted_at'] = submitted_at
                user_reviews[actor][u'commit_id'] = commit_id

            elif state == u'COMMENTED':
                # comments do not override change requests
                if user_reviews[actor].get(u'state') != u'CHANGES_REQUESTED':
                    user_reviews[actor][u'state'] = state
                    user_reviews[actor][u'submitted_at'] = submitted_at
                    user_reviews[actor][u'commit_id'] = commit_id

            elif state == u'DISMISSED':
                # a dismissed review 'magically' turns into a comment
                user_reviews[actor][u'state'] = u'COMMENTED'
                user_reviews[actor][u'submitted_at'] = submitted_at
                user_reviews[actor][u'commit_id'] = commit_id

            elif state == u'PENDING':
                pass

            else:
                logging.error(u'%s not handled yet' % state)
                if C.DEFAULT_BREAKPOINTS:
                    logging.error(u'breakpoint!')
                    import epdb; epdb.st()

    return user_reviews


def get_shippable_run_facts(iw, meta, shippable=None):
    '''Does an issue need the test result comment?'''

    # https://github.com/ansible/ansibullbot/issues/312
    # https://github.com/ansible/ansibullbot/issues/404
    # https://github.com/ansible/ansibullbot/issues/418

    rmeta = {
        u'shippable_test_results': None,
        u'ci_verified': None,
        u'needs_testresult_notification': None
    }

    # should only be here if the run state is failed ...
    if not meta[u'has_shippable']:
        return rmeta
    if meta[u'ci_state'] != u'failure':
        return rmeta

    if not shippable:
        spath = os.path.expanduser(u'~/.ansibullbot/cache/shippable.runs')
        shippable = ShippableRuns(cachedir=spath, writecache=True)

    ci_status = iw.pullrequest_status
    ci_verified = None
    shippable_test_results = None
    needs_testresult_notification = False

    # find the last chronological run id
    #   https://app.shippable.com/github/ansible/ansible/runs/21001/summary
    #   https://app.shippable.com/github/ansible/ansible/runs/21001
    last_run = [x[u'target_url'] for x in ci_status if x.get(u'context', u'') == u'Shippable'][0]
    last_run = last_run.split(u'/')
    if last_run[-1] == u'summary':
        last_run = last_run[-2]
    else:
        last_run = last_run[-1]

    # filter by the last run id
    (run_data, commitSha, shippable_test_results, ci_verified) = \
        shippable.get_test_results(
            last_run,
            usecache=True,
            filter_paths=[u'/testresults/ansible-test-.*.json'],
    )

    # do validation so that we're not stepping on toes
    if u'ci_verified' in iw.labels and not ci_verified:

        sh = ShippableHistory(iw, shippable, ci_status)
        vinfo = sh.info_for_last_ci_verified_run()

        if vinfo:
            if last_run == vinfo[u'run_id']:
                ci_verified = True
            else:
                if C.DEFAULT_BREAKPOINTS:
                    logging.error(u'breakpoint!')
                    import epdb; epdb.st()

    # no results means no notification required
    if len(shippable_test_results) < 1:
        needs_testresult_notification = False
    else:

        s_bpcs = iw.history.get_boilerplate_comments_content(
            bfilter='shippable_test_result'
        )

        if s_bpcs:
            # was this specific result shown?
            job_ids = [x[u'job_id'] for x in shippable_test_results]
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
    if rmeta[u'needs_testresult_notification']:
        hcd = has_commentable_data(shippable_test_results)
        rmeta[u'needs_testresult_notification'] = hcd

    rmeta = {
        u'shippable_test_results': shippable_test_results,
        u'ci_verified': ci_verified,
        u'needs_testresult_notification': needs_testresult_notification
    }

    return rmeta


def get_last_shippable_full_run_date(ci_status, shippable):
    '''Map partial re-runs back to their last full run date'''

    # https://github.com/ansible/ansibullbot/issues/935

    # (Epdb) pp [x['target_url'] for x in ci_status]
    # [u'https://app.shippable.com/github/ansible/ansible/runs/67039/summary',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67039/summary',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67039',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67037/summary',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67037/summary',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67037']

    if shippable is None:
        return None

    # extract and unique the run ids from the target urls
    runids = [get_runid_from_status(x) for x in ci_status]

    # get rid of duplicates and sort
    runids = sorted(set(runids))

    # always use the numerically higher run id
    runid = runids[-1]

    # build a datastructure to hold the info collected
    rundata = {
        u'runid': runid,
        u'created_at': None,
        u'rerun_batch_id': None,
        u'rerun_batch_createdat': None
    }

    # query the api for all data on this runid
    try:
        rdata = shippable.get_run_data(to_text(runid), usecache=False)
    except ShippableNoData:
        return None

    # whoops ...
    if rdata is None:
        return None

    # get the referenced run for the last runid if it exists
    pbag = rdata.get(u'propertyBag')
    if pbag:
        rundata[u'rerun_batch_id'] = pbag.get(u'originalRunId')

    # keep the timestamp too
    rundata[u'created_at'] = rdata.get(u'createdAt')

    # if it had a rerunbatchid it was a partial run and
    # we need to go get the date on the original run
    while rundata[u'rerun_batch_id']:
        # the original run data
        rjdata = shippable.get_run_data(rundata[u'rerun_batch_id'])
        # swap the timestamp
        rundata[u'rerun_batch_createdat'] = rundata[u'created_at']
        # get the old timestamp
        rundata[u'created_at'] = rjdata.get(u'createdAt')
        # get the new batchid
        #rundata['rerun_batch_id'] = rjdata.get('propertyBag', {}).get('originalRunId')
        pbag = rjdata.get(u'propertyBag')
        if pbag:
            rundata[u'rerun_batch_id'] = pbag.get(u'originalRunId')
        else:
            rundata[u'rerun_batch_id'] = None

    # return only the timestamp from the last full run
    return rundata[u'created_at']


def get_runid_from_status(status):
    # (Epdb) pp [(x['target_url'], x['description']) for x in ci_status]
    # [(u'https://app.shippable.com/runs/58cb6ad937380a0800e36940',
    # u'Run 16560 status is SUCCESS. '),
    # (u'https://app.shippable.com/runs/58cb6ad937380a0800e36940',
    # u'Run 16560 status is PROCESSING. '),
    # (u'https://app.shippable.com/github/ansible/ansible/runs/16560',
    # u'Run 16560 status is WAITING. ')]

    # (Epdb) pp [x['target_url'] for x in ci_status]
    # [u'https://app.shippable.com/github/ansible/ansible/runs/67039/summary',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67039/summary',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67039',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67037/summary',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67037/summary',
    # u'https://app.shippable.com/github/ansible/ansible/runs/67037']

    paths = status[u'target_url'].split(u'/')
    if paths[-1].isdigit():
        return int(paths[-1])
    if paths[-2].isdigit():
        return int(paths[-2])
    for x in status[u'description'].split():
        if x.isdigit():
            return int(x)

    return None

