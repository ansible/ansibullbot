#!/usr/bin/env python

from __future__ import print_function

from github.GithubException import GithubException
import glob
import pickle
import logging
import os
import re
import requests
import socket
import time
from datetime import datetime

from bs4 import BeautifulSoup
from lib.wrappers.decorators import RateLimited




class GithubWrapper(object):
    def __init__(self, gh):
        self.gh = gh

    @RateLimited
    def get_repo(self, repo_path, verbose=True):
        repo = RepoWrapper(self.gh, repo_path, verbose=verbose)
        return repo

    def get_current_time(self):
        return datetime.utcnow()

    def get_rate_limit(self):
        return self.gh.get_rate_limit().raw_data


class RepoWrapper(object):
    def __init__(self, gh, repo_path, verbose=True):

        self.gh = gh
        self.repo_path = repo_path
        self.cachefile = os.path.join('~/.ansibullbot', 'cache', repo_path)
        self.cachefile = '%s/repo.pickle' % self.cachefile
        self.cachefile = os.path.expanduser(self.cachefile)
        self.cachedir = os.path.dirname(self.cachefile)
        self.updated_at_previous = None
        self.updated = False
        self.verbose = verbose

        if not os.path.isdir(self.cachedir):
            os.makedirs(self.cachedir)
        if os.path.isfile(self.cachefile):
            with open(self.cachefile, 'rb') as f:
                self.repo = pickle.load(f)
            self.updated_at_previous = self.repo.updated_at
            #import epdb; epdb.st()
            self.updated = self.repo.update()
        else:
            self.repo = self.gh.get_repo(repo_path)
            self.save_repo()

    def get_rate_limit(self):
        return self.gh.get_rate_limit().raw_data

    def debug(self, msg=""):
        """Prints debug message if verbosity is given"""
        if self.verbose:
            print("Debug: " + msg)

    def save_repo(self):
        with open(self.cachefile, 'wb') as f:
            pickle.dump(self.repo, f)

    def get_last_issue_number(self):
        '''Scrape the newest issue/pr number'''

        url = 'https://github.com/'
        url += self.repo_path
        url += '/issues?q='

        rr = requests.get(url)
        soup = BeautifulSoup(rr.text, 'html.parser')
        refs = soup.findAll('a')
        urls = []
        for ref in refs:
            if 'href' in ref.attrs:
                print(ref.attrs['href'])
                urls.append(ref.attrs['href'])
        checkpath = '/' + self.repo_path
        m = re.compile('^%s/(pull|issues)/[0-9]+$' % checkpath)
        urls = [x for x in urls if m.match(x)]

        if not urls:
            import epdb; epdb.st()

        numbers = [x.split('/')[-1] for x in urls]
        numbers = [int(x) for x in numbers]
        numbers = sorted(set(numbers))
        if numbers:
            return numbers[-1]
        else:
            return None

    @RateLimited
    def get_issue(self, number):
        issue = self.load_issue(number)
        if issue:
            if issue.update():
                self.save_issue(issue)
        else:
            issue = self.repo.get_issue(number)
            self.save_issue(issue)
        return issue

    @RateLimited
    def get_pullrequest(self, number):
        #import epdb; epdb.st()
        pr = self.load_pullrequest(number)
        if pr:
            if pr.update():
                self.save_pullrequest(pr)
        else:
            pr = self.repo.get_pull(number)
            self.save_pullrequest(pr)
        return pr

    @RateLimited
    def get_labels(self):
        return self.load_update_fetch('labels')

    @RateLimited
    def get_assignees(self):
        return self.load_update_fetch('assignees')

    @RateLimited
    def get_issues(self, since=None, state='open', itype='issue'):

        '''Abstraction around get_issues to get ALL issues in a cached way'''

        if since:
            issues = self.repo.get_issues(since=since)
            issues = [x for x in issues]
            for issue in issues:
                self.save_issue(issue)
        else:

            # load all cached issues then update or fetch missing ...
            logging.debug('loading cached issues')
            issues = self.load_issues()

            logging.debug('fetching all issues')
            if state:
                rissues = self.repo.get_issues(state=state)
            else:
                rissues = self.repo.get_issues()

            if state == 'open':
                return rissues

            last_issue = rissues[0]

            logging.debug('comparing cache against fetched')
            expected = xrange(1, last_issue.number)
            for exp in expected:
                if self.is_missing(exp):
                    continue
                ci = next((i for i in issues if i.number == exp), None)

                # skip pull requests if requested
                if itype == 'issue' and ci:
                    if ci.pull_request:
                        continue

                if not ci:
                    logging.debug('fetching %s' % exp)
                    issue = self.repo.get_issue(exp)
                    issues.append(issue)
                    logging.debug('saving %s' % exp)
                    self.save_issue(issue)
                else:
                    if ci.state == 'open':
                        if ci.update():
                            logging.debug('%s updated' % exp)
                            self.save_issue(ci)

            logging.debug('storing cache of repo')
            self.save_repo()

            if itype == 'issue':
                issues = [x for x in issues if not x.pull_request]

            if state == 'open':
                issues = [x for x in issues if x.state == 'open']

            # sort in reverse numerical order
            issues.sort(key=lambda x: x.number, reverse=True)

        return issues

    @RateLimited
    def get_pullrequests(self, since=None, state='open', itype='pullrequest'):
        # there is no 'since' for pullrequests
        prs = [x for x in self.repo.get_pulls()]
        return prs

    def is_missing(self, number):
        mfile = os.path.join(self.cachedir, 'issues', str(number), 'missing')
        if os.path.isfile(mfile):
            return True
        else:
            return False

    def set_missing(self, number):
        mfile = os.path.join(self.cachedir, 'issues', str(number), 'missing')
        mdir = os.path.dirname(mfile)
        if not os.path.isdir(mdir):
            os.makedirs(mdir)
        with open(mfile, 'wb') as f:
            f.write('\n')

    def load_issues(self, state='open'):
        issues = []
        gfiles = glob.glob('%s/issues/*/issue.pickle' % self.cachedir)
        for gf in gfiles:
            logging.debug('load %s' % gf)
            issue = None
            try:
                with open(gf, 'rb') as f:
                    issue = pickle.load(f)
            except EOFError as e:
                # this is bad, get rid of it
                os.remove(gf)
            if issue:
                issues.append(issue)
        return issues

    def load_issue(self, number):
        pfile = os.path.join(
            self.cachedir,
            'issues',
            str(number),
            'issue.pickle'
        )
        if os.path.isfile(pfile):
            with open(pfile, 'rb') as f:
                issue = pickle.load(f)
            return issue
        else:
            return False

    def load_pullrequest(self, number):
        #import epdb; epdb.st()
        pfile = os.path.join(
            self.cachedir,
            'issues',
            str(number),
            'pullrequest.pickle'
        )
        pdir = os.path.dirname(pfile)
        if not os.path.isdir(pdir):
            os.makedirs(pdir)
        if os.path.isfile(pfile):
            with open(pfile, 'rb') as f:
                issue = pickle.load(f)
            return issue
        else:
            return False

    def save_issues(self, issues):
        for issue in issues:
            self.save_issue(issue)

    def save_issue(self, issue):
        cfile = os.path.join(
            self.cachedir,
            'issues',
            str(issue.number),
            'issue.pickle'
        )
        cdir = os.path.dirname(cfile)
        if not os.path.isdir(cdir):
            os.makedirs(cdir)
        with open(cfile, 'wb') as f:
            pickle.dump(issue, f)

    def save_pullrequest(self, issue):
        cfile = os.path.join(
            self.cachedir,
            'issues',
            str(issue.number),
            'pullrequest.pickle'
        )
        cdir = os.path.dirname(cfile)
        if not os.path.isdir(cdir):
            os.makedirs(cdir)
        with open(cfile, 'wb') as f:
            pickle.dump(issue, f)

    def load_update_fetch(self, property_name):
        '''Fetch a get() property for an object'''

        edata = None
        events = []
        updated = None
        update = False
        write_cache = False
        self.repo.update()

        #import epdb; epdb.st()
        pfile = os.path.join(self.cachedir, '%s.pickle' % property_name)
        pdir = os.path.dirname(pfile)

        if not os.path.isdir(pdir):
            os.makedirs(pdir)

        if os.path.isfile(pfile):
            try:
                with open(pfile, 'rb') as f:
                    edata = pickle.load(f)
            except Exception as e:
                update = True
                write_cache = True

            # check the timestamp on the cache
            if edata:
                updated = edata[0]
                events = edata[1]
                if updated < self.repo.updated_at:
                    update = True
                    write_cache = True

        # pull all events if timestamp is behind or no events cached
        if update or not events:
            write_cache = True
            updated = self.get_current_time()
            try:
                methodToCall = getattr(self.repo, 'get_' + property_name)
            except Exception as e:
                print(e)
                import epdb; epdb.st()
            events = [x for x in methodToCall()]

        if write_cache or not os.path.isfile(pfile):
            # need to dump the pickle back to disk
            edata = [updated, events]
            with open(pfile, 'wb') as f:
                pickle.dump(edata, f)

        return events

    def get_current_time(self):
        return datetime.utcnow()
