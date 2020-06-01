import yaml


class ActorMock(object):
    id = None
    login = None


class CommitterMock(object):
    date = None
    login = None


class CommitBottomMock(object):
    committer = CommitterMock()
    message = ""


class CommitMock(object):
    commit = CommitBottomMock()
    committer = commit.committer
    sha = None


class LabelMock(object):
    name = None


class RequesterMock(object):
    rdata = "{}"

    def requestJson(self, method, url, headers=None):
        return (200, "foo", self.rdata)


class IssueMock(object):
    """Mocks a pygithub object with data from a yaml file"""

    def __init__(self, datafile):
        self.calls = []
        self.ydata = None
        self.load_data(datafile)

    @property
    def commits(self):
        for x in self.events:
            if not x['event'] == 'committed':
                continue
            commit = CommitMock()
            commit.commit.committer.date = x['created_at']
            commit.commit.committer.login = x['actor']['login']
            self._commits.append(commit)
        return self._commits

    @property
    def comments(self):
        return self.get_events()

    @property
    def labels(self):
        for ev in self.events:
            if ev['event'] == 'labeled' or ev['event'] == 'unlabeled':
                label = LabelMock()
                label.name = ev['label']['name']
                if ev['event'] == 'labeled':
                    current = [x.name for x in self._labels if x.name == label.name]
                    if not current:
                        self._labels.append(label)
                #elif ev['event'] == 'unlabeled':
                #    current = [x.name for x in self.labels if x.name == label.name]
                #    if current:
                #        for idx, x in enumerate(self.labels):
                #            if x.name == label.name:
                #                del self._labels[idx]
                #                break
        return self._labels

    def load_data(self, datafile):
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
        self.comments_url = None
        self.created_at = self.ydata.get('created_at')
        self.events = self.ydata.get('events', [])
        self._commits = []
        self.events_url = None
        self.files = None
        self.html_url = self.ydata.get(
            'html_url',
            'https://github.com/ansible/ansible-modules-core/issues/1'
        )
        self.id = int(self.ydata.get('number', 1))
        self._labels = []
        self.labels_url = None
        self.milestone = None
        self.number = int(self.ydata.get('number', 1))
        self.pull_request = None
        self.repository = None
        self.reactions = []
        self.state = self.ydata.get('state', 'open')
        self.title = self.ydata.get('title', '')
        self.updated_at = None
        self.url = 'https://api.github.com/repos/ansible/ansible/issues/%s' % self.id
        self.user = ActorMock()
        self.user.login = self.ydata.get('submitter', "nobody")
        self._identity = self.number

        # need to mock this for reactions fetching
        self._requester = RequesterMock()

    def add_to_labels(self, *labels):
        self.calls.append(('add_to_labels', labels))

    def create_comment(self, body):
        self.calls.append(('create_comment', body))

    def edit(self, title=None, body=None, assignee=None, state=None, milestone=None, labels=None):
        self.calls.append(('edit', title, body, assignee, state, milestone, labels))

    def get_events(self):
        self.calls.append(('get_events'))
        return self.events

    def get_labels(self):
        self.calls.append(('get_labels'))

    def get_pullrequest_status(self):
        return []

    def get_pullrequest(self):
        self.calls.append('get_pullrequest')

    def remove_from_labels(self, label):
        self.calls.append(('remove_from_labels', label))

    def set_labels(self, *labels):
        self.calls.append(('set_labels', labels))

    def get_commits(self):
        self.calls.append('get_commits')
        return self.commits
