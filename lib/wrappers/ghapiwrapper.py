#!/usr/bin/env python

from __future__ import print_function

import glob
import pickle
import logging
import os
import re
import requests
#import time
#import urllib2
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
        self._assignees = False
        self._pullrequest_summaries = False
        self.repo = self.get_repo(repo_path)

    @RateLimited
    def get_repo(self, repo_path):
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
            import epdb; epdb.st()

        numbers = [x.split('/')[-1] for x in urls]
        numbers = [int(x) for x in numbers]
        numbers = sorted(set(numbers))
        if numbers:
            return numbers[-1]
        else:
            return None

    """
    @property
    def pullrequest_summaries(self):
        if self._pullrequest_summaries is False:
            self._pullrequest_summaries = \
                self.scrape_pullrequest_summaries()
        return self._pullrequest_summaries

    def scrape_pullrequest_summaries(self):

        prs = {}

        base_url = 'https://github.com'
        url = base_url
        url += '/'
        url += self.repo_path
        url += '/pulls?'
        url += urllib2.quote('q=is open')

        page_count = 0
        while url:
            page_count += 1
            rr = self._request_url(url)
            if rr.status_code != 200:
                break
            soup = BeautifulSoup(rr.text, 'html.parser')
            data = self._parse_pullrequests_summary_page(soup)
            if data['next_page']:
                url = base_url + data['next_page']
            else:
                url = None
            if data['prs']:
                prs.update(data['prs'])
            else:
                import epdb; epdb.st()

        return prs

    def scrape_pullrequest_review(self, number):

        reviews = {
            'users': {},
            'reviews': {}
        }

        base_url = 'https://github.com'
        url = base_url
        url += '/'
        url += self.repo_path
        url += '/pull/'
        url += str(number)

        rr = self._request_url(url)
        soup = BeautifulSoup(rr.text, 'html.parser')

        # <span class="reviewers-status-icon tooltipped tooltipped-nw
        # float-right d-block text-center" aria-label="nerzhul requested
        # changes">
        spans = soup.findAll(
            'span',
            {'class': lambda L: L and 'reviewers-status-icon' in L}
        )
        for span in spans:
            # nerzhul requested changes
            # bcoca left review comments
            # gundalow approved these changes
            txt = span.attrs['aria-label']
            tparts = txt.split(None, 1)
            reviews['users'][tparts[0]] = tparts[1]

        # <div id="pullrequestreview-15502866" class="timeline-comment
        # js-comment">
        rdivs = soup.findAll(
            'div',
            {'class': lambda L: L and 'discussion-item-review' in L}
        )
        count = 0
        for rdiv in rdivs:
            count += 1

            author = rdiv.find('a', {'class': ['author']}).text

            id_div = rdiv.find(
                'div',
                {'id': lambda L: L and L.startswith('pullrequestreview-')}
            )
            if id_div:
                rid = id_div.attrs['id']
            else:
                rid = count

            tdiv = rdiv.find('relative-time')
            if tdiv:
                timestamp = tdiv['datetime']
            else:
                timestamp = None

            obutton = rdiv.findAll(
                'button',
                {'class': lambda L: L and 'outdated-comment-label' in L}
            )
            if obutton:
                outdated = True
            else:
                outdated = False

            atxt = rdiv.find('div', {'class': ['discussion-item-header']}).text
            atxt = atxt.lower()
            if 'suggested changes' in atxt:
                action = 'suggested changes'
            elif 'requested changes' in atxt:
                action = 'requested changes'
            elif 'requested a review' in atxt:
                action = 'requested review'
            elif 'requested review' in atxt:
                action = 'requested review'
            elif 'approved these changes' in atxt:
                action = 'approved'
            elif 'left review comments' in atxt:
                action = 'review comment'
            elif 'reviewed' in atxt:
                action = 'reviewed'
            else:
                action = None
                import epdb; epdb.st()

            reviews['reviews'][rid] = {
                'actor': author,
                'action': action,
                'timestamp': timestamp,
                'outdated': outdated
            }

        return reviews

    def scrape_open_issue_numbers(self, url=None, recurse=True):

        '''Make a (semi-inaccurate) range of open issue numbers'''

        # The github api paginates through all open issues and quickly
        # hits a rate limit on large issue queues. Webscraping also
        # hits an undocumented rate limit. What this will do instead,
        # is find the issues on the first and last page of results and
        # then fill in the numbers between for a best guess range of
        # numbers that are likely to be open.

        # https://github.com/ansible/ansible/issues?q=is%3Aopen
        # https://github.com/ansible/ansible/issues?page=2&q=is%3Aopen

        base_url = 'https://github.com'
        if not url:
            url = base_url
            url += '/'
            url += self.repo_path
            url += '/issues?'
            #url += 'per_page=100'
            #url += '&'
            url += urllib2.quote('q=is open')

        rr = self._request_url(url)
        soup = BeautifulSoup(rr.text, 'html.parser')
        numbers = self._parse_issue_numbers_from_soup(soup)

        if recurse:

            pages = soup.findAll('a', {'href': lambda L: L and 'page=' in L})

            if pages:
                pages = [x for x in pages if 'class' not in x.attrs]
                last_page = pages[-1]
                last_url = base_url + last_page.attrs['href']
                new_numbers = self.scrape_open_issue_numbers(
                    url=last_url,
                    recurse=False
                )
                new_numbers = sorted(set(new_numbers))
                # fill in the gap ...
                fillers = [x for x in xrange(new_numbers[-1], numbers[0])]
                numbers += new_numbers
                numbers += fillers

        numbers = sorted(set(numbers))
        return numbers

    def _request_url(self, url):
        ua = 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0)'
        ua += ' Gecko/20100101 Firefix/40.1'
        headers = {
            'User-Agent': ua
        }

        sleep = 60
        failed = True
        while failed:
            rr = requests.get(url, headers=headers)
            if rr.reason == 'Too Many Requests':
                logging.debug('too many requests, sleeping %ss' % sleep)
                time.sleep(sleep)
                sleep = sleep * 2
            else:
                failed = False

        return rr

    def _parse_issue_numbers_from_soup(self, soup):
        refs = soup.findAll('a')
        urls = []
        for ref in refs:
            if 'href' in ref.attrs:
                print(ref.attrs['href'])
                urls.append(ref.attrs['href'])

        checkpath = '/' + self.repo_path
        m = re.compile('^%s/(pull|issues)/[0-9]+$' % checkpath)
        urls = [x for x in urls if m.match(x)]

        numbers = [x.split('/')[-1] for x in urls]
        numbers = [int(x) for x in numbers]
        numbers = sorted(set(numbers))
        return numbers

    def _parse_pullrequests_summary_page(self, soup):
        data = {
            'prs': {}
        }

        lis = soup.findAll(
            'li',
            {'class': lambda L: L and L.endswith('issue-row')}
        )

        if lis:
            for li in lis:

                number = li.attrs['id'].split('_')[-1]
                number = int(number)
                status_txt = None
                status_state = None
                review_txt = None

                status = li.find('div', {'class': 'commit-build-statuses'})
                if status:
                    status_a = status.find('a')
                    status_txt = status_a.attrs['aria-label'].lower().strip()
                    status_state = status_txt.split(':')[0]

                review_txt = None
                review = li.find(
                    'a',
                    {'aria-label': lambda L: L and 'review' in L}
                )
                if review:
                    review_txt = review.text.lower().strip()
                else:
                    review_txt = None

                data['prs'][number] = {
                    'ci_state': status_state,
                    'ci_message': status_txt,
                    'review_message': review_txt,

                }

        # next_page
        next_page = None
        next_a = soup.find('a', {'class': ['next_page']})
        if next_a:
            next_page = next_a.attrs['href']
        data['next_page'] = next_page

        #import epdb; epdb.st()
        return data
    """

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
        pr = self.repo.get_pull(number)
        return pr

    @RateLimited
    def get_labels(self):
        return self.load_update_fetch('labels')

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
                #import epdb; epdb.st()
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
