import datetime
import logging

import pytz

from ansibullbot.errors import NoCIError
from ansibullbot.triagers.plugins.shipit import is_approval
from ansibullbot.utils.timetools import strip_time_safely


CI_STALE_DAYS = 7


def get_needs_revision_facts(iw, meta, ci, core_team=None, botnames=None):
    # Thanks @adityacs for this PR. This PR requires revisions, either
    # because it fails to build or by reviewer request. Please make the
    # suggested revisions. When you are done, please comment with text
    # 'ready_for_review' and we will put this PR back into review.

    # a "dirty" mergeable_state can exist with "successfull" ci_state.

    if core_team is None:
        core_team = []
    if botnames is None:
        botnames = []

    committer_count = None
    needs_revision = False
    needs_revision_msgs = []
    merge_commits = []
    has_merge_commit_notification = False
    needs_rebase = False
    needs_rebase_msgs = []
    ci_state = None
    ci_stale = False
    mstate = None
    change_requested = None
    ready_for_review = None
    has_commit_mention = False
    has_commit_mention_notification = False

    has_ci = False

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
        'has_ci': has_ci,
        'merge_commits': merge_commits,
        'has_merge_commit_notification': has_merge_commit_notification,
        'mergeable': None,
        'mergeable_state': mstate,
        'change_requested': change_requested,
        'ci_state': ci_state,
        'ci_stale': ci_stale,
        'reviews': None,
        'ready_for_review': ready_for_review,
        'has_remote_repo': has_remote_repo,
        'stale_reviews': stale_reviews,
        'has_multiple_modules': has_multiple_modules,
        'needs_multiple_new_modules_notification': needs_multiple_new_modules_notification
    }

    if not iw.is_pullrequest():
        return rmeta

    bpcs = iw.history.get_boilerplate_comments()
    bpcs = [x[0] for x in bpcs]

    maintainers = [x for x in core_team if x not in botnames]

    maintainers += meta.get('component_maintainers', [])

    try:
        ci_date = ci.get_last_full_run_date()
    except NoCIError:
        pass
    else:
        has_ci = True
        if ci_date:
            ci_stale = (datetime.datetime.now() - ci_date).days > CI_STALE_DAYS
        ci_state = ci.state

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
        if ci_state is None:
            needs_revision = True

        # FIXME mstate == 'draft'
    else:
        shipits = {}  # key: actor, value: created_at

        has_set_needs_revision = set()

        for event in iw.history.history:

            if event['actor'] in botnames:
                continue

            if event['actor'] in maintainers and \
                    event['actor'] != iw.submitter:

                if event['event'] == 'labeled':
                    if event['label'] == 'needs_revision':
                        needs_revision = True
                        needs_revision_msgs.append(
                            '[%s] labeled' % event['actor']
                        )
                        has_set_needs_revision.add(event['actor'])
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
                    if any(line.startswith('needs_revision') for line in event['body'].splitlines()) and \
                            '!needs_revision' not in event['body']:
                        needs_revision = True
                        needs_revision_msgs.append(
                            '[%s] needs_revision' % event['actor']
                        )
                        has_set_needs_revision.add(event['actor'])
                        continue

                    if 'shipit' in event['body'].lower():
                        if event['actor'] in has_set_needs_revision:
                            has_set_needs_revision.remove(event['actor'])
                            if not has_set_needs_revision:
                                needs_revision = False
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
                        if ready_for_review is None or event['created_at'] > ready_for_review:
                            ready_for_review = event['created_at']
                        needs_revision = False
                        needs_revision_msgs.append(
                            '[%s] shipit' % event['actor']
                        )
                        continue

        # This is a complicated algo ... sigh
        user_reviews = _get_review_state(
            iw.reviews,
            iw.submitter,
        )

        if user_reviews:
            last_commit = iw.commits[-1].sha
            change_requested = _changes_requested_by(user_reviews, shipits, last_commit, ready_for_review)
            if change_requested:
                needs_revision = True
                needs_revision_msgs.append(
                    'outstanding reviews: %s' % ','.join(change_requested)
                )

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
                botnames,
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

    # keep track of who deleted their repo/branch
    has_remote_repo = bool(iw.pullrequest.head.repo)

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
        'has_ci': has_ci,
        'has_commit_mention': has_commit_mention,
        'has_commit_mention_notification': has_commit_mention_notification,
        'merge_commits': merge_commits,
        'has_merge_commit_notification': has_merge_commit_notification,
        'mergeable': iw.mergeable,
        'mergeable_state': mstate,
        'change_requested': change_requested,
        'ci_state': ci_state,
        'ci_stale': ci_stale,
        'reviews': iw.reviews,
        'ready_for_review_date': ready_for_review,
        'ready_for_review': bool(ready_for_review),
        'has_remote_repo': has_remote_repo,
        'stale_reviews': stale_reviews,
        'has_multiple_modules': has_multiple_modules,
        'needs_multiple_new_modules_notification': needs_multiple_new_modules_notification
    }
    if rmeta['ready_for_review_date']:
        rmeta['ready_for_review_date'] = rmeta['ready_for_review_date'].isoformat()

    return rmeta


def _changes_requested_by(user_reviews, shipits, last_commit, ready_for_review):
    outstanding = set()
    for actor, review in user_reviews.items():
        if review['state'] == 'CHANGES_REQUESTED':
            if actor in shipits:
                review_time = strip_time_safely(review['submitted_at'])
                review_time = pytz.utc.localize(review_time)
                shipit_time = shipits[actor]
                if review_time < shipit_time:
                    # ignore review older than shipit
                    # https://github.com/ansible/ansibullbot/issues/671
                    continue

            if ready_for_review:
                review_time = strip_time_safely(review['submitted_at'])
                review_time = pytz.utc.localize(review_time)
                if review['commit_id'] != last_commit and review_time < ready_for_review:
                    # ignore review older than ready_for_review comment wrote by submitter
                    # but only if the pull request has been updated (meaning the
                    # last commit isn't the reviewed commit).
                    continue

            outstanding.add(actor)
        elif review['state'] not in ['APPROVED', 'COMMENTED']:
            logging.error('%s unhandled' % review['state'])

    return list(outstanding)


def _get_review_state(reviews, submitter):
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
            if 'commit_id' in review:
                commit_id = review['commit_id']
            else:
                commit_id = None

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
                logging.error('%s not handled yet' % state)

    return user_reviews


def get_ci_run_facts(iw, meta, ci):
    '''Does an issue need the test result comment?'''
    # https://github.com/ansible/ansibullbot/issues/312
    # https://github.com/ansible/ansibullbot/issues/404
    # https://github.com/ansible/ansibullbot/issues/418

    ci_facts = {
        'ci_test_results': None,
        'ci_verified': None,
        'needs_testresult_notification': None
    }

    # should only be here if the run state is failed ...
    if not meta['has_ci'] or meta['ci_state'] != 'failure':
        return ci_facts

    if ci.last_run is None:
        return ci_facts

    # filter by the last run id
    ci_test_results, ci_verified = ci.get_test_results()

    # do validation so that we're not stepping on toes
    if 'ci_verified' in iw.labels and not ci_verified:
        ci_verified_last_applied = iw.history.label_last_applied('ci_verified')
        if ci_verified_last_applied >= ci.last_run['updated_at']:
            ci_verified = True

    # no results means no notification required
    if len(ci_test_results) < 1:
        needs_testresult_notification = False
    else:
        s_bpcs = iw.history.get_boilerplate_comments_content()
        if s_bpcs:
            # was this specific result shown?
            job_ids = [x['job_id'] for x in ci_test_results]
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

    return {
        'ci_test_results': ci_test_results,
        'ci_verified': ci_verified,
        'needs_testresult_notification': needs_testresult_notification
    }
