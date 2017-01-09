#!/usr/bin/env python

import json
import logging
import re
import requests
import os
import time
import urllib2

from bs4 import BeautifulSoup


class GithubWebScraper(object):
    baseurl = 'https://github.com'
    summaries = {}

    def get_issue_summaries(self, repo_url, cachefile=None):
        # https://github.com/ansible/ansible-modules-extras/issues?q=is%3Aopen

        issues = {}

        if cachefile is None:
            cachefile = '/tmp/%s_issue_summaries.json' \
                % repo_url.split('/')[-1]

        if os.path.isfile(cachefile):
            with open(cachefile, 'rb') as f:
                issues = json.load(f)

        url = repo_url
        url += '/issues'
        url += '?'
        url += 'q='
        url += urllib2.quote('sort:updated-desc')

        rr = self._request_url(url)
        soup = BeautifulSoup(rr.text, 'html.parser')
        data = self._parse_issue_summary_page(soup)
        issues.update(data['issues'])

        while data['next_page']:
            rr = self._request_url(self.baseurl + data['next_page'])
            soup = BeautifulSoup(rr.text, 'html.parser')
            data = self._parse_issue_summary_page(soup)
            if not data['next_page'] or not data['issues']:
                break

            changes = False
            for k,v in data['issues'].iteritems():
                v['href'] = self.baseurl + v['href']
                if str(k) not in issues:
                    changes = True
                elif v != issues[str(k)]:
                    changes = True
                issues[str(k)] = v

            if not changes:
                break

        with open(cachefile, 'wb') as f:
            f.write(json.dumps(issues, sort_keys=True, indent=2))

        #import epdb; epdb.st()
        return issues

    def get_single_issue_summary(self, repo_url, number, cachefile=None):

        issues = {}

        if cachefile is None:
            cachefile = '/tmp/%s_issue_summaries.json' \
                % repo_url.split('/')[-1]

        if os.path.isfile(cachefile):
            with open(cachefile, 'rb') as f:
                issues = json.load(f)

        url = self.baseurl + '/' + repo_url
        url += '/issues'
        url += '?'
        url += 'q=%s' % number

        rr = self._request_url(url)
        soup = BeautifulSoup(rr.text, 'html.parser')
        data = self._parse_issue_summary_page(soup)
        issues.update(data['issues'])

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
                print('next_page: %s' % next_page)
                np = next_page[0]
                np = self.baseurl + np
                print('np: %s' % np)

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
        rr = requests.get(url)
        soup = BeautifulSoup(rr.text, 'html.parser')

        commits = soup.findAll('td', {'class': 'blame-commit-info'})
        for commit in commits:
            avatar = commit.find('img', {'class': 'avatar blame-commit-avatar'})
            committer = avatar.attrs.get('alt')
            if committer:
                if committer.startswith('@'):
                    committer = committer.replace('@', '')
                    if committer not in commiters:
                        commiters[committer] = 0
                    commiters[committer] += 1

        return commiters

    def get_raw_content(self, namespace, repo, branch, filepath):
        # https://raw.githubusercontent.com/
        #   ansible/ansibullbot/master/MAINTAINERS-CORE.txt
        url = os.path.join(
            'https://raw.githubusercontent.com',
            namespace,
            repo, branch,
            filepath
        )
        rr = requests.get(url)
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
                import epdb; epdb.st()

        return prs

    def scrape_pullrequest_review(self, number):

        reviews = {
            'users': {},
            'reviews': {}
        }

        url = self.baseurl
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

        if not url:
            url = self.baseurl
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
                last_url = self.baseurl + last_page.attrs['href']
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
            print(url)
            rr = requests.get(url, headers=headers)
            if rr.reason == 'Too Many Requests':
                logging.debug('too many requests, sleeping %ss' % sleep)
                print('too many requests, sleeping %ss' % sleep)
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
                #import epdb; epdb.st()

                # <a class="link-gray-dark no-underline h4 js-navigation-open"
                # href="/ansible/ansible-modules-extras/issues/3661">
                link = li.find(
                    'a',
                    {'class': lambda L: L and 'js-navigation-open' in L}
                )
                href = link.attrs['href']
                if 'issues' in href:
                    itype = 'issue'
                else:
                    itype = 'pullrequest'
                title = link.text.strip()
                #import epdb; epdb.st()

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

                data['issues'][number] = {
                    'state': state,
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
