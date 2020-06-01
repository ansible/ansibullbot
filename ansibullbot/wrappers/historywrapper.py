import datetime
import logging
import os
from operator import itemgetter

import pytz

import ansibullbot.constants as C
from ansibullbot._pickle_compat import pickle_dump, pickle_load
from ansibullbot._text_compat import to_text


class HistoryWrapper(object):
    """A tool to ask questions about an issue's history.

    This class will join the events and comments of an issue into
    an object that allows the user to make basic queries without
    having to iterate through events manually.

    Constructor Examples:
        hwrapper = HistoryWrapper(IssueWrapper)
        hwrapper = HistoryWrapper(PullRequestWrapper)

    https://developer.github.com/v3/issues/timeline/
    """

    SCHEMA_VERSION = 1.2
    BOTNAMES = C.DEFAULT_BOT_NAMES

    def __init__(self, issue, usecache=True, cachedir=None):
        self.issue = issue
        self._waffled_labels = None

        if issue.repo.repo_path not in cachedir and u'issues' not in cachedir:
            self.cachefile = os.path.join(
                cachedir,
                issue.repo.repo_path,
                u'issues',
                to_text(issue.instance.number),
                u'history.pickle'
            )
        elif issue.repo.repo_path not in cachedir:
            self.cachefile = os.path.join(
                cachedir,
                issue.repo.repo_path,
                u'issues',
                to_text(issue.instance.number),
                u'history.pickle'
            )
        elif u'issues' not in cachedir:
            self.cachefile = os.path.join(
                cachedir,
                u'issues',
                to_text(issue.instance.number),
                u'history.pickle'
            )
        else:
            self.cachefile = os.path.join(
                cachedir,
                to_text(issue.instance.number),
                u'history.pickle'
            )

        self.cachedir = os.path.join(
            cachedir,
            os.path.dirname(self.cachefile)
        )
        if u'issues' not in self.cachedir:
            logging.error(self.cachedir)
            if C.DEFAULT_BREAKPOINTS:
                logging.error(u'breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception(u'')

        if usecache:
            cache = self._load_cache()

            if not self.validate_cache(cache):
                logging.info(u'history cache invalidated, rebuilding')
                self.history = self.issue.events
                self._dump_cache()
            else:
                logging.info(u'use cached history')
                self.history = cache[u'history']
        else:
            self.history = self.issue.events

        self.history = sorted(self.history, key=itemgetter(u'created_at'))

    def validate_cache(self, cache):
        if cache is None:
            return False

        if not isinstance(cache, dict):
            return False

        if 'history' not in cache:
            return False

        if 'updated_at' not in cache:
            return False

        # use a versioned schema to track changes
        if not cache.get('version') or cache['version'] < self.SCHEMA_VERSION:
            logging.info('history cache schema version behind')
            return False

        if cache[u'updated_at'] < self.issue.instance.updated_at:
            logging.info('history cache behind issue')
            return False

        # FIXME the cache is getting wiped out by cross-refences,
        #       so keeping this around as a failsafe
        if len(cache['history']) < (len([x for x in cache['history'] if x['event'] == 'commented']) + len(self.issue.labels)):
            return False

        # FIXME label events seem to go missing, so force a rebuild
        if 'needs_info' in self.issue.labels:
            le = [x for x in cache['history'] if x['event'] == 'labeled' and x['label'] == 'needs_info']
            if not le:
                return False

        return True

    def _load_cache(self):
        if not os.path.isdir(self.cachedir):
            os.makedirs(self.cachedir)
        if not os.path.isfile(self.cachefile):
            logging.info(u'!%s' % self.cachefile)
            return None
        try:
            with open(self.cachefile, 'rb') as f:
                cachedata = pickle_load(f)
        except Exception as e:
            logging.debug(e)
            logging.info(u'%s failed to load' % self.cachefile)
            cachedata = None

        cachedata[u'history'] = self._fix_event_bytes(cachedata[u'history'])

        return cachedata

    def _dump_cache(self):
        if any(x for x in self.history if not isinstance(x['created_at'], datetime.datetime)):
            logging.error(self.history)
            raise AssertionError(u'found a non-datetime created_at in events data')

        if not os.path.isdir(self.cachedir):
            os.makedirs(self.cachedir)

        # keep the timestamp
        cachedata = {
            u'version': self.SCHEMA_VERSION,
            u'updated_at': self.issue.instance.updated_at,
            u'history': self.history
        }

        try:
            with open(self.cachefile, 'wb') as f:
                pickle_dump(cachedata, f)
        except Exception as e:
            logging.error(e)
            if C.DEFAULT_BREAKPOINTS:
                logging.error(u'breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception(u'')

    def get_json_comments(self):
        comments = self.issue.comments[:]
        for idx, x in enumerate(comments):
            ca = x[u'created_at']
            if not (hasattr(ca, 'tzinfo') and ca.tzinfo):
                ca = pytz.utc.localize(x['created_at'])
            nc = {u'body': x[u'body'], u'created_at': ca, u'user': {u'login': x[u'actor']}}
            comments[idx] = nc
        return comments

    def _fix_event_bytes(self, events):
        '''Make sure all event values are strings and not bytes'''
        for ide,event in enumerate(events):
            for k,v in event.items():
                if isinstance(v, bytes):
                    events[ide][k] = v.decode('utf-8')
        return events

    def merge_commits(self, commits):
        for xc in commits:
            event = {}
            event[u'id'] = xc.sha
            if hasattr(xc.committer, u'login'):
                event[u'actor'] = xc.committer.login
            else:
                event[u'actor'] = to_text(xc.committer)
            event[u'created_at'] = pytz.utc.localize(xc.commit.committer.date)
            event[u'event'] = u'committed'
            event[u'message'] = xc.commit.message
            self.history.append(event)
        self.history = sorted(self.history, key=itemgetter(u'created_at'))

    def merge_reviews(self, reviews):
        for review in reviews:
            event = {}

            # https://github.com/ansible/ansibullbot/issues/1207
            # "ghost" users are deleted users and show up as NoneType
            if review.get('user') is None:
                continue

            if review[u'state'] == u'COMMENTED':
                event[u'event'] = u'review_comment'
            elif review[u'state'] == u'CHANGES_REQUESTED':
                event[u'event'] = u'review_changes_requested'
            elif review[u'state'] == u'APPROVED':
                event[u'event'] = u'review_approved'
            elif review[u'state'] == u'DISMISSED':
                event[u'event'] = u'review_dismissed'
            elif review[u'state'] == u'PENDING':
                # ignore pending review
                continue
            else:
                logging.error(u'unknown review state %s', review[u'state'])
                continue

            event[u'id'] = review[u'id']
            event[u'actor'] = review[u'user'][u'login']
            event[u'created_at'] = pytz.utc.localize(
                    datetime.datetime.strptime(review[u'submitted_at'], u'%Y-%m-%dT%H:%M:%SZ')
                )
            if u'commit_id' in review:
                event[u'commit_id'] = review[u'commit_id']
            else:
                event[u'commit_id'] = None
            event[u'body'] = review.get(u'body')

            self.history.append(event)
        self.history = sorted(self.history, key=itemgetter(u'created_at'))

    def merge_history(self, oldhistory):
        '''Combine history from another issue [migration]'''
        self.history += oldhistory
        self.history = sorted(self.history, key=itemgetter(u'created_at'))

    def _find_events_by_actor(self, eventname, actor, maxcount=1):
        matching_events = []
        for event in self.history:
            if event[u'event'] == eventname or not eventname:
                # allow actor to be a list or a string or None
                if actor is None:
                    matching_events.append(event)
                elif type(actor) != list and event[u'actor'] == actor:
                    matching_events.append(event)
                elif type(actor) == list and event[u'actor'] in actor:
                    matching_events.append(event)
                if len(matching_events) == maxcount:
                    break

        """
        # get rid of deleted comments
        if active and eventname == u'commented':
            cids = [x.id for x in self.issue.comments]
            for me in matching_events[:]:
                if me['id'] not in cids:
                    print('remove %s' % me['id'])
                    matching_events.remove(me)
                else:
                    print('%s in cids' % me['id'])
            import epdb; epdb.st()
        """

        return matching_events

    def get_user_comments(self, username):
        """Get all the comments from a user"""
        matching_events = self._find_events_by_actor(
            u'commented',
            username,
            maxcount=999
        )
        comments = [x[u'body'] for x in matching_events]
        return comments

    def search_user_comments(self, username, searchterm):
        """Get all the comments from a user"""
        matching_events = self._find_events_by_actor(
            u'commented',
            username,
            maxcount=999
        )
        comments = [x[u'body'] for x in matching_events if searchterm in x[u'body'].lower()]
        return comments

    def get_commands(self, username, command_keys, timestamps=False, uselabels=True):
        """Given a list of phrase keys, return a list of phrases used"""
        commands = []

        comments = self._find_events_by_actor(
            u'commented',
            username,
            maxcount=999
        )
        labels = self._find_events_by_actor(
            u'labeled',
            username,
            maxcount=999
        )
        unlabels = self._find_events_by_actor(
            u'unlabeled',
            username,
            maxcount=999
        )
        events = comments + labels + unlabels
        events = sorted(events, key=itemgetter(u'created_at'))
        for event in events:
            if event[u'actor'] in self.BOTNAMES:
                continue
            if event[u'event'] == u'commented':
                for y in command_keys:
                    if event[u'body'].startswith(u'_From @'):
                        continue
                    l_body = event[u'body'].split()
                    if y != u'bot_broken' and u'bot_broken' in l_body:
                        continue
                    if y in l_body and not u'!' + y in l_body:
                        if timestamps:
                            commands.append((event[u'created_at'], y))
                        else:
                            commands.append(y)
            elif event[u'event'] == u'labeled' and uselabels:
                if event[u'label'] in command_keys:
                    if timestamps:
                        commands.append((event[u'created_at'], y))
                    else:
                        commands.append(event[u'label'])
            elif event[u'event'] == u'unlabeled' and uselabels:
                if event[u'label'] in command_keys:
                    if timestamps:
                        commands.append((event[u'created_at'], y))
                    else:
                        commands.append(u'!' + event[u'label'])

        return commands

    def get_component_commands(self, command_key='!component'):
        """Given a list of phrase keys, return a list of phrases used"""
        commands = []
        events = self.get_json_comments()
        events = [x for x in events if x['user']['login'] not in self.BOTNAMES]

        for event in events:
            if event.get(u'body'):
                matched = False
                lines = event[u'body'].split(u'\n')
                for line in lines:
                    if line.strip().startswith(command_key):
                        matched = True
                        break
                if matched:
                    commands.append(event)

        return commands

    def was_assigned(self, username):
        """Has person X ever been assigned to this issue?"""
        matching_events = self._find_events_by_actor(u'assigned', username)
        return len(matching_events) > 0

    def was_subscribed(self, username):
        """Has person X ever been subscribed to this issue?"""
        matching_events = self._find_events_by_actor(u'subscribed', username)
        return len(matching_events) > 0

    def last_notified(self, username):
        """When was this person pinged last in a comment?"""
        if not isinstance(username, list):
            username = [username]
        username = [u'@' + x for x in username]
        last_notification = None
        comments = [x for x in self.history if x[u'event'] == u'commented']
        for comment in comments:
            if not comment.get(u'body'):
                continue
            for un in username:
                if un in comment[u'body']:
                    if not last_notification:
                        last_notification = comment[u'created_at']
                    else:
                        if comment[u'created_at'] > last_notification:
                            last_notification = comment[u'created_at']
        return last_notification

    def last_comment(self, username):
        last_comment = None
        for event in reversed(self.history):
            if event[u'event'] == u'commented':
                if type(username) == list:
                    if event[u'actor'] in username:
                        last_comment = event[u'body']
                elif event[u'actor'] == username:
                    last_comment = event[u'body']
            if last_comment:
                break
        return last_comment

    def label_last_applied(self, label):
        """What date was a label last applied?"""
        last_date = None
        for event in reversed(self.history):
            if event[u'event'] == u'labeled':
                if event[u'label'] == label:
                    last_date = event[u'created_at']
                    break
        return last_date

    def label_last_removed(self, label):
        """What date was a label last removed?"""
        last_date = None
        for event in reversed(self.history):
            if event[u'event'] == u'unlabeled':
                if event[u'label'] == label:
                    last_date = event[u'created_at']
                    break
        return last_date

    def was_labeled(self, label, bots=None):
        """Were labels -ever- applied to this issue?"""
        labeled = False
        for event in self.history:
            if bots:
                if event[u'actor'] in bots:
                    continue
            if event[u'event'] == u'labeled':
                if label and event[u'label'] == label:
                    labeled = True
                    break
                elif not label:
                    labeled = True
                    break
        return labeled

    def was_unlabeled(self, label, bots=None):
        """Were labels -ever- unapplied from this issue?"""
        labeled = False
        for event in self.history:
            if bots:
                if event[u'actor'] in bots:
                    continue
            if event[u'event'] == u'unlabeled':
                if label and event[u'label'] == label:
                    labeled = True
                    break
                elif not label:
                    labeled = True
                    break
        return labeled

    def get_boilerplate_comments(self, dates=False, content=True):
        boilerplates = []

        comments = self.get_json_comments()
        comments = [x for x in comments if x['user']['login'] in self.BOTNAMES] 

        for comment in comments:
            if not comment.get(u'body'):
                continue
            if u'boilerplate:' in comment[u'body']:
                lines = [x for x in comment[u'body'].split(u'\n')
                         if x.strip() and u'boilerplate:' in x]
                bp = lines[0].split()[2]

                if dates or content:
                    bpc = []
                    if dates:
                        bpc.append(comment[u'created_at'])
                    bpc.append(bp)
                    if content:
                        bpc.append(comment[u'body'])
                    boilerplates.append(bpc)
                else:
                    boilerplates.append(bp)

        return boilerplates

    def get_boilerplate_comments_content(self, bfilter=None):
        # FIXME bfilter not used but a caller passes it in
        # in ansibullbot/triagers/plugins/needs_revision.py
        bpcs = self.get_boilerplate_comments()
        bpcs = [x[-1] for x in bpcs]
        return bpcs

    def last_date_for_boilerplate(self, boiler):
        last_date = None
        bps = self.get_boilerplate_comments(dates=True)
        for bp in bps:
            if bp[1] == boiler:
                last_date = bp[0]
        return last_date

    @property
    def last_commit_date(self):
        events = [x for x in self.history if x[u'event'] == u'committed']
        if events:
            return events[-1][u'created_at']
        else:
            return None

    def get_changed_labels(self, prefix=None, bots=None):
        '''make a list of labels that have been set/unset'''
        if bots is None:
            bots = []
        labeled = []
        for event in self.history:
            if event[u'actor'] in bots:
                continue
            if event[u'event'] in [u'labeled', u'unlabeled']:
                if prefix:
                    if event[u'label'].startswith(prefix):
                        labeled.append(event[u'label'])
                else:
                    labeled.append(event[u'label'])
        return sorted(set(labeled))

    def label_is_waffling(self, label, limit=20):
        """ detect waffling on labels """
        #https://github.com/ansible/ansibullbot/issues/672
        if self._waffled_labels is None:
            self._waffled_labels = {}
            history = [x[u'label'] for x in self.history if u'label' in x]
            labels = sorted(set(history))
            for hl in labels:
                self._waffled_labels[hl] = len([x for x in history if x == hl])

        if self._waffled_labels.get(label, 0) >= limit:
            return True
        else:
            return False

    def command_status(self, command):
        status = None
        for event in self.history:
            if 'body' not in event:
                continue
            if event['body'].strip() == command:
                status = True
            elif event['body'].strip() == '!' + command:
                status = False
        return status


class ShippableHistory(object):
    '''A helper to associate ci_verified labels to runs/commits'''

    def __init__(self, issuewrapper, shippable, ci_status):
        self.iw = issuewrapper
        self.shippable = shippable
        self.ci_status = ci_status
        self.history = []
        self.join_history()

    def join_history(self):
        this_history = [x for x in self.iw.history.history]

        status = {}
        for x in self.ci_status:
            # target_url could be:
            # https://app.shippable.com/github/ansible/ansible/runs/41758/summary
            # https://app.shippable.com/github/ansible/ansible/runs/41758
            turl = x[u'target_url']
            if turl.endswith(u'/summary'):
                turl = turl[:-8]
            run_id = turl.split(u'/')[-1]
            if run_id == u'zuul.openstack.org':
                continue

            if run_id in status:
                rd = status[run_id]
            else:
                rd = self.shippable.get_run_data(run_id, usecache=True)
                status[run_id] = rd

            # sometimes the target urls are invalid
            #   https://app.shippable.com/runs/58cc4fe537380a0800e4284c
            #   https://app.shippable.com/github/ansible/ansible/runs/16628
            if not rd:
                continue

            ts = pytz.utc.localize(
                datetime.datetime.strptime(x[u'updated_at'], u'%Y-%m-%dT%H:%M:%SZ')
            )

            this_history.append(
                {
                    u'actor': rd.get(u'triggeredBy', {}).get(u'login'),
                    u'event': u'ci_run',
                    u'created_at': ts,
                    u'state': x[u'state'],
                    u'run_id': run_id,
                    u'status_id': x[u'id'],
                    u'sha': rd[u'commitSha']
                }
            )

        this_history = sorted(this_history, key=lambda k: k[u'created_at'])
        self.history = this_history

    def info_for_last_ci_verified_run(self):
        '''Attempt to correlate the ci_label to a specific run'''
        # The ci_status for an issue will "rollover", meaning older instances
        # will go missing and can no longer be recalled. We just have to
        # assume in those cases that the ci_verified label was added on a very
        # old run. =(

        verified_idx = None
        for idx, x in enumerate(self.history):
            if x[u'event'] == u'labeled':
                if x[u'label'] == u'ci_verified':
                    verified_idx = idx

        # exit early if never verified
        if verified_idx is None:
            return None

        run_idx = None
        for idx, x in enumerate(self.history):
            if x[u'event'] == u'ci_run':
                if x[u'created_at'] <= self.history[verified_idx][u'created_at']:
                    run_idx = idx
        if run_idx:
            run_info = self.history[run_idx]
            return run_info
        else:
            return None
