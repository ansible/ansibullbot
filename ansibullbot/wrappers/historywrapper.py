#!/usr/bin/env python

import datetime
import logging
import os
import pytz
from operator import itemgetter

import six

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


class HistoryWrapper(object):

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
            if not cache:
                logging.info(u'empty history cache, rebuilding')
                self.history = self.process()
                logging.info(u'dumping newly created history cache')
                self._dump_cache()
            else:
                if cache[u'updated_at'] >= self.issue.instance.updated_at:
                    logging.info(u'use cached history')
                    self.history = cache[u'history']
                else:
                    logging.info(u'history out of date, updating')
                    self.history = self.process()
                    logging.info(u'dumping newly created history cache')
                    self._dump_cache()

        if exclude_users:
            tmp_history = [x for x in self.history]
            for x in tmp_history:
                if x[u'actor'] in exclude_users:
                    self.history.remove(x)

        self.fix_history_tz()
        self.history = sorted(self.history, key=itemgetter(u'created_at'))

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
        return cachedata

    def _dump_cache(self):
        if not os.path.isdir(self.cachedir):
            os.makedirs(self.cachedir)

        # keep the timestamp
        cachedata = {u'updated_at': self.issue.instance.updated_at,
                     u'history': self.history}

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

    def _find_events_by_actor(self, eventname, actor, maxcount=1):
        matching_events = []
        for event in self.history:
            if event[u'event'] == eventname or not eventname:
                # allow actor to be a list or a string
                if type(actor) != list and event[u'actor'] == actor:
                    matching_events.append(event)
                elif type(actor) == list and event[u'actor'] in actor:
                    matching_events.append(event)
                if len(matching_events) == maxcount:
                    break

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

    def get_commands(self, username, command_keys, timestamps=False, uselabels=True, botnames=[]):
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
            if event[u'actor'] in botnames:
                continue
            if event[u'event'] == u'commented':
                for y in command_keys:
                    if event[u'body'].startswith(u'_From @'):
                        continue
                    if y != u'bot_broken' and u'bot_broken' in event[u'body']:
                        continue
                    if y in event[u'body'] and not u'!' + y in event[u'body']:
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

    def get_component_commands(self, command_key='!component', botnames=[]):
        """Given a list of phrase keys, return a list of phrases used"""
        commands = []

        comments = self._find_events_by_actor(
            u'commented',
            None,
            maxcount=999
        )
        events = sorted(comments, key=itemgetter(u'created_at'))

        for event in events:
            if event[u'actor'] in botnames:
                continue
            if event[u'event'] == u'commented':
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

    def get_boilerplate_comments(self, botname='ansibot', botnames=None, dates=False, content=True):
        boilerplates = []
        if botnames:
            comments = self._find_events_by_actor(u'commented',
                                                  botnames,
                                                  maxcount=999)
        else:
            comments = self._find_events_by_actor(u'commented',
                                                  botname,
                                                  maxcount=999)
        for comment in comments:
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

    def get_boilerplate_comments_content(self, botname='ansibot', bfilter=None):
        boilerplates = []
        comments = self._find_events_by_actor(u'commented',
                                              botname,
                                              maxcount=999)
        for comment in comments:
            if u'boilerplate:' in comment[u'body']:
                lines = [x for x in comment[u'body'].split(u'\n')
                         if x.strip() and u'boilerplate:' in x]
                bp = lines[0].split()[2]
                if bfilter:
                    if bp == bfilter:
                        boilerplates.append(comment[u'body'])
                else:
                    boilerplates.append(comment[u'body'])
        return boilerplates

    def last_date_for_boilerplate(self, boiler, botname='ansibot'):
        last_date = None
        bps = self.get_boilerplate_comments(botname=botname, dates=True)
        for bp in bps:
            if bp[1] == boiler:
                last_date = bp[0]
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
        for event in events:

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

                if isinstance(edict[u'created_at'], six.binary_type):
                    edict[u'created_at'] = to_text(edict[u'created_at'])

                # convert the timestamp the same way the lib does it
                if isinstance(edict[u'created_at'], six.text_type):
                    edict[u'created_at'] = self.parse_timestamp(
                        edict[u'created_at']
                    )

                processed_events.append(edict)

        # sort by created_at
        sorted_events = sorted(processed_events, key=itemgetter(u'created_at'))

        # return ...
        return sorted_events

    def parse_timestamp(self, timestamp):
        # convert the timestamp the same way the lib does it
        dt = GithubObject.GithubObject._makeDatetimeAttribute(timestamp)
        return dt.value

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

    def fix_history_tz(self):
        '''History needs to be timezone aware!!!'''
        for idx, x in enumerate(self.history):
            if not x[u'created_at'].tzinfo:
                ats = pytz.utc.localize(x[u'created_at'])
                self.history[idx][u'created_at'] = ats

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
