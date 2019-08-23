#!/usr/bin/env python3

import json
import logging
import os
import time

from pprint import pprint

from ansibullbot.utils.gh_gql_client import GithubGraphQLClient
from ansibullbot.wrappers.ghapiwrapper import GithubWrapper

import ansibullbot.constants as C


def main():

    logging.level = logging.DEBUG
    logFormatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

    summaries = None
    gq_cache_file = '/tmp/gql_cache.json'

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
        if v['state'] != 'open':
            continue
        numbers.add(v['number'])
    numbers = sorted(numbers, reverse=True)

    gh = GithubWrapper(None, token=C.DEFAULT_GITHUB_TOKEN)

    for idn,number in enumerate(numbers):
        logging.info('%s|%s issue %s' % (len(numbers), idn+1, number))

        if number > 52979:
            continue

        comments_url = 'https://api.github.com/repos/ansible/ansible/issues/%s/comments' % number
        comments = gh.get_request(comments_url)

        duplicates = {}
        for comment in comments:
            if comment['user']['login'] != 'ansibot':
                continue
            if comment['body'] not in duplicates:
                duplicates[comment['body']] = []
            duplicates[comment['body']].append(comment['id'])


        if duplicates:
            topop = []
            for k,v in duplicates.items():
                if len(v) <= 1:
                    topop.append(k)
            for tp in topop:
                duplicates.pop(tp, None)

            if duplicates:
                for k,v in duplicates.items():
                    dupes = [x for x in comments if x['id'] in v]
                    dupes = sorted(dupes, key=lambda x: x['created_at'])

                    pprint([[x['id'], x['body']] for x in dupes])

                    #if '<!--- boilerplate: notify --->' not in dupes[0]['body']:
                    #    continue

                    #import epdb; epdb.st()

                    for dupe in dupes[1:]:
                        gh.delete_request(dupe['url'])
                    time.sleep(1)


if __name__ == "__main__":
    main()
