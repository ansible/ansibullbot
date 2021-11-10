import unittest

from ansibullbot.plugins.shipit import get_automerge_facts


class HistoryWrapperMock:
    history = None
    def __init__(self):
        self.history = []


class IssueWrapperMock:
    _is_pullrequest = False
    _pr_files = []
    _wip = False
    _history = None
    _submitter = 'bob'

    def __init__(self, org, repo, number):
        self._history = HistoryWrapperMock()
        self.org = org
        self.repo = repo
        self.number = number

    def is_pullrequest(self):
        return self._is_pullrequest

    def add_comment(self, user, body):
        payload = {'actor': user, 'event': 'commented', 'body': body}
        self.history.history.append(payload)

    def add_file(self, filename, content):
        mf = MockFile(filename, content=content)
        self._pr_files.append(mf)

    @property
    def wip(self):
        return self._wip

    @property
    def files(self):
        return [x.filename for x in self._pr_files]

    @property
    def history(self):
        return self._history

    @property
    def submitter(self):
        return self._submitter

    @property
    def html_url(self):
        if self.is_pullrequest():
            return 'https://github.com/%s/%s/pulls/%s' % (self.org, self.repo, self.number)
        else:
            return 'https://github.com/%s/%s/issues/%s' % (self.org, self.repo, self.number)


class MockFile:
    def __init__(self, name, content=''):
        self.filename = name
        self.content = content


class TestAutomergeFacts(unittest.TestCase):

    def test_automerge_if_shipit(self):
        # if shipit and other tests pass, automerge should be True
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW._is_pullrequest = True
        IW.add_comment('jane', 'shipit')
        meta = {
            'ci_stale': False,
            'ci_state': 'success',
            'has_ci': True,
            'is_new_directory': False,
            'is_module': True,
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_info': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'is_backport': False,
            'mergeable': True,
            'merge_commits': False,
            'has_commit_mention': False,
            'shipit': True,
            'supershipit': True,
            'component_matches': [
                {
                    'repo_filename': 'foo',
                    'supershipit': ['jane', 'doe'],
                    'support': 'community'
                }
            ],
            'component_support': ['community']
        }
        meta['module_match'] = meta['component_matches'][:]
        amfacts = get_automerge_facts(IW, meta)
        assert amfacts['automerge']
        assert 'automerge_status' in amfacts

    def test_not_automerge_if_not_shipit(self):
        # if not shipit, automerge should be False
        IW = IssueWrapperMock('ansible', 'ansible', 1)
        IW._is_pullrequest = True
        IW.add_comment('jane', 'shipit')
        meta = {
            'ci_stale': False,
            'ci_state': 'success',
            'has_ci': True,
            'is_new_directory': False,
            'is_module': True,
            'is_module_util': False,
            'is_new_module': False,
            'is_needs_info': False,
            'is_needs_rebase': False,
            'is_needs_revision': False,
            'is_backport': False,
            'mergeable': True,
            'merge_commits': False,
            'has_commit_mention': False,
            'shipit': False,
            'supershipit': False,
            'component_matches': [
                {
                    'repo_filename': 'foo',
                    'supershipit': ['jane', 'doe'],
                    'support': 'community'
                }
            ],
            'component_support': ['community']
        }
        meta['module_match'] = meta['component_matches'][:]
        amfacts = get_automerge_facts(IW, meta)
        assert not amfacts['automerge']
        assert 'automerge_status' in amfacts
