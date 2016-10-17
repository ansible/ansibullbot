#!/usr/bin/env python

import os
import pickle
import sys
import time
from datetime import datetime
from operator import itemgetter
from github import GithubObject

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
        self.cachefile = os.path.join(self.maincache, str(issue.instance.number), 'history.pickle')
        self.cachedir = os.path.dirname(self.cachefile)
        if not usecache:
            self.history = self.process()
        else:
            """Building history is expensive and slow"""
            cache = self._load_cache()
            if not cache:
                self.history = self.process()
                self._dump_cache()
            else:
                if cache['updated_at'] >= self.issue.instance.updated_at:
                    self.history = cache['history']
                else:
                    self.history = self.process()
                    self._dump_cache()

        if exclude_users:
            tmp_history = [x for x in self.history]
            for x in tmp_history:
                if x['actor'] in exclude_users:
                    self.history.remove(x)
        #import epdb; epdb.st()

    def _load_cache(self):
        if not os.path.isdir(self.cachedir):
            os.makedirs(self.cachedir)
        if not os.path.isfile(self.cachefile):
            return None            
        try:
            with open(self.cachefile, 'rb') as f:
                cachedata = pickle.load(f)
        except Exception as e:
            cachedata = None
        return cachedata

    def _dump_cache(self):
        if not os.path.isdir(self.cachedir):
            os.makedirs(self.cachedir)
        cachefile = os.path.join(self.cachedir, 'history.pickle')

        # keep the timestamp
        cachedata = {'updated_at': self.issue.instance.updated_at,
                     'history': self.history}

        try:
            with open(self.cachefile, 'wb') as f:
                pickle.dump(cachedata, f)
        except Exception as e:
            import epdb; epdb.st()
            pass

    def _find_events_by_actor(self, eventname, actor, maxcount=1):
        matching_events = []
        for event in self.history:
            if event['event'] == eventname or not eventname:
                # allow actor to be a list or a string
                if type(actor) != list and event['actor'] == actor:
                    matching_events.append(event)
                elif type(actor) == list and event['actor'] in actor:
                    matching_events.append(event)
                if len(matching_events) == maxcount:
                    break
        return matching_events

    def get_user_comments(self, username):
        """Get all the comments from a user"""
        matching_events = self._find_events_by_actor('commented', 
                                                    username, 
                                                    maxcount=999)
        comments = [x['body'] for x in matching_events]
        return comments

    def get_user_comments_groupby(self, username, groupby='d'):
        '''Count comments for a user by day/week/month/year'''

        comments = self._find_events_by_actor('commented', 
                                              username, 
                                              maxcount=999)
        groups = {}
        for comment in comments:
            created = comment['created_at']
            ts = None
            if groupby == 'd':
                # day
                ts = '%s-%s-%s' % (created.year, created.month, created.day)
            elif groupby == 'w':
                # week
                ts = '%s-%s' % (created.year, created.isocalendar()[1])
            elif groupby == 'm':
                # month
                ts = '%s-%s' % (created.year, created.month)
            elif groupby == 'y':
                # year
                ts = '%s' % (created.year)

            if ts:
                if ts not in groups:
                    groups[ts] = 0
                groups[ts] += 1
 
        return groups

    def get_commands(self, username, command_keys):
        """Given a list of phrase keys, return a list of phrases used"""
        commands = []

        '''
        comments = self.get_user_comments(username)
        for x in comments:
            for y in command_keys:
                if y in x and not '!' + y in x:
                    commands.append(y)
                    break        
        '''

        comments = self._find_events_by_actor('commented', username, maxcount=999)
        labels = self._find_events_by_actor('labeled', username, maxcount=999)
        unlabels = self._find_events_by_actor('unlabeled', username, maxcount=999)
        events = comments + labels + unlabels
        events = sorted(events, key=itemgetter('created_at')) 
        for event in events:
            if event['event'] == 'commented':
                for y in command_keys:
                    if y in event['body'] and not '!' + y in event['body']:
                        commands.append(y)
            elif event['event'] == 'labeled':
                if event['label'] in command_keys:
                    commands.append(event['label'])
            elif event['event'] == 'unlabeled':
                if event['label'] in command_keys:
                    commands.append('!' + event['label'])
        #import epdb; epdb.st()
        return commands

    def is_referenced(self, username):
        """Has this issue ever been referenced by another issue|PR?"""
        matching_events = self._find_events_by_actor('referenced', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def is_mentioned(self, username):
        """Has person X ever been mentioned in this issue?"""
        matching_events = self._find_events_by_actor('mentioned', username)
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
        matching_events = self._find_events_by_actor('commented', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def has_subscribed(self, username):
        """Has person X ever subscribed to this issue?"""
        matching_events = self._find_events_by_actor('subscribed', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def was_assigned(self, username):
        """Has person X ever been assigned to this issue?"""
        matching_events = self._find_events_by_actor('assigned', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def was_unassigned(self, username):
        """Has person X ever been unassigned from this issue?"""
        matching_events = self._find_events_by_actor('unassigned', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def was_subscribed(self, username):
        """Has person X ever been subscribed to this issue?"""
        matching_events = self._find_events_by_actor('subscribed', username)
        if len(matching_events) > 0:
            return True
        else:
            return False

    def last_viewed_at(self, username):
        """When did person X last comment?"""
        last_date = None
        for event in reversed(self.history):
            if type(username) != list:
                if event['actor'] == username:
                    last_date = event['created_at']
                    #print("history - LAST DATE: %s" % last_date)
            else:
                if event['actor'] in username:
                    last_date = event['created_at']
                    #print("history - LAST DATE: %s" % last_date)
            if last_date:
                break
        return last_date

    def last_notified(self, username):
        """When was this person pinged last in a comment?"""
        if type(username) != list:
            username = [username]
        username = ['@' + x for x in username]
        last_notification = None
        comments = [x for x in self.history if x['event'] == 'commented']
        for comment in comments:
            for un in username:
                if un in comment['body']:
                    if not last_notification:
                        last_notification = comment['created_at']
                    else:
                        if comment['created_at'] > last_notification:
                            last_notification = comment['created_at']
        #import epdb; epdb.st()
        return last_notification

    def last_commented_at(self, username):
        """When did person X last comment?"""
        last_date = None
        for event in reversed(self.history):
            if event['event'] == 'commented':
                if type(username) == list:
                    if event['actor'] in username:
                        last_date = event['created_at']
                elif event['actor'] == username:
                    last_date = event['created_at']
            if last_date:
                break
        return last_date

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
        #import epdb; epdb.st()
        return last_comment

    def last_commentor(self):
        """Who commented last?"""
        last_commentor = None
        for event in reversed(self.history):
            if event['event'] == 'commented':
                last_commentor = event['actor']
                break
        return last_commentor

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

    def was_labeled(self, label=None):
        """Were labels -ever- applied to this issue?"""
        labeled = False
        for event in self.history:
            if event['event'] == 'labeled':
                if label and event['label'] == label:
                    labeled = True
                    break
                elif not label:
                    labeled = True
                    break
        return labeled

    def was_unlabeled(self, label=None):
        """Were labels -ever- unapplied from this issue?"""
        labeled = False
        for event in self.history:
            if event['event'] == 'unlabeled':
                if label and event['label'] == label:
                    labeled = True
                    break
                elif not label:
                    labeled = True
                    break
        return labeled

    def process(self):
        """Merge all events into chronological order"""

        processed_events = []

        events = self.issue.get_events()
        comments = self.issue.get_comments()
        reactions = self.issue.get_reactions()

        processed_events = []
        for ide,event in enumerate(events):
            edict = {}
            edict['id'] = event.id
            if not hasattr(event.actor, 'login'):
                edict['actor'] = None
            else:
                edict['actor'] = event.actor.login
            edict['event'] = event.event
            edict['created_at'] = event.created_at
            raw_data = event.raw_data.copy()
            if edict['event'] in ['labeled', 'unlabeled']:
                edict['label'] = raw_data.get('label', {}).get('name', None)
            elif edict['event'] == 'mentioned':
                pass
            elif edict['event'] == 'subscribed':
                pass
            elif edict['event'] == 'referenced':
                edict['commit_id'] = event.commit_id
                #edict['body'] = event.body
            processed_events.append(edict)

        for idc,comment in enumerate(comments):
            edict = {}
            edict['id'] = comment.id
            edict['event'] = 'commented'
            edict['actor'] = comment.user.login
            edict['created_at'] = comment.created_at
            edict['body'] = comment.body
            processed_events.append(edict)

        for reaction in reactions:
            # 2016-07-26T20:08:20Z
            edict = {}
            edict['id'] = reaction['id']
            edict['event'] = 'reacted'
            edict['created_at'] = reaction['created_at']
            edict['actor'] = reaction['user']['login']
            edict['content'] = reaction['content']

            # convert the timestamp the same way the lib does it
            if type(edict['created_at']) in [unicode, str]:
                dt = GithubObject.GithubObject.\
                        _makeDatetimeAttribute(edict['created_at'])
                edict['created_at'] = dt.value
                #import epdb; epdb.st()

            processed_events.append(edict)

        # sort by created_at
        sorted_events = sorted(processed_events, key=itemgetter('created_at')) 

        # return ...
        return sorted_events
