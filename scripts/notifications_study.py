#!/usr/bin/env python3

import hashlib
import json
import logging
import os
import re
import time

from pprint import pprint

from ansibullbot.utils.gh_gql_client import GithubGraphQLClient
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper

import ansibullbot.constants as C

import requests_cache
requests_cache.install_cache('/tmp/requests_cache')


def report(byissue):
    loginds = {}
    for issue, idata in byissue.items():
        for login, ldata in idata['mentions'].items():
            if login not in loginds:
                loginds[login] = []
            loginds[login].append(ldata)
    report_by_login(loginds)

    report_by_issue(byissue)

def report_by_login(ds):
    dates = set()
    logins = set()
    for k,v in ds.items():
        logins.add(k)
        for event in v:
            for event_key in ['responded', 'mentioned']:
                if event[event_key] is not None:
                    dates.add(event[event_key])

    logins = sorted(logins)
    dates = sorted(dates)

    #print('%s -> %s' % (dates[0], dates[-1]))
    response_averages = []

    for login, events in ds.items():
        attempts = []
        for event in events:

            if event['mentioned'] and not event['responded']:
                attempts.append(False)
            elif event['mentioned'] and event['responded']:
                if event['mentioned'] < event['responded']:
                    attempts.append(True)

        if not attempts:
            continue

        responded = float(len([x for x in attempts if x])) / float(len(attempts))
        response_averages.append([login, responded, len(attempts)])

    response_averages = sorted(response_averages, key=lambda x: x[1], reverse=True)
    #pprint(response_averages)

    bins = {}
    binrange = list(range(0, 11))
    for idb,_bin in enumerate(binrange):
        _bin = _bin * 10
        if _bin not in bins:
            bins[_bin] = 0
        _min = _bin
        try:
            _max = binrange[idb+1] * 10
        except IndexError:
            _max = _bin + 1
        for ra in response_averages:
            thisra = ra[1] * 100
            #if _min > 0:
            #    import epdb; epdb.st()
            if thisra >= _min and thisra < _max:
                bins[_bin] += 1

    print('%s -> %s' % (dates[0], dates[-1]))
    for _bin,res in bins.items():
        print('>= %s%% notification response %s users' % (_bin, res))
    print('')
    print('total logins pinged: %s' % len(logins))
    print('%% of users who never respond to pings: %s' % (float(bins[0]) / float(len(logins)) * 100))
    #import epdb; epdb.st()


def report_by_issue(ds):
    attempts = []
    for issue, idata in ds.items():
        if not idata['mentioned']:
            continue
        if idata['mentioned'] and idata['responded']:
            attempts.append(True)
        else:
            attempts.append(False)

    missed = float(len([x for x in attempts if not x])) / float(len(attempts))

    print('')
    print('%s%% of the last %s issues never got cc responses' % (missed * 100, len(ds.keys())))
    print('')


class Scraper:

    def __init__(self):
        self.gh = GithubWrapper(None, token=C.DEFAULT_GITHUB_TOKEN)

        self.cachedir  = '/tmp/pings.cache'
        if not os.path.exists(self.cachedir):
            os.makedirs(self.cachedir)

        bylogin = {}
        byissue = {}

        numbers = self.get_numbers()
        for idn,number in enumerate(numbers):

            logging.info('%s|%s issue %s' % (len(numbers), idn+1, number))

            #if idn < 6000:
            #    continue

            if idn > 7000:
                break

            issue = self.get_issue(number)

            if 'url' not in issue:
                continue

            url = issue['url']
            labels = [x['name'] for x in issue['labels']]
            login = issue['user']['login']

            byissue[url] = {
                'login': login,
                'team': set(),
                'mentions': {},
                'mentioned': None,
                'responded': None,
                'bug': 'bug' in labels,
                'feature': 'feature' in labels,
                'pull': 'pull' in issue['html_url']
            }

            comments = self.get_comments(number)
            if not comments:
                continue

            for comment in comments:

                if comment is None:
                    import epdb; epdb.st()
                if comment['user'] is None:
                    #import epdb; epdb.st()
                    continue

                login = comment['user']['login']
                mentions = self.parse_mentions(comment['body'])

                if mentions:
                    for mention in mentions:
                        byissue[url]['team'].add(mention)

                        if mention not in byissue[url]['mentions']:
                            byissue[url]['mentions'][mention] = {
                                'mentioned': comment['created_at'],
                                'responded': None
                            }
                        if comment['created_at'] < byissue[url]['mentions'][mention]['mentioned']:
                            byissue[url]['mentions'][mention]['mentioned'] = comment['created_at']

                    # team generally mentioned?
                    if byissue[url]['mentioned'] is None or \
                            byissue[url]['mentioned'] > comment['created_at']:
                        byissue[url]['mentioned'] = comment['created_at']

            for comment in comments:
                if comment is None:
                    import epdb; epdb.st()
                if comment['user'] is None:
                    #import epdb; epdb.st()
                    continue

                login = comment['user']['login']

                if login in byissue[url]['team']:
                    # team generally responded?
                    if byissue[url]['responded'] is None or \
                            byissue[url]['responded'] > comment['created_at']:
                        byissue[url]['responded'] = comment['created_at']
                    
                    if byissue[url]['mentions'][mention]['responded'] is None or \
                            byissue[url]['mentions'][mention]['responded'] > comment['created_at']:
                        byissue[url]['mentions'][mention]['responded'] = comment['created_at']

        report(byissue)

    def get_numbers(self):
        gq_cache_file = os.path.join(self.cachedir, 'gql_cache.json')

        if not os.path.exists(gq_cache_file):
            gqlc = GithubGraphQLClient(C.DEFAULT_GITHUB_TOKEN)
            summaries = gqlc.get_issue_summaries('ansible/ansible')
            with open(gq_cache_file, 'w') as f:
                f.write(json.dumps(summaries))
        else:
            with open(gq_cache_file, 'r') as f:
                summaries = json.loads(f.read())

        numbers = set()
        for k,v in summaries.items():
            #if v['state'] != 'open':
            #    continue
            numbers.add(v['number'])
        numbers = sorted(numbers, reverse=True)
        return numbers

    def get_issue(self, number):
        issue_url = 'https://api.github.com/repos/ansible/ansible/issues/%s' % number
        issue = self.get_url(issue_url)
        return issue

    def get_comments(self, number):
        issue_url = 'https://api.github.com/repos/ansible/ansible/issues/%s' % number
        issue = self.get_url(issue_url)
        comments_url = 'https://api.github.com/repos/ansible/ansible/issues/%s/comments' % number
        comments = self.get_url(comments_url)

        reviews = []
        if 'pull' in issue['html_url']:
            pull = self.get_url(issue['pull_request']['url'])
            if pull['review_comments'] > 0:
                reviews = self.get_url(pull['review_comments_url'])

        return comments + reviews

    def get_url(self, url):
        cachedir = os.path.join(self.cachedir, 'requests')
        if not os.path.exists(cachedir):
            os.makedirs(cachedir)
        m = hashlib.md5()
        m.update(url.encode('utf-8'))
        digest = m.hexdigest()

        cachefile = os.path.join(cachedir, '%s.json' % digest)
        if not os.path.exists(cachefile):
            data = self.gh.get_request(url)
            with open(cachefile, 'w') as f:
                f.write(json.dumps(data))
        else:
            with open(cachefile, 'r') as f:
                data = json.loads(f.read())

        return data

    def parse_mentions(self, body):

        mentioned = set()

        if '@' in body:
            words = body.split()
            for word in words:
                if word.startswith('@'):
                    login = word.replace('@', '')
                    if not login.strip():
                        continue
                    if '"' in login:
                        continue
                    if "'" in login:
                        continue
                    if '(' in login:
                        continue
                    if ')' in login:
                        continue
                    if '/' in login:
                        continue
                    if '\\' in login:
                        continue
                    if '{' in login:
                        continue
                    login = login.rstrip(',')

                    if login:
                        mentioned.add(login)

        return list(mentioned)


def main():

    logging.level = logging.DEBUG
    logFormatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

    scraper = Scraper()


if __name__ == "__main__":
    main()
