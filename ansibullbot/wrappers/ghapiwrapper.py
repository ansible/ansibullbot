#!/usr/bin/env python

from __future__ import print_function

import glob
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

from ansibullbot._pickle_compat import pickle_dump, pickle_load
from ansibullbot._text_compat import to_text
from ansibullbot.decorators.github import RateLimited
from ansibullbot.errors import RateLimitError


class GithubWrapper(object):
    def __init__(self, gh, token=None, username=None, password=None, cachedir=u'~/.ansibullbot/cache'):
        self.gh = gh
        self.token = token
        self.username = username
        self.password = password
        self.cachedir = os.path.expanduser(cachedir)
        self.cachefile = os.path.join(self.cachedir, u'github.pickle')

    @RateLimited
    def get_repo(self, repo_path, verbose=True):
        repo = RepoWrapper(self.gh, repo_path, verbose=verbose, cachedir=self.cachedir)
        return repo

    def get_current_time(self):
        return datetime.utcnow()

    def get_rate_limit(self):
        return self.gh.get_rate_limit().raw_data

    @RateLimited
    def get_request(self, url):
        '''Get an arbitrary API endpoint'''

        accepts = [
            u'application/json',
            u'application/vnd.github.mockingbird-preview',
            u'application/vnd.github.sailor-v-preview+json',
            u'application/vnd.github.starfox-preview+json',
            u'application/vnd.github.v3+json',
        ]

        headers = {
            u'Accept': u','.join(accepts),
            u'Authorization': u'Bearer %s' % self.token,
        }

        rr = requests.get(url, headers=headers)
        data = rr.json()

        # handle ratelimits ...
        if isinstance(data, dict) and data.get(u'message'):
            if data[u'message'].lower().startswith('api rate limit exceeded'):
                raise RateLimitError()

        if hasattr(rr, 'links') and rr.links and rr.links.get('next'):
            _data = self.get_request(rr.links['next']['url'])
            data += _data

        return data


class RepoWrapper(object):
    def __init__(self, gh, repo_path, verbose=True, cachedir=u'~/.ansibullbot/cache'):

        self.gh = gh
        self.repo_path = repo_path

        self.cachedir = os.path.expanduser(cachedir)
        self.cachedir = os.path.join(self.cachedir, repo_path)
        self.cachefile = os.path.join(self.cachedir, u'repo.pickle')

        self.updated_at_previous = None
        self.updated = False
        self.verbose = verbose
        self._assignees = False
        self._pullrequest_summaries = False
        self.repo = self.get_repo(repo_path)

        self._labels = False

    @RateLimited
    def get_repo(self, repo_path):
        logging.getLogger(u'github.Requester').setLevel(logging.INFO)
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
            pickle_dump(self.repo, f)

    def get_last_issue_number(self):
        '''Scrape the newest issue/pr number'''

        logging.info(u'scraping last issue number')

        url = u'https://github.com/'
        url += self.repo_path
        url += u'/issues?q='

        rr = requests.get(url)
        soup = BeautifulSoup(rr.text, u'html.parser')
        refs = soup.findAll(u'a')
        urls = []
        for ref in refs:
            if u'href' in ref.attrs:
                #print(ref.attrs['href'])
                urls.append(ref.attrs[u'href'])
        checkpath = u'/' + self.repo_path
        m = re.compile(u'^%s/(pull|issues)/[0-9]+$' % checkpath)
        urls = [x for x in urls if m.match(x)]

        if not urls:
            logging.error(u'no urls found in %s' % url)
            if C.DEFAULT_BREAKPOINTS:
                logging.error(u'breakpoint!')
                import epdb; epdb.st()
            else:
                raise Exception(u'no urls')

        numbers = [x.split(u'/')[-1] for x in urls]
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
                logging.warning(u'cleaning cache for %s' % number)
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
            self._assignees = self.load_update_fetch(u'assignees')
        return self._assignees

    '''
    @RateLimited
    def get_assignees(self):
        if self._assignees is False:
            self._assignees = self.load_update_fetch(u'assignees')
        return self._assignees
    '''

    def get_issues(self, since=None, state=u'open', itype=u'issue'):

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
            logging.debug(u'%s updated' % issue.number)
            self.save_issue(issue)
        return issue

    @RateLimited
    def get_pullrequests(self, since=None, state=u'open', itype=u'pullrequest'):
        # there is no 'since' for pullrequests
        prs = [x for x in self.repo.get_pulls()]
        return prs

    def is_missing(self, number):
        mfile = os.path.join(self.cachedir, u'issues', to_text(number), u'missing')
        if os.path.isfile(mfile):
            return True
        else:
            return False

    def set_missing(self, number):
        mfile = os.path.join(self.cachedir, u'issues', to_text(number), u'missing')
        mdir = os.path.dirname(mfile)
        if not os.path.isdir(mdir):
            os.makedirs(mdir)
        with open(mfile, 'wb') as f:
            f.write('\n')

    def load_issues(self, state=u'open', filter=None):
        issues = []
        gfiles = glob.glob(u'%s/issues/*/issue.pickle' % self.cachedir)
        for gf in gfiles:

            if filter:
                gf_parts = gf.split(u'/')
                this_number = gf_parts[-2]
                this_number = int(this_number)
                if this_number not in filter:
                    continue

            logging.debug(u'load %s' % gf)
            issue = None
            try:
                with open(gf, 'rb') as f:
                    issue = pickle_load(f)
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
            u'issues',
            to_text(number),
            u'issue.pickle'
        )
        if os.path.isfile(pfile):
            with open(pfile, 'rb') as f:
                try:
                    issue = pickle_load(f)
                except TypeError:
                    return False
            return issue
        else:
            return False

    def load_pullrequest(self, number):
        pfile = os.path.join(
            self.cachedir,
            u'issues',
            to_text(number),
            u'pullrequest.pickle'
        )
        pdir = os.path.dirname(pfile)
        if not os.path.isdir(pdir):
            os.makedirs(pdir)
        if os.path.isfile(pfile):
            with open(pfile, 'rb') as f:
                issue = pickle_load(f)
            return issue
        else:
            return False

    def save_issues(self, issues):
        for issue in issues:
            self.save_issue(issue)

    def save_issue(self, issue):
        cfile = os.path.join(
            self.cachedir,
            u'issues',
            to_text(issue.number),
            u'issue.pickle'
        )
        cdir = os.path.dirname(cfile)
        if not os.path.isdir(cdir):
            os.makedirs(cdir)
        logging.debug(u'dump %s' % cfile)
        with open(cfile, 'wb') as f:
            pickle_dump(issue, f)

    def save_pullrequest(self, issue):
        cfile = os.path.join(
            self.cachedir,
            u'issues',
            to_text(issue.number),
            u'pullrequest.pickle'
        )
        cdir = os.path.dirname(cfile)
        if not os.path.isdir(cdir):
            os.makedirs(cdir)
        with open(cfile, 'wb') as f:
            pickle_dump(issue, f)

    @RateLimited
    def load_update_fetch(self, property_name):
        '''Fetch a get() property for an object'''

        edata = None
        events = []
        updated = None
        update = False
        write_cache = False
        self.repo.update()

        pfile = os.path.join(self.cachedir, u'%s.pickle' % property_name)
        pdir = os.path.dirname(pfile)

        if not os.path.isdir(pdir):
            os.makedirs(pdir)

        if os.path.isfile(pfile):
            try:
                with open(pfile, 'rb') as f:
                    edata = pickle_load(f)
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
                methodToCall = getattr(self.repo, u'get_' + property_name)
            except Exception as e:
                logging.error(e)
                if C.DEFAULT_BREAKPOINTS:
                    logging.error(u'breakpoint!')
                    import epdb; epdb.st()
                else:
                    raise Exception(u'unable to get %s' % property_name)
            events = [x for x in methodToCall()]

        if write_cache or not os.path.isfile(pfile):
            # need to dump the pickle back to disk
            edata = [updated, events]
            with open(pfile, 'wb') as f:
                pickle_dump(edata, f)

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

        lm = self.repo.get_file_contents(u'.github/LABEL_MAP.md')
        lm_content = lm.decoded_content

        lines = lm_content.split(u'\n')
        for line in lines:
            line = line.strip()
            if line:
                parts = [x.strip() for x in line.split(u':', 1) if x.strip()]
                label_map[parts[0].lower()] = parts[1].replace(u'"', u'').replace(u"'", u'')

        return label_map

    def clean_issue_cache(self, number):
        # https://github.com/ansible/ansibullbot/issues/610
        cdir = os.path.join(
            self.cachedir,
            u'issues',
            to_text(number)
        )
        shutil.rmtree(cdir)
