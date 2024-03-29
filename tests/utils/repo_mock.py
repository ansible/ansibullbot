from collections import namedtuple


class SubRepo:
    def __init__(self, assignees=None):
        self.assignees = assignees or []

    def has_in_assignees(self, user):
        return user in self.assignees


class RepoMock:
    issues = {}

    def __init__(self, assignees=None):
        self.repo = SubRepo(assignees)

    def get_issue(self, issueid):
        return self.issues.get(issueid, None)

    def get_pullrequest(self, issueid):
        return namedtuple('PullRequest', ['draft'])(draft=False)

    def get_issues(self):
        return [issues[x] for x in issues.keys()]

    def has_in_assignees(self, login):
        return True
