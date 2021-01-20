#!/usr/bin/env python

import json
import logging
import re
import requests
import os
import shutil
import sys
import tempfile
import time
import urllib.parse

from bs4 import BeautifulSoup

from ansibullbot._text_compat import to_text
from ansibullbot.utils.receiver_client import post_to_receiver
import ansibullbot.constants as C


class GithubWebScraper:
    cachedir = None
    baseurl = 'https://github.com'
    summaries = {}
    reviews = {}

    def __init__(self, cachedir=None, server=None):
        if server:
            # this is for testing
            self.baseurl = server.rstrip('/')
        if cachedir:
            self.cachedir = cachedir
        else:
            self.cachedir = '/tmp/gws'
        if not os.path.isdir(self.cachedir):
            os.makedirs(self.cachedir)

    def split_repo_url(self, repo_url):
        rparts = repo_url.split('/')
        rparts = [x.strip() for x in rparts if x.strip()]
        return rparts[-2], rparts[-1]

    def load_summaries(self, repo_url):
        issues = {}
        ns, repo = self.split_repo_url(repo_url)
        cachefile = os.path.join(self.cachedir, ns, repo, 'html_summaries.json')
        if os.path.isfile(cachefile):
            try:
                with open(cachefile, 'rb') as f:
                    issues = json.load(f)
            except Exception as e:
                logging.error(e)
                raise
        return issues

    def dump_summaries(self, repo_url, issues, filename="html_summaries"):

        """
        [jtanner@fedmac ansibullbot]$ sudo ls -al /proc/10895/fd
        total 0
        dr-x------ 2 jtanner docker  0 Jan 13 08:51 .
        dr-xr-xr-x 9 jtanner docker  0 Jan 13 08:42 ..
        lrwx------ 1 jtanner docker 64 Jan 13 08:51 0 -> /dev/pts/2
        lrwx------ 1 jtanner docker 64 Jan 13 08:51 1 -> /dev/pts/2
        lr-x------ 1 jtanner docker 64 Jan 13 08:51 10 -> /dev/urandom
        lrwx------ 1 jtanner d 64 Jan 13 08:51 11 -> /tmp/tmpag2rAb (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 12 -> /tmp/tmpD2plk9 (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 13 -> /tmp/tmpfkSSPA (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 14 -> /tmp/tmpIDY_wb (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 15 -> /tmp/tmpbQBvI2 (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 16 -> /tmp/tmpknP5os (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 17 -> /tmp/tmpDJgEnc (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 18 -> /tmp/tmprWLicP (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 19 -> /tmp/tmpm6d8Qx (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 2 -> /dev/pts/2
        lrwx------ 1 jtanner d 64 Jan 13 08:51 20 -> /tmp/tmp_w9Sth (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 21 -> /tmp/tmpRGnb3p (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 22 -> /tmp/tmpiVYdTE (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 23 -> /tmp/tmpEyGXuP (deleted)
        l-wx------ 1 jtanner d 64 Jan 13 08:51 3 -> /var/log/ansibullbot.log
        lrwx------ 1 jtanner d 64 Jan 13 08:51 4 -> /tmp/tmpIlHOg_ (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 5 -> /tmp/tmp5P8Mya (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 6 -> /tmp/tmpDW4MRD (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 7 -> /tmp/tmpUyBIFB (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 8 -> /tmp/tmpYcWaLe (deleted)
        lrwx------ 1 jtanner d 64 Jan 13 08:51 9 -> /tmp/tmp_Qcxrt (deleted)
        """

        ns, repo = self.split_repo_url(repo_url)
        cachefile = os.path.join(
            self.cachedir,
            ns,
            repo,
            '%s.json' % filename
        )
        if not issues:
            raise Exception('no issues')

        tfh, tfn = tempfile.mkstemp()
        os.close(tfh)
        with open(tfn, 'wb') as f:
            f.write(json.dumps(issues, sort_keys=True, indent=2))

        if os.path.isfile(cachefile):
            os.remove(cachefile)
        shutil.move(tfn, cachefile)

    def dump_summaries_tmp(self, repo_url, issues):
        self.dump_summaries(repo_url, issues, filename="html_summaries-tmp")

    def get_last_number(self, repo_path):
        repo_url = self.baseurl + '/' + repo_path
        issues = self.get_issue_summaries(repo_url)
        if issues:
            return sorted([int(x) for x in issues.keys()])[-1]
        else:
            return None

    def get_issue_summaries(self, repo_url, baseurl=None, cachefile=None):
        '''Paginate through github's web interface and scrape summaries'''

        # repo_url - https://github.com/ansible/ansible for example
        # baseurl - an entrypoint for one-off utils to scrape specific issue
        #           query urls. NOTE: this disables writing a cache

        # get cached
        if not baseurl:
            issues = self.load_summaries(repo_url)
        else:
            issues = {}

        if not baseurl:
            url = repo_url
            url += '/issues'
            url += '?'
            url += 'q='
            url += urllib.parse.quote('sort:updated-desc')
        else:
            url = baseurl

        namespace = repo_url.split('/')[-2]
        reponame = repo_url.split('/')[-1]

        rr = self._request_url(url)
        soup = BeautifulSoup(rr.text, 'html.parser')
        data = self._parse_issue_summary_page(soup)
        if data['issues']:
            # send to receiver
            post_to_receiver('html_summaries', {'user': namespace, 'repo': reponame}, data['issues'])
            # update master list
            issues.update(data['issues'])

        if not baseurl:
            self.dump_summaries_tmp(repo_url, issues)

        while data['next_page']:
            rr = self._request_url(self.baseurl + data['next_page'])
            soup = BeautifulSoup(rr.text, 'html.parser')
            data = self._parse_issue_summary_page(soup)

            # send to receiver
            post_to_receiver('html_summaries', {'user': namespace, 'repo': reponame}, data['issues'])

            if not data['next_page'] or not data['issues']:
                break

            changed = []
            changes = False
            for k, v in data['issues'].items():

                if not isinstance(k, unicode):
                    k = '%s' % k

                if k not in issues:
                    changed.append(k)
                    changes = True
                elif v != issues[k]:
                    changed.append(k)
                    changes = True
                issues[k] = v

            if changed:
                logging.info('changed: %s' % ','.join(x for x in changed))

            if not baseurl:
                self.dump_summaries_tmp(repo_url, issues)

            if not changes:
                break

        # get missing
        if not baseurl:
            numbers = sorted([int(x) for x in issues.keys()])
            missing = [x for x in xrange(1, numbers[-1]) if x not in numbers]
            for x in missing:
                summary = self.get_single_issue_summary(repo_url, x, force=True)
                if summary:
                    post_to_receiver('html_summaries', {'user': namespace, 'repo': reponame}, {x: summary})
                    if not isinstance(x, unicode):
                        x = '%s' % x
                    issues[x] = summary

        # get missing timestamps
        if not baseurl:
            numbers = sorted([int(x) for x in issues.keys()])
            missing = [x for x in numbers if to_text(x) not in issues or not issues[to_text(x)]['updated_at']]
            for x in missing:
                summary = self.get_single_issue_summary(repo_url, x, force=True)
                if summary:
                    post_to_receiver('html_summaries', {'user': namespace, 'repo': reponame}, {x: summary})
                    if not isinstance(x, unicode):
                        x = '%s' % x
                    issues[x] = summary

        # save the cache
        if not baseurl:
            self.dump_summaries(repo_url, issues)

        return issues

    def get_single_issue_summary(
        self,
        repo_url,
        number,
        cachefile=None,
        force=False
    ):

        '''Scrape the summary for a specific issue'''

        # get cached
        issues = self.load_summaries(repo_url)

        if number in issues and not force:
            return issues[number]
        else:
            if repo_url.startswith('http'):
                url = repo_url
            else:
                url = self.baseurl + '/' + repo_url
            url += '/issues/'
            url += to_text(number)

            rr = self._request_url(url)
            soup = BeautifulSoup(rr.text, 'html.parser')
            if soup.text.lower().strip() != 'not found':
                summary = self.parse_issue_page_to_summary(soup, url=rr.url)
                if summary:
                    issues[number] = summary

        if number in issues:
            return issues[number]
        else:
            return {}

    def _issue_urls_from_links(self, links, checkstring=None):
        issue_urls = []
        for link in links:
            href = link.get('href')
            if href.startswith(checkstring):
                issue_urls.append(href)
        return issue_urls

    def _get_issue_urls(self, namespace, repo, pages=0):
        url = os.path.join(self.baseurl, namespace, repo, 'issues')
        rr = requests.get(url)
        soup = BeautifulSoup(rr.text, 'html.parser')
        links = soup.find_all('a')

        issue_urls = []

        # href="/ansible/ansible/issues/17952"
        checkstring = '/%s/%s/issues' % (namespace, repo)
        issue_urls = self._issue_urls_from_links(
            links,
            checkstring=checkstring + '/'
        )

        if pages > 1:
            # rel="next"
            next_page = [
                x['href'] for x in links
                if 'next' in x.get('rel', []) and checkstring in x['href']
            ]
            while next_page:
                np = next_page[0]
                np = self.baseurl + np
                logging.debug('np: %s' % np)

                rr = requests.get(np)
                soup = BeautifulSoup(rr.text, 'html.parser')
                links = soup.find_all('a')
                issue_urls += self._issue_urls_from_links(
                    links,
                    checkstring=checkstring + '/'
                )
                next_page = [
                    x['href'] for x in links
                    if 'next' in x.get('rel', []) and checkstring in x['href']
                ]

        return issue_urls

    def get_latest_issue(self, namespace, repo):

        '''
        issue_urls = self._get_issue_urls(namespace, repo, pages=1)

        issue_ids = []
        for issue_url in issue_urls:
            iid = issue_url.split('/')[-1]
            if iid.isdigit():
                iid = int(iid)
                issue_ids.append(iid)

        issue_ids = sorted(set(issue_ids))
        if issue_ids:
            return issue_ids[-1]
        else:
            return None
        '''
        issues = self.get_issue_summaries(namespace + '/' + repo)
        keys = sorted({int(x['number']) for x in issues.keys()})
        return keys[-1]

    def get_usernames_from_filename_blame(
            self,
            namespace,
            repo,
            branch,
            filepath
    ):
        # https://github.com/ansible/
        #   ansible-modules-extras/blame/devel/cloud/vmware/vmware_guest.py
        commiters = {}

        url = os.path.join(
            self.baseurl,
            namespace,
            repo,
            'blame',
            branch,
            filepath
        )

        rr = self._request_url(url)

        logging.debug('parsing blame page for %s' % filepath)
        soup = BeautifulSoup(rr.text, 'html.parser')
        commits = soup.findAll('td', {'class': 'blame-commit-info'})
        for commit in commits:
            avatar = commit.find('img', {'class': 'avatar blame-commit-avatar'})
            committer = avatar.attrs.get('alt')
            if committer:

                if committer.startswith('@'):

                    msg = commit.find('a', {'class': 'message'})
                    mhref = msg.attrs['href']
                    chash = mhref.split('/')[-1]

                    committer = committer.replace('@', '')
                    if committer not in commiters:
                        commiters[committer] = []
                    if chash not in commiters[committer]:
                        commiters[committer].append(chash)

        return commiters

    def get_raw_content(self, namespace, repo, branch, filepath,
                        usecache=False):
        # https://raw.githubusercontent.com/
        #   ansible/ansibullbot/master/MAINTAINERS-CORE.txt

        tdir = '/tmp/webscraper_cache'
        tfile = os.path.join(tdir, filepath.replace('/', '__'))

        if usecache and os.path.exists(tfile):
            tdata = ''
            with open(tfile, 'rb') as f:
                tdata = f.read()

            return tdata

        url = os.path.join(
            'https://raw.githubusercontent.com',
            namespace,
            repo, branch,
            filepath
        )
        rr = requests.get(url)

        if rr.status_code != 200:
            raise Exception('bad statuscode on %s' % url)

        if usecache:
            if not os.path.isdir(tdir):
                os.makedirs(tdir)
            with open(tfile, 'wb') as f:
                f.write(rr.text.encode('ascii', 'ignore'))

        return rr.text

    def scrape_pullrequest_summaries(self):

        prs = {}

        url = self.baseurl
        url += '/'
        url += self.repo_path
        url += '/pulls?'
        url += urllib.parse.quote('q=is open')

        page_count = 0
        while url:
            page_count += 1
            rr = self._request_url(url)
            if rr.status_code != 200:
                break
            soup = BeautifulSoup(rr.text, 'html.parser')
            data = self._parse_pullrequests_summary_page(soup)
            if data['next_page']:
                url = self.baseurl + data['next_page']
            else:
                url = None
            if data['prs']:
                prs.update(data['prs'])
            else:
                raise Exception('no "prs" key in data')

        return prs

    def scrape_pullrequest_review(self, repo_path, number):

        reviews = {
            'users': {},
            'reviews': {}
        }

        url = self.baseurl
        url += '/'
        url += repo_path
        url += '/pull/'
        url += to_text(number)

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
            # requested review from gundalow
            txt = span.attrs['aria-label']
            tparts = txt.split(None, 1)
            if not tparts[0].lower() == 'awaiting':
                reviews['users'][tparts[0]] = tparts[1]

        # <div class="discussion-item discussion-item-review_requested">
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

            reviewer = None

            # https://github.com/ansible/ansibullbot/issues/523
            adiv = rdiv.find(
                'div',
                {'class': lambda L: L and L.startswith('discussion-item-header')}
            )
            if not adiv:
                adiv = rdiv.find(
                    'div',
                    {'class': 'discussion-item'}
                )

                if not adiv:

                    adiv = rdiv.find(
                        'h3',
                        {'class': lambda L: L and L.startswith('discussion-item-header')}
                    )

            atxt = adiv.text
            atxt = atxt.lower()
            if 'suggested changes' in atxt:
                action = 'suggested changes'
            elif 'requested changes' in atxt:
                action = 'requested changes'
            elif 'self-requested a review' in atxt:
                # <a href="/resmo" class="author">resmo</a>
                action = 'requested review'
                ra = rdiv.find('a', {'class': 'author'})
                if ra:
                    reviewer = ra.text.strip()
            elif 'requested a review' in atxt:
                action = 'requested review'
                tparts = atxt.split()
                findex = tparts.index('from')
                reviewer = tparts[findex+1]
            elif 'requested review' in atxt:
                action = 'requested review'
                tparts = atxt.split()
                findex = tparts.index('from')
                reviewer = tparts[findex+1]
            elif 'approved these changes' in atxt:
                action = 'approved'
            elif 'left review comments' in atxt:
                action = 'review comment'
            elif 'reviewed' in atxt:
                action = 'reviewed'
            elif 'dismissed' in atxt:
                action = 'dismissed'
            elif 'removed ' in atxt:
                action = 'removed'
                tparts = atxt.split()
                if 'from' in tparts:
                    findex = tparts.index('from')
                    reviewer = tparts[findex+1]
            else:
                raise Exception('parsing error on %s' % atxt)

            reviews['reviews'][rid] = {
                'actor': author,
                'action': action,
                'reviewer': reviewer,
                'timestamp': timestamp,
                'outdated': outdated
            }

        # force to ascii
        x = {}
        for k, v in reviews['users'].items():
            k = k.encode('ascii','ignore')
            v = v.encode('ascii', 'ignore')
            x[k] = v
        reviews['users'] = x.copy()

        return reviews

    def _request_url(self, url):
        ua = 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0)'
        ua += ' Gecko/20100101 Firefix/40.1'
        headers = {
            'User-Agent': ua
        }

        sleep = 60
        failed = True
        while failed:
            logging.debug(url)
            rr = None
            try:
                rr = requests.get(url, headers=headers)
                if rr.reason == 'Too Many Requests' or rr.status_code == 500:
                    logging.debug(
                        'too many www requests, sleeping %ss' % sleep
                    )
                    if not C.DEFAULT_RATELIMIT:
                        sys.exit(1)
                    time.sleep(sleep)
                    sleep *=  2
                else:
                    failed = False
            except requests.exceptions.ConnectionError:
                # Failed to establish a new connection: [Errno 111] Connection
                # refused',))
                logging.debug('connection refused')
                if not C.DEFAULT_RATELIMIT:
                    sys.exit(1)
                time.sleep(sleep)
                sleep *= 2
            except requests.exceptions.ChunkedEncodingError as e:
                logging.debug(e)
                if not C.DEFAULT_RATELIMIT:
                    sys.exit(1)
                time.sleep(sleep)
                sleep *= 2

            if not rr:
                failed = True
                logging.warning('no response')
                if not C.DEFAULT_RATELIMIT:
                    sys.exit(1)
                time.sleep(sleep)
                sleep *= 2

            # https://github.com/ansible/ansibullbot/issues/573
            if not rr or 'page is taking way too long to load' in rr.text.lower():
                failed = True
                logging.warning('github page took too long to load')
                if not C.DEFAULT_RATELIMIT:
                    sys.exit(1)
                time.sleep(sleep)
                sleep *= 2

        return rr

    def _parse_issue_numbers_from_soup(self, soup):
        refs = soup.findAll('a')
        urls = []
        for ref in refs:
            if 'href' in ref.attrs:
                logging.debug(ref.attrs['href'])
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

        return data

    def _parse_issue_summary_page(self, soup):

        # 2019-02-02
        #   <a id="issue_31602_link" class="link-gray-dark v-align-middle
        #       no-underline h4 js-navigation-open" data-hovercard-type="issue"
        #       data-hovercard-url="/ansible/ansible/issues/31602/ hovercard"
        #       href="/ansible/ansible/issues/31602">TITLE</a>


        data = {
            'issues': {},
            'next_page': None
        }

        '''
        lis = soup.findAll(
            u'li',
            {u'class': lambda L: L and L.endswith(u'issue-row')}
        )

        if lis:
            for li in lis:

                number = li.attrs[u'id'].split(u'_')[-1]
                number = int(number)

                # <span aria-label="Closed issue" class="tooltipped
                # tooltipped-n">
                merged = None
                state = None
                cspan = li.find(u'span', {u'aria-label': u'Closed issue'})
                ospan = li.find(u'span', {u'aria-label': u'Open issue'})
                mspan = li.find(u'span', {u'aria-label': u'Merged pull request'})
                cpspan = li.find(u'span', {u'aria-label': u'Closed pull request'})
                opspan = li.find(u'span', {u'aria-label': u'Open pull request'})
                if mspan:
                    state = u'closed'
                    merged = True
                elif ospan:
                    state = u'open'
                elif cspan:
                    state = u'closed'
                elif cpspan:
                    state = u'closed'
                    merged = False
                elif opspan:
                    state = u'open'
                    merged = False
                else:
                    raise Exception(u'state parsing error')

                created_at = None
                updated_at = None
                closed_at = None
                merged_at = None

                timestamp = li.find(u'relative-time').attrs[u'datetime']
                updated_at = timestamp
                if merged:
                    merged_at = timestamp
                if state == u'closed':
                    closed_at = timestamp

                # <a class="link-gray-dark no-underline h4 js-navigation-open"
                # href="/ansible/ansible-modules-extras/issues/3661">
                link = li.find(
                    u'a',
                    {u'class': lambda L: L and u'js-navigation-open' in L}
                )
                href = link.attrs[u'href']

                if not href.startswith(self.baseurl):
                    href = self.baseurl + href

                if u'issues' in href:
                    itype = u'issue'
                else:
                    itype = u'pullrequest'
                title = link.text.strip()

                status_txt = None
                status_state = None
                review_txt = None
                status = li.find(u'div', {u'class': u'commit-build-statuses'})
                if status:
                    status_a = status.find(u'a')
                    status_txt = status_a.attrs[u'aria-label'].lower().strip()
                    status_state = status_txt.split(u':')[0]

                review_txt = None
                review = li.find(
                    u'a',
                    {u'aria-label': lambda L: L and u'review' in L}
                )
                if review:
                    review_txt = review.text.lower().strip()
                else:
                    review_txt = None

                labels = []
                alabels = li.findAll(
                    u'a',
                    {u'class': lambda L: L.startswith(u'label')}
                )
                for alabel in alabels:
                    labels.append(alabel.text)

                data[u'issues'][number] = {
                    u'state': state,
                    u'labels': sorted(set(labels)),
                    u'merged': merged,
                    u'href': href,
                    u'type': itype,
                    u'number': number,
                    u'title': title,
                    u'ci_state': status_state,
                    u'ci_message': status_txt,
                    u'review_message': review_txt,
                    u'created_at': created_at,
                    u'updated_at': updated_at,
                    u'closed_at': closed_at,
                    u'merged_at': merged_at
                }
        '''

        '''
        # next_page
        next_page = None
        next_a = soup.find(u'a', {u'class': [u'next_page']})
        if next_a:
            next_page = next_a.attrs[u'href']
        data[u'next_page'] = next_page
        '''

        # 2019-02-02
        #   <a id="issue_31602_link" class="link-gray-dark v-align-middle
        #       no-underline h4 js-navigation-open" data-hovercard-type="issue"
        #       data-hovercard-url="/ansible/ansible/issues/31602/ hovercard"
        #       href="/ansible/ansible/issues/31602">TITLE</a>

        refs = soup.findAll(
            'a',
            {'id': lambda L: L and L.startswith('issue_') and L.endswith('_link')}
        )

        for ref in refs:
            issue = {
                'type': ref.attrs['data-hovercard-type'],
                'url': ref.attrs['href'],
                'href': ref.attrs['href'],
                'title': ref.text,
                'number': int(ref.attrs['href'].split('/')[-1]),
                'labels': [],
                'created_at': None,
            }

            # the parent is a div containing all the other info
            idiv = ref.parent

            lspan = idiv.findAll('span')[0]
            for a in lspan.findAll('a'):
                issue['labels'].append(a.text)

            oby = idiv.find('span', {'class': 'opened-by'})
            issue['created_at'] = oby.find('relative-time').attrs['datetime']
            issue['created_by'] = oby.find('a').text

            data['issues'][issue['number']] = issue.copy()


        try:
            data['next_page'] = soup.find('a', {'class': 'next_page'}).attrs['href']
        except AttributeError:
            pass

        return data

    def parse_issue_page_to_summary(self, soup, url=None):
        data = {
            'state': None,
            'labels': [],
            'merged': None,
            'href': None,
            'type': None,
            'number': None,
            'title': None,
            'ci_state': None,
            'ci_message': None,
            'review_message': None,
            'created_at': None,
            'updated_at': None,
            'closed_at': None,
            'merged_at': None
        }

        if url:
            if '/pull/' in url:
                data['type'] = 'pullrequest'
            else:
                data['type'] = 'issue'

        '''
        # <div class="state state-open">
        # <div class="state state-closed">
        state_div = soup.find(
            u'div', {u'class': lambda L: L and
                    L.lower().startswith(u'state state')}
        )

        if not state_div:
            raise Exception(u'no state div')

        if u'state-merged' in state_div.attrs[u'class']:
            data[u'state'] = u'closed'
            data[u'merged'] = True
        elif u'state-closed' in state_div.attrs[u'class']:
            data[u'state'] = u'closed'
            if data[u'type'] == u'pullrequest':
                data[u'merged'] = False
        else:
            data[u'state'] = u'open'
            if data[u'type'] == u'pullrequest':
                data[u'merged'] = False
        '''

        #<span title="Status: Closed" class="State State--red  ">
        #<span title="Status: Open" class="State State--green  ">
        #<span title="Status: Merged" class="State State--purple  ">
        #<span title="Status: Draft" class="State   ">
        state_span = soup.find(
            'span', {'class': lambda L: L and
                    L.lower().startswith('state ')}
        )

        if not state_span:
            raise Exception('no state div')

        if 'merged' in state_span.attrs['title'].lower():
            data['state'] = 'closed'
            data['merged'] = True
        elif 'closed' in state_span.attrs['title'].lower():
            data['state'] = 'closed'
            if data['type'] == 'pullrequest':
                data['merged'] = False
        else:
            data['state'] = 'open'
            if data['type'] == 'pullrequest':
                data['merged'] = False

        title = soup.find('span', {'class': 'js-issue-title'})
        data['title'] = title.text.strip()

        number = soup.find('span', {'class': 'gh-header-number'})
        data['number'] = int(number.text.replace('#', ''))

        '''
        # <div class="TableObject-item TableObject-item--primary">
        to = soup.find(u'div', {u'class': 'TableObject-item TableObject-item--primary'})
        '''

        # <div class="timeline-comment-header-text">
        # <div class="TableObject-item TableObject-item--primary">
        timeline_header = soup.find('div', {'class': 'timeline-comment-header-text'})
        if not timeline_header:
            # https://github.com/ansible/ansibullbot/issues/520
            timeline_header = soup.find('div', {'class': 'TableObject-item TableObject-item--primary'})
        timeline_relative_time = timeline_header.find('relative-time')
        if not timeline_relative_time:
            timeline_header = soup.find('h3', {'class': 'timeline-comment-header-text f5 text-normal'})
            timeline_relative_time = timeline_header.find('relative-time')

        data['created_at'] = timeline_relative_time.attrs['datetime']

        if data['merged']:
            # <div class="discussion-item-header" id="event-11140358">
            event_divs = soup.findAll('div', {'id': lambda L: L and L.startswith('event-')})
            for x in event_divs:
                rt = x.find('relative-time')
                data['merged_at'] = rt.attrs['datetime']
                data['closed_at'] = rt.attrs['datetime']
                data['updated_at'] = rt.attrs['datetime']
        elif data['state'] == 'closed':
            close_div = soup.find('div', {'class': 'discussion-item discussion-item-closed'})
            closed_rtime = close_div.find('relative-time')
            data['closed_at'] = closed_rtime.attrs['datetime']
            data['updated_at'] = closed_rtime.attrs['datetime']

        comments = []
        comment_divs = soup.findAll('div', {'class': 'timeline-comment-wrapper js-comment-container'})
        for cd in comment_divs:
            rt = cd.find('relative-time')
            if rt:
                comments.append(rt.attrs['datetime'])

        commits = []
        if data['type'] == 'pullrequest':
            commit_divs = soup.findAll('div', {'class': 'discussion-item discussion-commits'})
            for cd in commit_divs:
                rt = cd.find('relative-time')
                if rt:
                    commits.append(rt.attrs['datetime'])

        if not data['updated_at']:
            events = comments + commits
            events = sorted(set(events))
            if events:
                data['updated_at'] = events[-1]
            else:
                data['updated_at'] = data['created_at']

        return data
