#!/usr/bin/env python

import json
import logging
import re
import requests
import os
import shutil
import tempfile
import time
import urllib2

from bs4 import BeautifulSoup


class GithubWebScraper(object):
    cachedir = None
    baseurl = 'https://github.com'
    summaries = {}
    reviews = {}

    def __init__(self, cachedir=None):
        if cachedir:
            self.cachedir = cachedir
        else:
            self.cachedir = '/tmp/gws'
        if not os.path.isdir(self.cachedir):
            os.makedirs(self.cachedir)

    def split_repo_url(self, repo_url):
        rparts = repo_url.split('/')
        rparts = [x.strip() for x in rparts if x.strip()]
        return (rparts[-2], rparts[-1])

    def load_summaries(self, repo_url):
        issues = {}
        ns,repo = self.split_repo_url(repo_url)
        cachefile = os.path.join(self.cachedir, ns, repo, 'summaries.json')
        if os.path.isfile(cachefile):
            try:
                with open(cachefile, 'rb') as f:
                    issues = json.load(f)
            except Exception as e:
                logging.error(e)
                issues = {}
                logging.error('breakpoint!')
                import epdb; epdb.st()
        return issues

    def dump_summaries(self, repo_url, issues, filename="summaries"):

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

        ns,repo = self.split_repo_url(repo_url)
        cachefile = os.path.join(
            self.cachedir,
            ns,
            repo,
            '%s.json' % filename
        )
        if not issues:
            logging.error('breakpoint!')
            import epdb; epdb.st()

        tfh, tfn = tempfile.mkstemp()
        os.close(tfh)
        with open(tfn, 'wb') as f:
            f.write(json.dumps(issues, sort_keys=True, indent=2))

        if os.path.isfile(cachefile):
            os.remove(cachefile)
        shutil.move(tfn, cachefile)

    def dump_summaries_tmp(self, repo_url, issues):
        self.dump_summaries(repo_url, issues, filename="summaries-tmp")

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
            url += urllib2.quote('sort:updated-desc')
        else:
            url = baseurl

        rr = self._request_url(url)
        soup = BeautifulSoup(rr.text, 'html.parser')
        data = self._parse_issue_summary_page(soup)
        if data['issues']:
            issues.update(data['issues'])

        if not baseurl:
            self.dump_summaries_tmp(repo_url, issues)

        while data['next_page']:
            rr = self._request_url(self.baseurl + data['next_page'])
            soup = BeautifulSoup(rr.text, 'html.parser')
            data = self._parse_issue_summary_page(soup)
            if not data['next_page'] or not data['issues']:
                break

            changed = []
            changes = False
            for k,v in data['issues'].iteritems():

                if not isinstance(k, unicode):
                    k = u'%s' % k

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
                    if not isinstance(x, unicode):
                        x = u'%s' % x
                    issues[x] = summary

        # get missing timestamps
        if not baseurl:
            numbers = sorted([int(x) for x in issues.keys()])
            missing = [x for x in numbers if str(x) not in issues or not issues[str(x)]['updated_at']]
            for x in missing:
                summary = self.get_single_issue_summary(repo_url, x, force=True)
                if summary:
                    if not isinstance(x, unicode):
                        x = u'%s' % x
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
            url += str(number)

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
        keys = sorted(set([int(x['number']) for x in issues.keys()]))
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
            #import epdb; epdb.st()
            return tdata

        url = os.path.join(
            'https://raw.githubusercontent.com',
            namespace,
            repo, branch,
            filepath
        )
        rr = requests.get(url)

        if rr.status_code != 200:
            import epdb; epdb.st()

        if usecache:
            if not os.path.isdir(tdir):
                os.makedirs(tdir)
            with open(tfile, 'wb') as f:
                f.write(rr.text.encode('ascii', 'ignore'))

        #import epdb; epdb.st()
        return rr.text

    def scrape_pullrequest_summaries(self):

        prs = {}

        url = self.baseurl
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
                url = self.baseurl + data['next_page']
            else:
                url = None
            if data['prs']:
                prs.update(data['prs'])
            else:
                logging.error('breakpoint!')
                import epdb; epdb.st()

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

        #import epdb; epdb.st()

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
            atxt = rdiv.find('div', {'class': ['discussion-item-header']}).text
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
                findex = tparts.index('from')
                reviewer = tparts[findex+1]
            else:
                action = None
                logging.error('breakpoint!')
                import epdb; epdb.st()

            reviews['reviews'][rid] = {
                'actor': author,
                'action': action,
                'reviewer': reviewer,
                'timestamp': timestamp,
                'outdated': outdated
            }

        # force to ascii
        x = {}
        for k,v in reviews['users'].iteritems():
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
            try:
                rr = requests.get(url, headers=headers)
                if rr.reason == 'Too Many Requests' or rr.status_code == 500:
                    logging.debug(
                        'too many www requests, sleeping %ss' % sleep
                    )
                    time.sleep(sleep)
                    sleep = sleep * 2
                else:
                    failed = False
            except requests.exceptions.ConnectionError:
                # Failed to establish a new connection: [Errno 111] Connection
                # refused',))
                logging.debug('connection refused')
                time.sleep(sleep)
                sleep = sleep * 2

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
        data = {
            'issues': {}
        }

        lis = soup.findAll(
            'li',
            {'class': lambda L: L and L.endswith('issue-row')}
        )

        if lis:
            for li in lis:

                number = li.attrs['id'].split('_')[-1]
                number = int(number)

                # <span aria-label="Closed issue" class="tooltipped
                # tooltipped-n">
                merged = None
                state = None
                cspan = li.find('span', {'aria-label': 'Closed issue'})
                ospan = li.find('span', {'aria-label': 'Open issue'})
                mspan = li.find('span', {'aria-label': 'Merged pull request'})
                cpspan = li.find('span', {'aria-label': 'Closed pull request'})
                opspan = li.find('span', {'aria-label': 'Open pull request'})
                if mspan:
                    state = 'closed'
                    merged = True
                elif ospan:
                    state = 'open'
                elif cspan:
                    state = 'closed'
                elif cpspan:
                    state = 'closed'
                    merged = False
                elif opspan:
                    state = 'open'
                    merged = False
                else:
                    logging.error('breakpoint!')
                    import epdb; epdb.st()

                created_at = None
                updated_at = None
                closed_at = None
                merged_at = None

                timestamp = li.find('relative-time').attrs['datetime']
                updated_at = timestamp
                if merged:
                    merged_at = timestamp
                if state == 'closed':
                    closed_at = timestamp

                # <a class="link-gray-dark no-underline h4 js-navigation-open"
                # href="/ansible/ansible-modules-extras/issues/3661">
                link = li.find(
                    'a',
                    {'class': lambda L: L and 'js-navigation-open' in L}
                )
                href = link.attrs['href']

                if not href.startswith(self.baseurl):
                    href = self.baseurl + href

                if 'issues' in href:
                    itype = 'issue'
                else:
                    itype = 'pullrequest'
                title = link.text.strip()

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

                labels = []
                alabels = li.findAll(
                    'a',
                    {'class': lambda L: L.startswith('label')}
                )
                for alabel in alabels:
                    labels.append(alabel.text)

                data['issues'][number] = {
                    'state': state,
                    'labels': sorted(set(labels)),
                    'merged': merged,
                    'href': href,
                    'type': itype,
                    'number': number,
                    'title': title,
                    'state': state,
                    'ci_state': status_state,
                    'ci_message': status_txt,
                    'review_message': review_txt,
                    'created_at': created_at,
                    'updated_at': updated_at,
                    'closed_at': closed_at,
                    'merged_at': merged_at
                }

        # next_page
        next_page = None
        next_a = soup.find('a', {'class': ['next_page']})
        if next_a:
            next_page = next_a.attrs['href']
        data['next_page'] = next_page

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
            'state': None,
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

        # <div class="state state-open">
        # <div class="state state-closed">
        state_div = soup.find(
            'div', {'class': lambda L: L and
                    L.lower().startswith('state state')}
        )

        if not state_div:
            import epdb; epdb.st()

        if 'state-merged' in state_div.attrs['class']:
            data['state'] = 'closed'
            data['merged'] = True
        elif 'state-closed' in state_div.attrs['class']:
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

        # <div class="TableObject-item TableObject-item--primary">
        to = soup.find('div', {'class': 'TableObject-item TableObject-item--primary'})

        # <div class="timeline-comment-header-text">
        timeline_header = soup.find('div', {'class': 'timeline-comment-header-text'})
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
            data['updated_at'] = events[-1]
            #import epdb; epdb.st()

        #import epdb; epdb.st()
        return data
