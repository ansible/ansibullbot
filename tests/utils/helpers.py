from contextlib import contextmanager
import json
import shutil
import tempfile

from tests.utils.issue_mock import IssueMock
from tests.utils.repo_mock import RepoMock
from ansibullbot.wrappers.issuewrapper import IssueWrapper
from ansibullbot.wrappers.historywrapper import HistoryWrapper

@contextmanager
def get_issue(datafile, statusfile):
    cachedir = tempfile.mkdtemp(prefix='ansibot_tests_')

    try:
        issue = IssueMock(datafile)
        issue.html_url = issue.html_url.replace('issues', 'pull')
        repo = RepoMock()
        repo.repo_path = 'ansible/ansible'

        iw = IssueWrapper(repo=repo, cachedir=cachedir, issue=issue)

        # disable this completely
        iw.load_update_fetch = lambda x: []
        # hook in here to avoid github api calls
        iw._comments = issue.comments
        iw._events = issue.events
        iw._reactions = issue.reactions
        iw._commits = issue.commits

        # pre-load status to avoid github api calls
        with open(statusfile, 'rb') as status:
            iw._pr_status = json.loads(status.read())

        # pre-create history to avoid github api calls
        history = HistoryWrapper(iw, cachedir=cachedir, usecache=False)
        iw._history = history

        # merge_commits(self, commits)
        if issue.commits:
            iw._history.merge_commits(issue.commits)

        yield iw

    finally:
        shutil.rmtree(cachedir)
