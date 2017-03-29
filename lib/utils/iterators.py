#!/usr/bin/env python


class RepoIssuesIterator(object):

    def __init__(self, repo, numbers):
        self.repo = repo
        self.numbers = numbers
        self.i = 0

    def __iter__(self):
        return self

    def next(self):

        if self.i > (len(self.numbers) - 1):
            raise StopIteration()

        thisnum = self.numbers[self.i]
        self.i += 1
        issue = self.repo.get_issue(thisnum)
        return issue

