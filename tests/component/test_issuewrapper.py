import logging
import os
import shutil
import unittest
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper
from ansibullbot.wrappers.issuewrapper import IssueWrapper


class GithubMock:
    def get_repo(self, full_name):
        gr = GithubRepoMock(full_name)
        return gr


class GithubRepoMock:
    repo = None
    full_name = None

    def __init__(self, full_name):
        self.full_name = full_name

    def get_issue(self, number):
        issue = GithubIssueMock()
        issue.number = number
        return issue

class GithubUserMock:

    @property
    def login(self):
        return 'testuser'


class GithubIssueMock:
    number = 1
    title = 'test ticket'
    state = 'open'
    _body = [
        "##### ISSUE TYPE",
        "Bug Report"
        "##### COMPONENT NAME",
        "cron module",
        "##### ANSIBLE VERSION",
        "2.3",
        "##### ENVIRONMENT",
        "N/A",
        "##### SUMMARY",
        "It's broken",
        "##### EXPECTED RESULTS",
        "N/A",
        "##### ACTUAL RESULTS"
        "N/A",
    ]
    body = '\n'.join(_body)

    def get_raw_data(self):
        data = {
            'number': self.number
        }
        return data

    @property
    def html_url(self):
        return 'https://github.com/test/test/issues/%s' % self.number

    @property
    def user(self):
        return GithubUserMock()

    @property
    def created_at(self):
        return 'xxxx-xx-xx:xx:xx:xx'

    @property
    def closed_at(self):
        return 'xxxx-xx-xx:xx:xx:xx'

    @property
    def updated_at(self):
        return 'xxxx-xx-xx:xx:xx:xx'


class GitRepoWrapperMock:
    def get_file_content(self, filename):
        fd = [
            "##### ISSUE TYPE",
            "##### COMPONENT NAME",
            "##### ANSIBLE VERSION",
            "##### ENVIRONMENT",
            "##### SUMMARY",
            "##### EXPECTED RESULTS",
            "##### ACTUAL RESULTS"
        ]
        return '\n'.join(fd)


class TestIssueWrapperBase(unittest.TestCase):
    def setUp(self):
        cache = '/tmp/testcache'
        if os.path.isdir(cache):
            shutil.rmtree(cache)
        os.makedirs(cache)

        gh = GithubMock()
        ghw = GithubWrapper(gh, cachedir=cache)

        gr = ghw.get_repo('test/test')
        # FIXME - this should return a wrapped issue
        gi = gr.get_issue(1)
        self.iw = IssueWrapper(github=gh, repo=gr, issue=gi, cachedir=cache)
        self.iw.gitrepo = GitRepoWrapperMock()



class TestIssueWrapperProperties(TestIssueWrapperBase):
    def runTest(self):
        self.assertEqual(self.iw.cachedir, '/tmp/testcache')
        self.assertEqual(self.iw.number, 1)
        self.assertEqual(self.iw.title, 'test ticket')
        self.assertEqual(self.iw.state, 'open')
        self.assertEqual(self.iw.repo_full_name, 'test/test')
        self.assertEqual(self.iw.submitter, 'testuser')
        self.assertEqual(self.iw.created_at, 'xxxx-xx-xx:xx:xx:xx')
        self.assertEqual(self.iw.updated_at, 'xxxx-xx-xx:xx:xx:xx')
        self.assertEqual(self.iw.closed_at, 'xxxx-xx-xx:xx:xx:xx')
        assert hasattr(self.iw, 'template_data')

class TestIssueWrapperTemplateData(TestIssueWrapperBase):
    def runTest(self):
        td = self.iw.template_data
        self.assertEqual(td['ansible version'], '2.3')
        self.assertEqual(td['issue type'], "bug report")
        self.assertEqual(td['summary'], "It's broken")
        self.assertEqual(td['component_raw'], "cron module")
        self.assertEqual(td['component name'], "cron")
