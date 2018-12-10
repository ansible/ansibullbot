#!/usr/bin/env python

import logging
import requests
import time
from tenacity import retry
from tenacity import stop_after_attempt
from tenacity import wait_fixed
from six.moves.urllib.parse import urlparse

from ansibullbot._json_compat import json_dumps

class IssueMigrator(object):
    def __init__(self, token):
        self.token = token
        self.postcount = 0
        self.s = requests.Session()
        self.migration_map = {}

    def get_headers(self):
        headers = {u'Authorization': u'token %s' % self.token}
        return headers

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(60*5))
    def __post(self, url, headers, payload):

        logging.info(u'POSTCOUNT: {}'.format(self.postcount))

        if self.postcount > 18:
            logging.info(u'sleep 2m')
            time.sleep(2*60)
            self.postcount = 0

        logging.info(headers)
        rr = self.s.post(url, headers=headers, data=json_dumps(payload))

        if isinstance(rr.json(), dict) and u'documentation_url' in rr.json():
            logging.error(rr.json())
            raise Exception

        self.postcount += 1
        return rr

    def migrate(self, issueurl, destrepo):

        # https://developer.github.com/v3/issues/#create-an-issue
        self.s = requests.Session()

        # split the source into relevant data
        parts = urlparse(issueurl).path.split(u'/')
        src_repo = u'/'.join(parts[1:3])
        src_number = int(parts[-1])
        src_api_url = u'https://api.github.com/repos/{}/issues/{}'.format(src_repo, src_number)

        # get the api data
        src_rr = self.s.get(src_api_url, headers=self.get_headers())
        src_data = src_rr.json()

        # get the labels
        labels = sorted([x[u'name'] for x in src_data[u'labels']])
        vlabel = [x for x in labels if x.startswith(u'affects_')]
        if len(vlabel) >= 1:
            vlabel = vlabel[0]
        else:
            vlabel = None

        # get the comments
        src_comment_url = src_api_url + u'/comments'
        src_comment_rr = self.s.get(src_comment_url, headers=self.get_headers())
        src_comment_data = src_comment_rr.json()

        # paginate for more comments
        if len(src_comment_data) != src_data[u'comments'] or src_comment_rr.links:
            while u'next' in src_comment_rr.links:
                src_comment_rr = self.s.get(src_comment_rr.links[u'next'][u'url'], headers=self.get_headers())
                src_comment_data += src_comment_rr.json()

        if not self.migration_map.get(issueurl, {}).get(u'new'):

            # create the post url
            new_post_url = u'https://api.github.com/repos/{}/issues'.format(destrepo)

            # create the payload
            newbody = u'From @{} on {}\r\n'.format(
                src_data[u'user'][u'login'],
                src_data[u'created_at']
            )
            newbody += src_data[u'body'] + u'\r\n'
            newbody += u'Copied from original issue: {}#{}\r\n'.format(src_repo, src_number)

            payload = {
                u'title': src_data[u'title'],
                u'body': newbody
            }

            # create the new issue
            logging.info(u'copy {} to {}'.format(issueurl, destrepo))
            new_rr = self.__post(new_post_url, self.get_headers(), payload)

            new_data = new_rr.json()
            #new_api_issue = new_rr.json()['url']
            new_html_issue = new_rr.json()[u'html_url']

            self.migration_map[issueurl] = {}
            self.migration_map[issueurl][u'new'] = new_html_issue
            self.migration_map[issueurl][u'comments'] = []

        else:

            # need to fetch the api data for the new issue
            newurl = self.migration_map.get(issueurl, {}).get(u'new')
            parts = urlparse(newurl).path.split(u'/')
            new_repo = u'/'.join(parts[1:3])
            new_number = int(parts[-1])
            new_api_url = u'https://api.github.com/repos/{}/issues/{}'.format(new_repo, new_number)
            new_rr = self.s.get(new_api_url, headers=self.get_headers())
            new_data = new_rr.json()
            new_html_issue = new_rr.json()[u'html_url']

        # add the version label if known
        if vlabel:
            clabels = [x[u'name'] for x in new_data[u'labels']]
            if vlabel not in clabels:
                label_url = new_data[u'labels_url']
                label_url = label_url.split(u'{')[0]
                payload = [vlabel]
                logging.info(u'adding {} label to {}'.format(vlabel, new_html_issue))
                new_rr = self.__post(label_url, self.get_headers(), payload)

        # add the comments
        totalc = len(src_comment_data)
        new_comments_url = new_data[u'comments_url']
        for idc, comment in enumerate(src_comment_data):

            if u'<!-- boilerplate: repomerge -->' in comment[u'body']:
                logging.info(u'skip comment {} of {} -- {}'.format(idc, totalc, new_html_issue))
                continue

            if u'<!--- boilerplate: issue_renotify_maintainer --->' in comment[u'body']:
                logging.info(u'skip comment {} of {} -- {}'.format(idc, totalc, new_html_issue))
                continue

            if idc in self.migration_map[issueurl][u'comments']:
                logging.info(u'skip comment {} of {} -- {}'.format(idc, totalc, new_html_issue))
                continue

            newbody = u'From @{} on {}\r\n\r\n'.format(
                comment[u'user'][u'login'],
                src_data[u'created_at']
            )
            newbody += comment[u'body']
            payload = {u'body': newbody}
            logging.info(u'copy comment {} of {} to {}'.format(idc, totalc, new_html_issue))
            self.__post(new_comments_url, self.get_headers(), payload)
            self.migration_map[issueurl][u'comments'].append(idc)

        # add note about migration in old issue
        comment = u'This issue was migrated to {}\r\n'.format(new_html_issue)
        payload = {u'body': comment}
        curl = src_api_url + u'/comments'
        logging.info(u'note migration in {}'.format(issueurl))
        self.__post(curl, self.get_headers(), payload)

        # close the old issue
        payload = {u'state': u'closed'}
        logging.info(u'close {}'.format(issueurl))
        closure_rr = self.s.patch(src_api_url, headers=self.get_headers(), data=json_dumps(payload))
        if closure_rr.status_code != 200:
            logging.info(u'closing {} failed'.format(issueurl))

        self.s.close()
