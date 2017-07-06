#!/usr/bin/env python


class RepoMock(object):
    issues = {}
    def get_issue(self, issueid):
        return self.issues.get(issueid, None)
    def get_issues(self):
        return [issues[x] for x in issues.keys()]
