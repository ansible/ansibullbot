#!/usr/bin/env python

import datetime
import logging
import os
import pytz
from operator import itemgetter

from github import GithubObject
from ansibullbot.decorators.github import RateLimited

import ansibullbot.constants as C
from ansibullbot._pickle_compat import pickle_dump, pickle_load
from ansibullbot._text_compat import to_text

# historywrapper.py
#
#   HistoryWrapper - a tool to ask questions about an issue's history
#
#   This class will join the events and comments of an issue into
#   an object that allows the user to make basic queries without
#   having to iterate through events manaully.
#
#   Constructor Examples:
#       hwrapper = HistoryWrapper(IssueWrapper)
#       hwrapper = HistoryWrapper(PullRequestWrapper)
#
#   https://developer.github.com/v3/issues/events/
#   https://developer.github.com/v3/issues/comments/

class Actor(object):
    login = None


class Event(object):

    def __init__(self, raw_data, id=None):
        self.id = id
        self.raw_data = raw_data

    @property
    def node_id(self):
        return self.raw_data.get(u'node_id')

    @property
    def created_at(self):
        ts = self.raw_data.get(u'created_at')
        ts = datetime.datetime.strptime(ts, u'%Y-%m-%dT%H:%M:%SZ')
        return ts

    @property
    def event(self):
        return self.raw_data.get(u'event')

    @property
    def actor(self):
        actor = Actor()
        actor.login = self.raw_data[u'actor'][u'login']
        return actor

    @property
    def commit_id(self):
        return self.raw_data.get(u'commit_id')

    @property
    def commit_url(self):
        return self.raw_data.get(u'commit_url')


class HistoryWrapper(object):

    SCHEMA_VERSION = 1.1
    BOTNAMES = C.DEFAULT_BOT_NAMES

    def __init__(self, issue, usecache=True, cachedir=None, exclude_users=[]):

        self.issue = issue
        self.maincache = cachedir
        self._waffled_labels = None

        if issue.repo.repo_path not in cachedir and u'issues' not in cachedir:
            self.cachefile = os.path.join(
                self.maincache,
                issue.repo.repo_path,
                u'issues',
                to_text(issue.instance.number),
                u'history.pickle'
            )
        elif issue.repo.repo_path not in cachedir:
            self.cachefile = os.path.join(
                self.maincache,
                issue.repo.repo_path,
                u'issues',
                to_text(issue.instance.number),
                u'history.pickle'
            )
        elif u'issues' not in cachedir:
            self.cachefile = os.path.join(
                self.maincache,
                u'issues',
                to_text(issue.instance.number),
                u'history.pickle'
            )
        else:
            self.cachefile = os.path.join(
                self.maincache,
                to_text(issue.instance.number),
                u'history.pickle'
            )

        self.cachedir = os.path.join(
            self.maincache,
            os.path.dirname(self.cachefile)
        )
        if u'issues' not in self.cachedir:
            logging.error(self.cachedir)
            if C.DEFAULT_BREAKPOINTS:
                logging.error(u'breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception(u'')

        if not usecache:
            self.history = self.process()
        else:
            """Building history is expensive and slow"""
            cache = self._load_cache()

            if not self.validate_cache(cache):
                logging.info(u'history cache invalidated, rebuilding')
                self.history = self.process()
                self._dump_cache()
            else:
                logging.info(u'use cached history')
                self.history = cache[u'history'][:]

        if exclude_users:
            tmp_history = [x for x in self.history]
            for x in tmp_history:
                if x[u'actor'] in exclude_users:
                    self.history.remove(x)

        self.history = self._fix_comments_with_no_body(self.history[:])
        self.history = self._fix_commits_with_no_message(self.history[:])
        self.fix_history_tz()
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
        if len(cache['history']) < (len(self.issue.comments) + len(self.issue.labels)):
            return False

        # FIXME label events seem to go missing, so force a rebuild
        if 'needs_info' in self.issue.labels:
            le = [x for x in cache['history'] if x['event'] == 'labeled' and x['label'] == 'needs_info']
            if not le:
                return False

        return True

    def get_rate_limit(self):
        return self.issue.repo.gh.get_rate_limit()

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

        cachedata[u'history'] = self._fix_comments_with_no_body(cachedata[u'history'])
        cachedata[u'history'] = self._fix_event_bytes(cachedata[u'history'])

        return cachedata

    def _dump_cache(self):

        # all events should have datetime.datetime types for created_at
        if [x for x in self.history if not isinstance(x['created_at'], datetime.datetime)]:
            msg = u'found a non-datetime created_at in events data'
            logging.error(msg)
            raise Exception(msg)

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
        for idx,x in enumerate(comments):
            ca = x.created_at
            if not (hasattr(ca, 'tzinfo') and ca.tzinfo):
                ca = pytz.utc.localize(x.created_at)
            nc = {u'body': x.body, u'created_at': ca, u'user': {u'login': x.user.login}}
            comments[idx] = nc
        return comments

    def _fix_comments_with_no_body(self, events):
        '''Make sure all comment events have a body key'''
        for idx,x in enumerate(events):
            if x['event'] == u'commented' and u'body' not in x:
                events[idx][u'body'] = u''
        return events

    def _fix_event_bytes(self, events):
        '''Make sure all event values are strings and not bytes'''
        for ide,event in enumerate(events):
            for k,v in event.items():
                if isinstance(v, bytes):
                    events[ide][k] = v.decode('utf-8')
        return events

    def _fix_commits_with_no_message(self, events):
        for idx,x in enumerate(events):
            if x['event'] == u'committed' and u'message' not in x:
                events[idx][u'message'] = ''
        return events

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

        #import epdb; epdb.st()
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
        comments = [x[u'body'] for x in matching_events
                    if searchterm in x[u'body'].lower()]
        return comments

    def get_user_comments_groupby(self, username, groupby='d'):
        '''Count comments for a user by day/week/month/year'''

        comments = self._find_events_by_actor(
            u'commented',
            username,
            maxcount=999
        )
        groups = {}
        for comment in comments:
            created = comment[u'created_at']
            ts = None
            if groupby == u'd':
                # day
                ts = u'%s-%s-%s' % (created.year, created.month, created.day)
            elif groupby == u'w':
                # week
                ts = u'%s-%s' % (created.year, created.isocalendar()[1])
            elif groupby == u'm':
                # month
                ts = u'%s-%s' % (created.year, created.month)
            elif groupby == u'y':
                # year
                ts = u'%s' % created.year

            if ts:
                if ts not in groups:
                    groups[ts] = 0
                groups[ts] += 1

        return groups


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
            #if event[u'actor'] in self.BOTNAMES:
            #    continue
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

    def is_referenced(self, username):
        """Has this issue ever been referenced by another issue|PR?"""
        matching_events = self._find_events_by_actor(u'referenced', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def is_mentioned(self, username):
        """Has person X ever been mentioned in this issue?"""

        matching_events = self._find_events_by_actor(u'mentioned', username)

        if len(matching_events) > 0:
            return True
        else:
            return False

    def has_viewed(self, username):
        """Has person X ever interacted with issue in any way?"""
        matching_events = self._find_events_by_actor(None, username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def has_commented(self, username):
        """Has person X ever commented on this issue?"""
        matching_events = self._find_events_by_actor(u'commented', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def has_labeled(self, username):
        """Has person X ever labeled issue?"""
        matching_events = self._find_events_by_actor(u'labeled', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def has_unlabeled(self, username):
        """Has person X ever unlabeled issue?"""
        matching_events = self._find_events_by_actor(u'unlabeled', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def has_reviewed(self, username):
        """Has person X ever reviewed issue?"""
        events = [
            u'review_comment',
            u'review_changes_requested',
            u'review_approved',
            u'review_dismissed'
        ]
        for x in events:
            matching_events = self._find_events_by_actor(x, username)
            if len(matching_events) > 0:
                return True
        return False

    def has_subscribed(self, username):
        """Has person X ever subscribed to this issue?"""
        matching_events = self._find_events_by_actor(u'subscribed', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def was_self_assigned(self):
        """Has anyone ever assigned self to this issue?"""
        matching_events = self._find_events_by_actor(u'assigned', None)
        for event in matching_events:
            try:
                if event[u'assignee'] == event[u'assigner']:
                    return True
            except KeyError:
                continue

        return False

    def was_assigned(self, username):
        """Has person X ever been assigned to this issue?"""
        matching_events = self._find_events_by_actor(u'assigned', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def was_unassigned(self, username):
        """Has person X ever been unassigned from this issue?"""
        matching_events = self._find_events_by_actor(u'unassigned', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def was_subscribed(self, username):
        """Has person X ever been subscribed to this issue?"""
        matching_events = self._find_events_by_actor(u'subscribed', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def last_viewed_at(self, username):
        """When did person X last comment?"""
        last_date = None
        for event in reversed(self.history):
            if type(username) != list:
                if event[u'actor'] == username:
                    last_date = event[u'created_at']
                    #print("history - LAST DATE: %s" % last_date)
            else:
                if event[u'actor'] in username:
                    last_date = event[u'created_at']
                    #print("history - LAST DATE: %s" % last_date)
            if last_date:
                break
        return last_date

    def last_notified(self, username):
        """When was this person pinged last in a comment?"""
        if type(username) != list:
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

    def last_commented_at(self, username):
        """When did person X last comment?"""
        last_date = None
        for event in reversed(self.history):
            if event[u'event'] == u'commented':
                if type(username) == list:
                    if event[u'actor'] in username:
                        last_date = event[u'created_at']
                elif event[u'actor'] == username:
                    last_date = event[u'created_at']
            if last_date:
                break
        return last_date

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

    def last_commentor(self):
        """Who commented last?"""
        last_commentor = None
        for event in reversed(self.history):
            if event[u'event'] == u'commented':
                last_commentor = event[u'actor']
                break
        return last_commentor

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
                    #boilerplates.append((comment['created_at'], bp))
                    boilerplates.append(bpc)
                else:
                    boilerplates.append(bp)

        return boilerplates

    def get_boilerplate_comments_content(self, bfilter=None):
        bpcs = self.get_boilerplate_comments()
        bpcs = [x[-1] for x in bpcs]
        return bpcs

    def last_date_for_boilerplate(self, boiler):
        last_date = None
        bps = self.get_boilerplate_comments(dates=True)
        for bp in bps:
            if bp[1] == boiler:
                last_date = bp[0]
        #import epdb; epdb.st()
        return last_date

    @RateLimited
    def _raw_data_from_event(self, event):
        raw_data = event.raw_data.copy()
        return raw_data

    def get_event_from_cache(self, eventid, cache):
        if not cache:
            return None
        matches = [x for x in cache[u'history'] if x[u'id'] == eventid]
        if matches:
            return matches[0]
        else:
            return None

    def process(self):
        """Merge all events into chronological order"""

        # FIXME - load this just once for later reference
        cache = self._load_cache()

        processed_events = []

        events = self.issue.events
        comments = self.issue.comments
        reactions = self.issue.reactions

        processed_events = []
        for ide,event in enumerate(events):

            if isinstance(event, dict):
                if 'id' in event:
                    thisid = event['id']
                else:
                    thisid = '%s_%s_%s' % (self.issue.repo_full_name, self.issue.number, ide)
                event = Event(event, id=thisid)

            cdict = self.get_event_from_cache(event.id, cache)

            if cdict:
                edict = cdict.copy()
            else:
                edict = {}
                edict[u'id'] = event.id
                if not hasattr(event.actor, u'login'):
                    edict[u'actor'] = None
                else:
                    edict[u'actor'] = event.actor.login
                edict[u'event'] = event.event
                edict[u'created_at'] = event.created_at

                if edict[u'event'] in [u'labeled', u'unlabeled']:
                    raw_data = self._raw_data_from_event(event)
                    edict[u'label'] = raw_data.get(u'label', {}).get(u'name', None)
                elif edict[u'event'] == u'mentioned':
                    pass
                elif edict[u'event'] == u'subscribed':
                    pass
                elif edict[u'event'] == u'referenced':
                    edict[u'commit_id'] = event.commit_id
                elif edict[u'event'] == u'assigned':
                    edict[u'assignee'] = event.raw_data[u'assignee'][u'login']
                    edict[u'assigner'] = event.raw_data[u'assigner'][u'login']

            processed_events.append(edict)

        for comment in comments:
            edict = {
                u'id': comment.id,
                u'event': u'commented',
                u'actor': comment.user.login,
                u'created_at': comment.created_at,
                u'body': comment.body,
            }
            processed_events.append(edict)

        for reaction in reactions:
            # 2016-07-26T20:08:20Z
            if not isinstance(reaction, dict):
                # FIXME - not sure what's happening here
                pass
            else:
                edict = {
                    u'id': reaction[u'id'],
                    u'event': u'reacted',
                    u'created_at': reaction[u'created_at'],
                    u'actor': reaction[u'user'][u'login'],
                    u'content': reaction[u'content'],
                }

                processed_events.append(edict)

        # get rid of events with no created_at =(
        processed_events = [x for x in processed_events if x.get(u'created_at')]
        processed_events = self._fix_history_tz(processed_events)

        try:
            # sort by created_at
            sorted_events = sorted(processed_events, key=itemgetter(u'created_at'))
        except Exception as e:
            print(e)
            print('failed to sort events')
            import epdb; epdb.st()

        # return ...
        return sorted_events

    def parse_timestamp(self, timestamp):
        # convert the timestamp the same way the lib does it
        try:
            dt = GithubObject.GithubObject._makeDatetimeAttribute(timestamp)
        except Exception as e:
            print(e)
            import epdb; epdb.st()
        try:
            return dt.value
        except Exception as e:
            print(e)
            import epdb; epdb.st()

    def merge_commits(self, commits):
        for xc in commits:

            '''
            # 'Thu, 12 Jan 2017 15:06:46 GMT'
            tfmt = '%a, %d %b %Y %H:%M:%S %Z'
            ts = xc.last_modified
            dts = datetime.datetime.strptime(ts, tfmt)
            '''
            # committer.date: "2016-12-19T08:05:45Z"
            dts = xc.commit.committer.date
            adts = pytz.utc.localize(dts)

            event = {}
            event[u'id'] = xc.sha
            if hasattr(xc.committer, u'login'):
                event[u'actor'] = xc.committer.login
            else:
                event[u'actor'] = to_text(xc.committer)
            #event[u'created_at'] = dts
            event[u'created_at'] = adts
            event[u'event'] = u'committed'
            event[u'message'] = xc.commit.message
            self.history.append(event)

        self.fix_history_tz()
        self.history = sorted(self.history, key=itemgetter(u'created_at'))

    @property
    def last_commit_date(self):
        events = [x for x in self.history if x[u'event'] == u'committed']
        if events:
            return events[-1][u'created_at']
        else:
            return None

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
                if C.DEFAULT_BREAKPOINTS:
                    logging.error(u'breakpoint!')
                    import epdb; epdb.st()
                else:
                    raise Exception(u'unknown review state')

            event[u'id'] = review[u'id']
            event[u'actor'] = review[u'user'][u'login']
            event[u'created_at'] = self.parse_timestamp(review[u'submitted_at'])
            if u'commit_id' in review:
                event[u'commit_id'] = review[u'commit_id']
            else:
                event[u'commit_id'] = None

            # keep these for shipit analysis
            event[u'body'] = review.get(u'body')

            self.history.append(event)

        self.fix_history_tz()
        self.history = sorted(self.history, key=itemgetter(u'created_at'))

    def merge_history(self, oldhistory):
        '''Combine history from another issue [migration]'''
        self.history += oldhistory
        # sort by created_at
        self.history = sorted(self.history, key=itemgetter(u'created_at'))

    def _fix_history_tz(self, history):

        # make datetime objects for all
        for idx, x in enumerate(history):
            if not hasattr(x['created_at'], 'tzinfo'):
                # convert string to datetime
                if '+' in x['created_at']:
                    # u'2019-08-12T09:44:01+00:00'
                    ts = x['created_at'].split('+')[0]
                    if '.' in ts:
                        ts = datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S.%f')
                    else:
                        ts = datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
                    x['created_at'] = ts
                    history[idx]['created_at'] = ts
                elif x['created_at'].endswith('Z'):
                    # 2017-01-17T06:27:21Z'
                    ts = datetime.datetime.strptime(x['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                    history[idx]['created_at'] = ts
                elif x['created_at'].endswith('Z'):
                    ts = datetime.datetime.strptime(x['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                    history[idx]['created_at'] = ts
                else:
                    ts = datetime.datetime.strptime(x['created_at'], '%Y-%m-%dT%H:%M:%S')
                    history[idx]['created_at'] = ts

        # set to UTC
        for idx, x in enumerate(history):
            if not x[u'created_at'].tzinfo:
                ats = pytz.utc.localize(x[u'created_at'])
                history[idx][u'created_at'] = ats

        return history

    def fix_history_tz(self):
        '''History needs to be timezone aware!!!'''
        self.history = self._fix_history_tz(self.history)

    def get_changed_labels(self, prefix=None, bots=[]):
        '''make a list of labels that have been set/unset'''
        labeled = []
        for event in self.history:
            if bots:
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

            ts = x[u'updated_at']
            ts = datetime.datetime.strptime(ts, u'%Y-%m-%dT%H:%M:%SZ')
            ts = pytz.utc.localize(ts)

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
