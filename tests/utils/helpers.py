from contextlib import contextmanager
import shutil
import tempfile

from tests.utils.issue_mock import IssueMock
from tests.utils.repo_mock import RepoMock
from ansibullbot.issuewrapper import IssueWrapper
from ansibullbot.historywrapper import HistoryWrapper

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
        iw.load_update_fetch_files = lambda: []
        # hook in here to avoid github api calls
        iw._events = iw._parse_events(issue.events)
        iw._commits = issue.commits

        # pre-create history to avoid github api calls
        history = HistoryWrapper(iw.events, iw.labels, iw.updated_at, cachedir=cachedir, usecache=False)
        iw._history = history

        if issue.commits:
            iw._history.merge_commits(issue.commits)

        yield iw

    finally:
        shutil.rmtree(cachedir)
