#!/usr/bin/env python

import json
import logging
import requests
import time
from tenacity import retry
from tenacity import stop_after_attempt
from tenacity import wait_fixed
from urlparse import urlparse


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
            logging.info('sleep 2m')
            time.sleep(2*60)
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

        # get the labels
        labels = sorted([x['name'] for x in src_data['labels']])
        vlabel = [x for x in labels if x.startswith('affects_')]
        if len(vlabel) >= 1:
            vlabel = vlabel[0]
        else:
            vlabel = None

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
            #new_api_issue = new_rr.json()['url']
            new_html_issue = new_rr.json()['html_url']

            self.migration_map[issueurl] = {}
            self.migration_map[issueurl]['new'] = new_html_issue
            self.migration_map[issueurl]['comments'] = []

        else:

            # need to fetch the api data for the new issue
            newurl = self.migration_map.get(issueurl, {}).get('new')
            parts = urlparse(newurl).path.split('/')
            new_repo = '/'.join(parts[1:3])
            new_number = int(parts[-1])
            new_api_url = 'https://api.github.com/repos/{}/issues/{}'.format(new_repo, new_number)
            new_rr = self.s.get(new_api_url, headers=self.get_headers())
            new_data = new_rr.json()
            new_html_issue = new_rr.json()['html_url']

        # add the version label if known
        if vlabel:
            clabels = [x['name'] for x in new_data['labels']]
            if vlabel not in clabels:
                label_url = new_data['labels_url']
                label_url = label_url.split('{')[0]
                payload = [vlabel]
                logging.info('adding {} label to {}'.format(vlabel, new_html_issue))
                new_rr = self.__post(label_url, self.get_headers(), payload)

        # add the comments
        totalc = len(src_comment_data)
        new_comments_url = new_data['comments_url']
        for idc, comment in enumerate(src_comment_data):

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
