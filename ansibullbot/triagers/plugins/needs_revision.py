import datetime
import logging

import pytz

from ansibullbot.triagers.plugins.shipit import is_approval
from ansibullbot.utils.timetools import strip_time_safely
from ansibullbot.wrappers.historywrapper import ShippableHistory

import ansibullbot.constants as C


def get_needs_revision_facts(triager, issuewrapper, meta, shippable):
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
    ci_state = None
    ci_stale = True
    mstate = None
    change_requested = None
    ready_for_review = None
    has_commit_mention = False
    has_commit_mention_notification = False

    has_shippable = False
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
        u'merge_commits': merge_commits,
        u'has_merge_commit_notification': has_merge_commit_notification,
        u'mergeable': None,
        u'mergeable_state': mstate,
        u'change_requested': change_requested,
        u'ci_state': ci_state,
        u'ci_stale': ci_stale,
        u'reviews': None,
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

    maintainers = [x for x in triager.ansible_core_team
                   if x not in triager.BOTNAMES]

    maintainers += meta.get(u'component_maintainers', [])

    ci_states = shippable.get_states(iw.pullrequest_status)
    if ci_states:
        has_shippable = True
        ci_stale = shippable.is_stale(ci_states)
        ci_state = shippable.get_state(ci_states)

    logging.info(u'ci_state == %s' % ci_state)

    # clean/unstable/dirty/unknown
    mstate = iw.mergeable_state
    if not mstate:
        mstate = u'unknown'
    logging.info(u'mergeable_state == %s' % mstate)

    # clean/unstable/dirty/unknown
    # FIXME ci_state related to shippable? make it general?
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
        user_reviews = _get_review_state(
            iw.reviews,
            iw.submitter,
            number=iw.number,
        )

        if user_reviews:
            last_commit = iw.commits[-1].sha
            change_requested = _changes_requested_by(user_reviews, shipits, last_commit, ready_for_review)
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

    # keep track of who deleted their repo/branch
    if iw.pullrequest.head.repo:
        has_remote_repo = True
    else:
        has_remote_repo = False

    # https://github.com/ansible/ansibullbot/issues/406
    has_shippable_yaml = iw.pullrequest_filepath_exists(shippable.required_file)
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
        u'has_commit_mention': has_commit_mention,
        u'has_commit_mention_notification': has_commit_mention_notification,
        u'merge_commits': merge_commits,
        u'has_merge_commit_notification': has_merge_commit_notification,
        u'mergeable': iw.mergeable,
        u'mergeable_state': mstate,
        u'change_requested': change_requested,
        u'ci_state': ci_state,
        u'ci_stale': ci_stale,
        u'reviews': iw.reviews,
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


def _changes_requested_by(user_reviews, shipits, last_commit, ready_for_review):
    outstanding = set()
    for actor, review in user_reviews.items():
        if review[u'state'] == u'CHANGES_REQUESTED':
            if actor in shipits:
                review_time = strip_time_safely(review[u'submitted_at'])
                review_time = pytz.utc.localize(review_time)
                shipit_time = shipits[actor]
                if review_time < shipit_time:
                    # ignore review older than shipit
                    # https://github.com/ansible/ansibullbot/issues/671
                    continue

            if ready_for_review:
                review_time = strip_time_safely(review[u'submitted_at'])
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


def _get_review_state(reviews, submitter, number=None):
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


def get_shippable_run_facts(iw, meta, shippable):
    '''Does an issue need the test result comment?'''
    # https://github.com/ansible/ansibullbot/issues/312
    # https://github.com/ansible/ansibullbot/issues/404
    # https://github.com/ansible/ansibullbot/issues/418
    # should only be here if the run state is failed ...
    if not meta[u'has_shippable'] or meta[u'ci_state'] != u'failure':
        return {
            u'shippable_test_results': None,
            u'ci_verified': None,
            u'needs_testresult_notification': None
        }

    needs_testresult_notification = False

    ci_status = iw.pullrequest_status
    last_run_id = shippable.get_last_run_id(ci_status)

    # filter by the last run id
    # FIXME this needs to be split into two methods
    shippable_test_results, ci_verified = \
        shippable.get_test_results(
            last_run_id,
            usecache=True,
            filter_paths=[u'/testresults/ansible-test-.*.json'],
        )

    # do validation so that we're not stepping on toes
    if u'ci_verified' in iw.labels and not ci_verified:
        sh = ShippableHistory(iw, shippable, ci_status)
        vinfo = sh.info_for_last_ci_verified_run()
        if vinfo:
            if last_run_id == vinfo[u'run_id']:
                ci_verified = True

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

    return {
        u'shippable_test_results': shippable_test_results,
        u'ci_verified': ci_verified,
        u'needs_testresult_notification': needs_testresult_notification
    }
