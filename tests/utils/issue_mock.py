#!/usr/bin/env python

import yaml
from lib.utils.timetools import timeobj_from_timestamp

class LabelMock(object):
    name = None
    color = None

class CommentMock(object):
    id = None
    actor = None
    user = None
    body = None
    created_at = None

class EventMock(object):
    raw_data = {}
    id = None
    event = None # labeled, renamed, closed, etc ...
    actor = None
    created_at = None
    # unique to each event type ...
    label = None
    rename = None

class ActorMock(object):
    id = None
    login = None    

class RequesterMock(object):
    rdata = "{}"
    def requstJson(self, method, url, headers=None):
        return (200, "foo", self.rdata)

class IssueMock(object):
    """Mocks a pygithub object with data from a yaml file"""

    def __init__(self, datafile):
        self.calls = []
        self.ydata = None
        self.load_data(datafile)

    def load_data(self, datafile):
        ydata = None
        fdata = None
        with open(datafile, 'rb') as f:
            fdata = f.read()
        if fdata:
            self.ydata = yaml.load(fdata)        
        else:
            self.ydata = {}

        self.assignee = None
        self.body = self.ydata.get('body', '')
        self.closed_at = None
        self.closed_by = None
        self.comments = []
        self.comments_url = None
        self.created_at = self.ydata.get('created_at')
        self._events = self.ydata.get('events', [])
        self.events = []
        self.events_url = None
        self.html_url = self.ydata.get('html_url', 'https://github.com/ansible/ansible-modules-core/issues/1')
        self.id = int(self.ydata.get('number', 1))
        self.labels = []
        self.labels_url = None
        self.milestone = None
        self.number = int(self.ydata.get('number', 1))
        self.pull_request = None
        self.repository = None
        self.state = self.ydata.get('state', 'open')
        self.title = self.ydata.get('title', '')
        self.updated_at = None
        self.url = 'https://api.github.com/repos/ansible/ansible-modules-%s/issues/%s' % ('core', self.id)
        self.user = ActorMock()
        self.user.login = self.ydata.get('submitter', "nobody")
        self._identity = self.number

        # need to mock this for reactions fetching
        self._requester = RequesterMock()

        # build the mocked event data
        self._load_events()


    def _load_events(self):
        # parse the yaml events into mocked objects
        for ev in self._events:

            # make a mocked actor object
            actor = ActorMock()
            actor.login = ev['actor']['login']

            # build an event -or- a comment
            if ev['event'] == 'commented':
                comment = CommentMock()
                comment.actor = actor
                comment.user = actor
                comment.body = ev['body']
                comment.created_at = ev['created_at']
                self.comments.append(comment)
            else:
                event = EventMock()
                event.raw_data = ev.copy()
                event.actor = actor
                event.id = ev['id']
                event.event = ev['event']
                event.created_at = ev['created_at']

                if ev['event'] == 'labeled' or ev['event'] == 'unlabeled':
                    label = LabelMock()
                    label.name = ev['label']['name']
                    event.label = label
                    if ev['event'] == 'labeled' and not label in self.labels:
                        self.labels.append(label)
                    if ev['event'] == 'unlabeled' and label in self.labels:
                        self.labels.append(remove)
                    
                else:
                    import epdb; epdb.st()

                self.events.append(event)
        #import epdb; epdb.st()

    def add_to_labels(self, *labels):
        self.calls.append(('add_to_labels', labels))

    def create_comment(self, body):
        self.calls.append(('create_comment', body))

    def delete_labels(self):
        self.calls.append(('delete_labels'))

    def edit(self, title=None, body=None, assignee=None, state=None, milestone=None, labels=None):
        self.calls.append(('edit', title, body, assignee, state, milestone, labels))

    def get_comment(self, id):
        self.calls.append(('get_comment', id))

    def get_comments(self, since=None):
        self.calls.append(('get_comments', since))
        return list(self.comments)

    def get_events(self):
        self.calls.append(('get_events'))
        return self.events

    def get_labels(self):
        self.calls.append(('get_labels'))

    def remove_from_labels(self, label):
        self.calls.append(('remove_from_labels', label))

    def set_labels(self, *labels):
        self.calls.append(('set_labels', labels))

    def _useAttributes(self):
        self.calls.append(('_useAttributes'))
