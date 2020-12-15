class RepoIssuesIterator:

    def __init__(self, repo, numbers, issuecache={}):
        self.repo = repo
        self.numbers = numbers
        self.issuecache = issuecache
        self.i = 0

    def __iter__(self):
        return self

    def __next__(self):

        if self.i > (len(self.numbers) - 1):
            raise StopIteration()

        thisnum = self.numbers[self.i]
        self.i += 1
        if thisnum in self.issuecache:
            issue = self.issuecache[thisnum]
        else:
            issue = self.repo.get_issue(thisnum)

        return issue
