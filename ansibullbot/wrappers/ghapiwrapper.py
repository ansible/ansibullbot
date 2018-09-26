#!/usr/bin/env python

from __future__ import print_function

import glob
import pickle
import logging
import os
import re
import requests
import shutil
#import time
#import urllib2
from datetime import datetime

import ansibullbot.constants as C

from bs4 import BeautifulSoup
from ansibullbot.decorators.github import RateLimited


class GithubWrapper(object):
    def __init__(self, gh, cachedir='~/.ansibullbot/cache'):
        self.gh = gh
        self.cachedir = os.path.expanduser(cachedir)
        self.cachefile = os.path.join(self.cachedir, 'github.pickle')

    @RateLimited
    def get_repo(self, repo_path, verbose=True):
        repo = RepoWrapper(self.gh, repo_path, verbose=verbose, cachedir=self.cachedir)
        return repo

    def get_current_time(self):
        return datetime.utcnow()

    def get_rate_limit(self):
        return self.gh.get_rate_limit().raw_data


class RepoWrapper(object):
    def __init__(self, gh, repo_path, verbose=True, cachedir='~/.ansibullbot/cache'):

        self.gh = gh
        self.repo_path = repo_path

        self.cachedir = os.path.expanduser(cachedir)
        self.cachedir = os.path.join(self.cachedir, repo_path)
        self.cachefile = os.path.join(self.cachedir, 'repo.pickle')

        self.updated_at_previous = None
        self.updated = False
        self.verbose = verbose
        self._assignees = False
        self._pullrequest_summaries = False
        self.repo = self.get_repo(repo_path)

        self._labels = False

    @RateLimited
    def get_repo(self, repo_path):
        logging.getLogger('github.Requester').setLevel(logging.INFO)
        repo = self.gh.get_repo(repo_path)
        return repo

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

        logging.info('scraping last issue number')

        url = 'https://github.com/'
        url += self.repo_path
        url += '/issues?q='

        rr = requests.get(url)
        soup = BeautifulSoup(rr.text, 'html.parser')
        refs = soup.findAll('a')
        urls = []
        for ref in refs:
            if 'href' in ref.attrs:
                #print(ref.attrs['href'])
                urls.append(ref.attrs['href'])
        checkpath = '/' + self.repo_path
        m = re.compile('^%s/(pull|issues)/[0-9]+$' % checkpath)
        urls = [x for x in urls if m.match(x)]

        if not urls:
            logging.error('no urls found in %s' % url)
            if C.DEFAULT_BREAKPOINTS:
                logging.error('breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception('no urls')

        numbers = [x.split('/')[-1] for x in urls]
        numbers = [int(x) for x in numbers]
        numbers = sorted(set(numbers))
        if numbers:
            return numbers[-1]
        else:
            return None

    @RateLimited
    def get_issue(self, number):
        issue = None
        while True:
            try:
                issue = self.load_issue(number)
                if issue:
                    if issue.update():
                        self.save_issue(issue)
                else:
                    issue = self.repo.get_issue(number)
                    self.save_issue(issue)
                break
            except UnicodeDecodeError:
                # https://github.com/ansible/ansibullbot/issues/610
                logging.warning('cleaning cache for %s' % number)
                self.clean_issue_cache(number)

        return issue

    @RateLimited
    def get_pullrequest(self, number):
        pr = self.repo.get_pull(number)
        return pr

    @property
    def labels(self):
        if self._labels is False:
            self._labels = [x.name for x in self.get_labels()]
        return self._labels

    @RateLimited
    def get_labels(self):
        #return self.load_update_fetch('labels')
        labels = []
        for label in self.repo.get_labels():
            labels.append(label)
        return labels

    @property
    def assignees(self):
        if self._assignees is False:
            self._assignees = self.load_update_fetch('assignees')
        return self._assignees

    '''
    @RateLimited
    def get_assignees(self):
        if self._assignees is False:
            self._assignees = self.load_update_fetch('assignees')
        return self._assignees
    '''

    def get_issues(self, since=None, state='open', itype='issue'):

        if since:
            return self.repo.get_issues(since=since)
        else:
            return self.repo.get_issues()

    @RateLimited
    def fetch_repo_issue(self, number):
        issue = self.repo.get_issue(number)
        return issue

    @RateLimited
    def update_issue(self, issue):
        if issue.update():
            logging.debug('%s updated' % issue.number)
            self.save_issue(issue)
        return issue

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

    def load_issues(self, state='open', filter=None):
        issues = []
        gfiles = glob.glob('%s/issues/*/issue.pickle' % self.cachedir)
        for gf in gfiles:

            if filter:
                gf_parts = gf.split('/')
                this_number = gf_parts[-2]
                this_number = int(this_number)
                if this_number not in filter:
                    continue

            logging.debug('load %s' % gf)
            issue = None
            try:
                with open(gf, 'rb') as f:
                    issue = pickle.load(f)
            except EOFError as e:
                # this is bad, get rid of it
                logging.error(e)
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
        logging.debug('dump %s' % cfile)
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

    @RateLimited
    def load_update_fetch(self, property_name):
        '''Fetch a get() property for an object'''

        edata = None
        events = []
        updated = None
        update = False
        write_cache = False
        self.repo.update()

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
                logging.error(e)
                if C.DEFAULT_BREAKPOINTS:
                    logging.error('breakpoint!')
                    import epdb; epdb.st()
                else:
                    raise Exception('unable to get %s' % property_name)
            events = [x for x in methodToCall()]

        if write_cache or not os.path.isfile(pfile):
            # need to dump the pickle back to disk
            edata = [updated, events]
            with open(pfile, 'wb') as f:
                pickle.dump(edata, f)

        return events

    @RateLimited
    def get_file_contents(self, filepath):

        # FIXME - cachethis

        filedata = None
        try:
            filedata = self.repo.get_file_contents(filepath)
        except:
            pass

        return filedata

    def get_current_time(self):
        return datetime.utcnow()

    def get_label_map(self):

        label_map = {}

        lm = self.repo.get_file_contents('.github/LABEL_MAP.md')
        lm_content = lm.decoded_content

        lines = lm_content.split('\n')
        for line in lines:
            line = line.strip()
            if line:
                parts = [x.strip() for x in line.split(':', 1) if x.strip()]
                label_map[parts[0].lower()] = parts[1].replace('"', '').replace("'", '')

        return label_map

    def clean_issue_cache(self, number):
        # https://github.com/ansible/ansibullbot/issues/610
        cdir = os.path.join(
            self.cachedir,
            'issues',
            str(number)
        )
        shutil.rmtree(cdir)
