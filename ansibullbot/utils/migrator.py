#!/usr/bin/env python

import json
import logging
import requests
import sys
import time
from tenacity import retry
from tenacity import stop_after_attempt
from tenacity import wait_fixed
from urlparse import urlparse

from ansibullbot.utils.gh_gql_client import GithubGraphQLClient


class IssueMigrator(object):
    def __init__(self, token):
        self.token = token
        self.postcount = 0
        self.s = requests.Session()
        self.migration_map = {}

    def get_headers(self):
        headers = {'Authorization': 'token %s' % self.token}
        return headers

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(60*5))
    def __post(self, url, headers, payload):

        logging.info('POSTCOUNT: {}'.format(self.postcount))

        if self.postcount > 18:
            logging.info('sleep 3m')
            time.sleep(3*60)
            self.postcount = 0

        logging.info(headers)
        rr = self.s.post(url, headers=headers, data=json.dumps(payload))

        if isinstance(rr.json(), dict) and 'documentation_url' in rr.json():
            logging.error(rr.json())
            raise Exception

        self.postcount += 1
        return rr

    def migrate(self, issueurl, destrepo):

        # https://developer.github.com/v3/issues/#create-an-issue
        self.s = requests.Session()

        # split the source into relevant data
        parts = urlparse(issueurl).path.split('/')
        src_repo = '/'.join(parts[1:3])
        src_number = int(parts[-1])
        src_api_url = 'https://api.github.com/repos/{}/issues/{}'.format(src_repo, src_number)

        # get the api data
        src_rr = self.s.get(src_api_url, headers=self.get_headers())
        src_data = src_rr.json()

        # get the comments
        src_comment_url = src_api_url + '/comments'
        src_comment_rr = self.s.get(src_comment_url, headers=self.get_headers())
        src_comment_data = src_comment_rr.json()

        # paginate for more comments
        if len(src_comment_data) != src_data['comments'] or src_comment_rr.links:
            while 'next' in src_comment_rr.links:
                src_comment_rr = self.s.get(src_comment_rr.links['next']['url'], headers=self.get_headers())
                src_comment_data += src_comment_rr.json()

        if not self.migration_map.get(issueurl, {}).get('new'):

            # create the post url
            new_post_url = 'https://api.github.com/repos/{}/issues'.format(destrepo)

            # create the payload
            newbody = 'From @{} on {}\r\n'.format(
                src_data['user']['login'],
                src_data['created_at']
            )
            newbody += src_data['body'] + '\r\n'
            newbody += 'Copied from original issue: {}#{}\r\n'.format(src_repo, src_number)

            payload = {
                'title': src_data['title'],
                'body': newbody
            }

            # create the new issue
            logging.info('copy {} to {}'.format(issueurl, destrepo))
            new_rr = self.__post(new_post_url, self.get_headers(), payload)

            new_data = new_rr.json()
            new_api_issue = new_rr.json()['url']
            new_html_issue = new_rr.json()['html_url']

            self.migration_map[issueurl] = {}
            self.migration_map[issueurl]['new'] = new_html_issue
            self.migration_map[issueurl]['comments'] = []

        # add the comments
        totalc = len(src_comment_data)
        new_comments_url = new_data['comments_url']
        for idc,comment in enumerate(src_comment_data):

            if '<!-- boilerplate: repomerge -->' in comment['body']:
                logging.info('skip comment {} of {} -- {}'.format(idc, totalc, new_html_issue))
                continue

            if '<!--- boilerplate: issue_renotify_maintainer --->' in comment['body']:
                logging.info('skip comment {} of {} -- {}'.format(idc, totalc, new_html_issue))
                continue

            if idc in self.migration_map[issueurl]['comments']:
                logging.info('skip comment {} of {} -- {}'.format(idc, totalc, new_html_issue))
                continue

            newbody = 'From @{} on {}\r\n\r\n'.format(
                comment['user']['login'],
                src_data['created_at']
            )
            newbody += comment['body']
            payload = {'body': newbody}
            logging.info('copy comment {} of {} to {}'.format(idc, totalc, new_html_issue))
            self.__post(new_comments_url, self.get_headers(), payload)
            self.migration_map[issueurl]['comments'].append(idc)

        # add note about migration in old issue
        comment = 'This issue was migrated to {}\r\n'.format(new_html_issue)
        payload = {'body': comment}
        curl = src_api_url + '/comments'
        logging.info('note migration in {}'.format(issueurl))
        self.__post(curl, self.get_headers(), payload)

        # close the old issue
        payload = {'state': 'closed'}
        logging.info('close {}'.format(issueurl))
        closure_rr = self.s.patch(src_api_url, headers=self.get_headers(), data=json.dumps(payload))
        if closure_rr.status_code != 200:
            logging.info('closing {} failed'.format(issueurl))

        self.s.close()
