#!/usr/bin/env python

import logging
import os
import shutil
import unittest
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper
from ansibullbot.wrappers.issuewrapper import IssueWrapper


class GithubMock(object):
    def get_repo(self, full_name):
        gr = GithubRepoMock(full_name)
        return gr


class GithubRepoMock(object):
    repo = None
    full_name = None

    def __init__(self, full_name):
        self.full_name = full_name

    def get_issue(self, number):
        issue = GithubIssueMock()
        issue.number = number
        return issue

class GithubUserMock(object):

    @property
    def login(self):
        return u'testuser'


class GithubIssueMock(object):
    number = 1
    title = u'test ticket'
    state = u'open'
    _body = [
        u"##### ISSUE TYPE",
        u"Bug Report"
        u"##### COMPONENT NAME",
        u"cron module",
        u"##### ANSIBLE VERSION",
        u"2.3",
        u"##### ENVIRONMENT",
        u"N/A",
        u"##### SUMMARY",
        u"It's broken",
        u"##### EXPECTED RESULTS",
        u"N/A",
        u"##### ACTUAL RESULTS"
        u"N/A",
    ]
    body = u'\n'.join(_body)

    def get_raw_data(self):
        data = {
            u'number': self.number
        }
        return data

    @property
    def html_url(self):
        return u'https://github.com/test/test/issues/%s' % self.number

    @property
    def user(self):
        return GithubUserMock()

    @property
    def created_at(self):
        return u'xxxx-xx-xx:xx:xx:xx'

    @property
    def closed_at(self):
        return u'xxxx-xx-xx:xx:xx:xx'

    @property
    def updated_at(self):
        return u'xxxx-xx-xx:xx:xx:xx'


class FileIndexerMock(object):
    def get_file_content(self, filename):
        fd = [
            u"##### ISSUE TYPE",
            u"##### COMPONENT NAME",
            u"##### ANSIBLE VERSION",
            u"##### ENVIRONMENT",
            u"##### SUMMARY",
            u"##### EXPECTED RESULTS",
            u"##### ACTUAL RESULTS"
        ]
        return u'\n'.join(fd)


class TestIssueWrapperBase(unittest.TestCase):
    def setUp(self):
        cache = '/tmp/testcache'
        if os.path.isdir(cache):
            shutil.rmtree(cache)
        os.makedirs(cache)

        gh = GithubMock()
        ghw = GithubWrapper(gh, cachedir=cache)

        gr = ghw.get_repo('test/test', verbose=False)
        # FIXME - this should return a wrapped issue
        gi = gr.get_issue(1)
        self.iw = IssueWrapper(github=gh, repo=gr, issue=gi, cachedir=cache)
        self.iw.file_indexer = FileIndexerMock()



class TestIssueWrapperProperties(TestIssueWrapperBase):
    def runTest(self):
        self.assertEqual(self.iw.cachedir, u'/tmp/testcache')
        self.assertEqual(self.iw.number, 1)
        self.assertEqual(self.iw.title, u'test ticket')
        self.assertEqual(self.iw.state, u'open')
        self.assertEqual(self.iw.repo_full_name, u'test/test')
        self.assertEqual(self.iw.submitter, u'testuser')
        self.assertEqual(self.iw.created_at, u'xxxx-xx-xx:xx:xx:xx')
        self.assertEqual(self.iw.updated_at, u'xxxx-xx-xx:xx:xx:xx')
        self.assertEqual(self.iw.closed_at, u'xxxx-xx-xx:xx:xx:xx')
        assert hasattr(self.iw, u'template_data')

class TestIssueWrapperTemplateData(TestIssueWrapperBase):
    def runTest(self):
        td = self.iw.template_data
        self.assertEqual(td['ansible version'], u'2.3')
        self.assertEqual(td['issue type'], u"bug report")
        self.assertEqual(td['summary'], u"It's broken")
        self.assertEqual(td['component_raw'], u"cron module")
        self.assertEqual(td['component name'], u"cron")
