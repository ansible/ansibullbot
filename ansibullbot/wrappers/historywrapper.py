import datetime
import logging
import os
import pickle

from operator import itemgetter

import pytz

import ansibullbot.constants as C
from ansibullbot._text_compat import to_text
from ansibullbot.utils.timetools import strip_time_safely


class HistoryWrapper:
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

        if issue.repo.repo_path not in cachedir and 'issues' not in cachedir:
            self.cachefile = os.path.join(
                cachedir,
                issue.repo.repo_path,
                'issues',
                to_text(issue.instance.number),
                'history.pickle'
            )
        elif issue.repo.repo_path not in cachedir:
            self.cachefile = os.path.join(
                cachedir,
                issue.repo.repo_path,
                'issues',
                to_text(issue.instance.number),
                'history.pickle'
            )
        elif 'issues' not in cachedir:
            self.cachefile = os.path.join(
                cachedir,
                'issues',
                to_text(issue.instance.number),
                'history.pickle'
            )
        else:
            self.cachefile = os.path.join(
                cachedir,
                to_text(issue.instance.number),
                'history.pickle'
            )

        self.cachedir = os.path.join(
            cachedir,
            os.path.dirname(self.cachefile)
        )
        if 'issues' not in self.cachedir:
            logging.error(self.cachedir)
            raise Exception

        if usecache:
            cache = self._load_cache()

            if not self.validate_cache(cache):
                logging.info('history cache invalidated, rebuilding')
                self.history = self.issue.events
                self._dump_cache()
            else:
                logging.info('use cached history')
                self.history = cache['history']
        else:
            self.history = self.issue.events

        self.history = sorted(self.history, key=itemgetter('created_at'))

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

        if cache['updated_at'] < self.issue.instance.updated_at:
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
            logging.info('!%s' % self.cachefile)
            return None
        try:
            with open(self.cachefile, 'rb') as f:
                cachedata = pickle.load(f)
        except Exception as e:
            logging.debug(e)
            logging.info('%s failed to load' % self.cachefile)
            cachedata = None

        cachedata['history'] = self._fix_event_bytes(cachedata['history'])

        return cachedata

    def _dump_cache(self):
        if any(x for x in self.history if not isinstance(x['created_at'], datetime.datetime)):
            logging.error(self.history)
            raise AssertionError('found a non-datetime created_at in events data')

        if not os.path.isdir(self.cachedir):
            os.makedirs(self.cachedir)

        # keep the timestamp
        cachedata = {
            'version': self.SCHEMA_VERSION,
            'updated_at': self.issue.instance.updated_at,
            'history': self.history
        }

        try:
            with open(self.cachefile, 'wb') as f:
                pickle.dump(cachedata, f)
        except Exception as e:
            logging.error(e)
            raise

    def get_json_comments(self):
        comments = self.issue.comments[:]
        for idx, x in enumerate(comments):
            ca = x['created_at']
            if not (hasattr(ca, 'tzinfo') and ca.tzinfo):
                ca = pytz.utc.localize(x['created_at'])
            nc = {'body': x['body'], 'created_at': ca, 'user': {'login': x['actor']}}
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
            event['id'] = xc.sha
            if hasattr(xc.committer, 'login'):
                event['actor'] = xc.committer.login
            else:
                event['actor'] = to_text(xc.committer)
            event['created_at'] = pytz.utc.localize(xc.commit.committer.date)
            event['event'] = 'committed'
            event['message'] = xc.commit.message
            self.history.append(event)
        self.history = sorted(self.history, key=itemgetter('created_at'))

    def merge_reviews(self, reviews):
        for review in reviews:
            event = {}

            # https://github.com/ansible/ansibullbot/issues/1207
            # "ghost" users are deleted users and show up as NoneType
            if review.get('user') is None:
                continue

            if review['state'] == 'COMMENTED':
                event['event'] = 'review_comment'
            elif review['state'] == 'CHANGES_REQUESTED':
                event['event'] = 'review_changes_requested'
            elif review['state'] == 'APPROVED':
                event['event'] = 'review_approved'
            elif review['state'] == 'DISMISSED':
                event['event'] = 'review_dismissed'
            elif review['state'] == 'PENDING':
                # ignore pending review
                continue
            else:
                logging.error('unknown review state %s', review['state'])
                continue

            event['id'] = review['id']
            event['actor'] = review['user']['login']
            event['created_at'] = pytz.utc.localize(strip_time_safely(review['submitted_at']))
            if 'commit_id' in review:
                event['commit_id'] = review['commit_id']
            else:
                event['commit_id'] = None
            event['body'] = review.get('body')

            self.history.append(event)
        self.history = sorted(self.history, key=itemgetter('created_at'))

    def merge_history(self, oldhistory):
        '''Combine history from another issue [migration]'''
        self.history += oldhistory
        self.history = sorted(self.history, key=itemgetter('created_at'))

    def _find_events_by_actor(self, eventname, actor, maxcount=1):
        matching_events = []
        for event in self.history:
            if event['event'] == eventname or not eventname:
                # allow actor to be a list or a string or None
                if actor is None:
                    matching_events.append(event)
                elif type(actor) != list and event['actor'] == actor:
                    matching_events.append(event)
                elif type(actor) == list and event['actor'] in actor:
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
        """

        return matching_events

    def get_user_comments(self, username):
        """Get all the comments from a user"""
        matching_events = self._find_events_by_actor(
            'commented',
            username,
            maxcount=999
        )
        comments = [x['body'] for x in matching_events]
        return comments

    def search_user_comments(self, username, searchterm):
        """Get all the comments from a user"""
        matching_events = self._find_events_by_actor(
            'commented',
            username,
            maxcount=999
        )
        comments = [x['body'] for x in matching_events if searchterm in x['body'].lower()]
        return comments

    def get_commands(self, username, command_keys, timestamps=False, uselabels=True):
        """Given a list of phrase keys, return a list of phrases used"""
        commands = []

        comments = self._find_events_by_actor(
            'commented',
            username,
            maxcount=999
        )
        labels = self._find_events_by_actor(
            'labeled',
            username,
            maxcount=999
        )
        unlabels = self._find_events_by_actor(
            'unlabeled',
            username,
            maxcount=999
        )
        events = comments + labels + unlabels
        events = sorted(events, key=itemgetter('created_at'))
        for event in events:
            if event['actor'] in self.BOTNAMES:
                continue
            if event['event'] == 'commented':
                for y in command_keys:
                    if event['body'].startswith('_From @'):
                        continue
                    l_body = event['body'].split()
                    if y in l_body and not '!' + y in l_body:
                        if timestamps:
                            commands.append((event['created_at'], y))
                        else:
                            commands.append(y)
            elif event['event'] == 'labeled' and uselabels:
                if event['label'] in command_keys:
                    if timestamps:
                        commands.append((event['created_at'], y))
                    else:
                        commands.append(event['label'])
            elif event['event'] == 'unlabeled' and uselabels:
                if event['label'] in command_keys:
                    if timestamps:
                        commands.append((event['created_at'], y))
                    else:
                        commands.append('!' + event['label'])

        return commands

    def get_component_commands(self, command_key='!component'):
        """Given a list of phrase keys, return a list of phrases used"""
        commands = []
        events = self.get_json_comments()
        events = [x for x in events if x['user']['login'] not in self.BOTNAMES]

        for event in events:
            if event.get('body'):
                matched = False
                lines = event['body'].split('\n')
                for line in lines:
                    if line.strip().startswith(command_key):
                        matched = True
                        break
                if matched:
                    commands.append(event)

        return commands

    def was_assigned(self, username):
        """Has person X ever been assigned to this issue?"""
        matching_events = self._find_events_by_actor('assigned', username)
        return len(matching_events) > 0

    def was_subscribed(self, username):
        """Has person X ever been subscribed to this issue?"""
        matching_events = self._find_events_by_actor('subscribed', username)
        return len(matching_events) > 0

    def last_notified(self, username):
        """When was this person pinged last in a comment?"""
        if not isinstance(username, list):
            username = [username]
        username = ['@' + x for x in username]
        last_notification = None
        comments = [x for x in self.history if x['event'] == 'commented']
        for comment in comments:
            if not comment.get('body'):
                continue
            for un in username:
                if un in comment['body']:
                    if not last_notification:
                        last_notification = comment['created_at']
                    else:
                        if comment['created_at'] > last_notification:
                            last_notification = comment['created_at']
        return last_notification

    def last_comment(self, username):
        last_comment = None
        for event in reversed(self.history):
            if event['event'] == 'commented':
                if type(username) == list:
                    if event['actor'] in username:
                        last_comment = event['body']
                elif event['actor'] == username:
                    last_comment = event['body']
            if last_comment:
                break
        return last_comment

    def label_last_applied(self, label):
        """What date was a label last applied?"""
        last_date = None
        for event in reversed(self.history):
            if event['event'] == 'labeled':
                if event['label'] == label:
                    last_date = event['created_at']
                    break
        return last_date

    def label_last_removed(self, label):
        """What date was a label last removed?"""
        last_date = None
        for event in reversed(self.history):
            if event['event'] == 'unlabeled':
                if event['label'] == label:
                    last_date = event['created_at']
                    break
        return last_date

    def was_labeled(self, label, bots=None):
        """Were labels -ever- applied to this issue?"""
        labeled = False
        for event in self.history:
            if bots:
                if event['actor'] in bots:
                    continue
            if event['event'] == 'labeled':
                if label and event['label'] == label:
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
                if event['actor'] in bots:
                    continue
            if event['event'] == 'unlabeled':
                if label and event['label'] == label:
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
            if not comment.get('body'):
                continue
            if 'boilerplate:' in comment['body']:
                lines = [x for x in comment['body'].split('\n')
                         if x.strip() and 'boilerplate:' in x]
                bp = lines[0].split()[2]

                if dates or content:
                    bpc = []
                    if dates:
                        bpc.append(comment['created_at'])
                    bpc.append(bp)
                    if content:
                        bpc.append(comment['body'])
                    boilerplates.append(bpc)
                else:
                    boilerplates.append(bp)

        return boilerplates

    def get_boilerplate_comments_content(self):
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
        events = [x for x in self.history if x['event'] == 'committed']
        if events:
            return events[-1]['created_at']
        else:
            return None

    def get_changed_labels(self, prefix=None, bots=None):
        '''make a list of labels that have been set/unset'''
        if bots is None:
            bots = []
        labeled = []
        for event in self.history:
            if event['actor'] in bots:
                continue
            if event['event'] in ['labeled', 'unlabeled']:
                if prefix:
                    if event['label'].startswith(prefix):
                        labeled.append(event['label'])
                else:
                    labeled.append(event['label'])
        return sorted(set(labeled))

    def label_is_waffling(self, label, limit=20):
        """ detect waffling on labels """
        #https://github.com/ansible/ansibullbot/issues/672
        if self._waffled_labels is None:
            self._waffled_labels = {}
            history = [x['label'] for x in self.history if 'label' in x]
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
