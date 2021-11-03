# https://developer.github.com/v4/explorer/
# https://developer.github.com/v4/guides/forming-calls/

import json
import logging
import time

from collections import defaultdict
from operator import itemgetter
from string import Template

import requests

from ansibullbot._text_compat import to_bytes, to_text
from ansibullbot.utils.receiver_client import post_to_receiver


QUERY_FIELDS = """
id
url
number
state
createdAt
updatedAt
repository {
    nameWithOwner
}
"""

QUERY_TEMPLATE = """
{
    repository(owner:"$owner", name:"$repo") {
        $object_type($object_params) {
            pageInfo {
                startCursor
                endCursor
                hasNextPage
                hasPreviousPage
            }
            edges {
                node {
                $fields
                }
            }
        }
    }
}
"""

QUERY_TEMPLATE_SINGLE_NODE = """
{
    repository(owner:"$owner", name:"$repo") {
          $object_type($object_params){
            $fields
        }
    }
}
"""

QUERY_TEMPLATE_BLAME = """
query {
  repository(owner: "$owner", name: "$repo") {
    ... on Repository {
      ref(qualifiedName: "$branch") {
        target {
          ... on Commit {
            blame(path: "$path") {
              ranges {
                commit {
                  oid
                  author {
                    email
                    user {
                      login
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


class GithubGraphQLClient:
    baseurl = 'https://api.github.com/graphql'

    def __init__(self, token, server=None):
        if server:
            # this is for testing
            self.baseurl = server.rstrip('/') + '/graphql'
        self.token = token
        self.headers = {
            'Accept': 'application/json',
            'Authorization': 'Bearer %s' % self.token,
        }

    def get_issue_summaries(self, repo_url):
        """Return a dict of all issue summaries with numbers as keys

        Adds a compatibility method for the webscraper

        Args:
            repo_url  (str): username/repository
        """
        owner = repo_url.split('/', 1)[0]
        repo = repo_url.split('/', 1)[1]
        summaries = self.get_all_summaries(owner, repo)

        issues = {}
        for x in summaries:
            issues[to_text(x['number'])] = x

        # keep the summaries for out of band analysis
        repodata = {
            'user': repo_url.split('/', 1)[0],
            'repo': repo_url.split('/', 1)[1],
        }
        post_to_receiver('summaries', repodata, issues)

        return issues

    def get_all_summaries(self, owner, repo):
        """Collect all the summary data for issues and pullreuests

        Args:
            owner (str): the github namespace
            repo  (str): the github repository
        """
        isummaries = self.get_summaries(owner, repo, otype='issues')
        psummaries = self.get_summaries(owner, repo, otype='pullRequests')
        summaries = []
        for iis in isummaries:
            summaries.append(iis)
        for prs in psummaries:
            summaries.append(prs)

        if not summaries:
            return []

        numbers = [x['number'] for x in summaries]
        if numbers:
            missing = (x for x in range(1, numbers[-1]) if x not in numbers)
        else:
            missing = []
        for x in missing:
            data = {
                'created_at': None,
                'updated_at': None,
                'id': None,
                'number': x,
                'state': 'closed',
                'repository': {
                    'nameWithOwner': '%s/%s' % (owner, repo)
                },
                'type': None
            }
            summaries.append(data)

        return sorted(summaries, key=itemgetter('number'))

    def get_summaries(self, owner, repo, otype='issues', last=None, first='first: 100', states='states: OPEN', paginate=True):
        """Collect all the summary data for issues or pullreuests

        Args:
            owner     (str): the github namespace
            repo      (str): the github repository
            otype     (str): issues or pullRequests
            first     (str): number of nodes per page, oldest to newest
            last      (str): number of nodes per page, newest to oldest
            states    (str): open or closed issues
            paginate (bool): recurse through page results

        """

        templ = Template(QUERY_TEMPLATE)
        after = None
        nodes = []
        pagecount = 0
        while True:
            logging.debug('%s/%s %s pagecount:%s nodecount: %s' %
                          (owner, repo, otype, pagecount, len(nodes)))

            issueparams = ', '.join([x for x in [states, first, last, after] if x])
            query = templ.substitute(owner=owner, repo=repo, object_type=otype, object_params=issueparams, fields=QUERY_FIELDS)

            payload = {
                'query': to_text(query, 'ascii', 'ignore').strip(),
                'variables': '{}',
                'operationName': None
            }
            rr = requests.post(self.baseurl, headers=self.headers, data=json.dumps(payload))
            if not rr.ok:
                break
            data = rr.json()
            if not data:
                break

            # keep each edge/node/issue
            for edge in data.get('data', {}).get('repository', {}).get(otype, {}).get('edges', []):
                node = edge['node']
                self.update_node(node, otype.lower()[:-1], owner, repo)
                nodes.append(node)

            if not paginate:
                break

            pageinfo = data.get('data', {}).get('repository', {}).get(otype, {}).get('pageInfo')
            if not pageinfo:
                break
            if not pageinfo.get('hasNextPage'):
                break

            after = 'after: "%s"' % pageinfo['endCursor']
            pagecount += 1

        return nodes

    def get_summary(self, repo_url, otype, number):
        """Collect all the summary data for issues or pull requests ids

        Args:
            repo_url  (str): repository URL
            otype     (str): issue or pullRequest
            number    (str): Identifies the pull-request or issue, for example: 12345
        """
        owner = repo_url.split('/', 1)[0]
        repo = repo_url.split('/', 1)[1]

        template = Template(QUERY_TEMPLATE_SINGLE_NODE)

        query = template.substitute(owner=owner, repo=repo, object_type=otype, object_params='number: %s' % number, fields=QUERY_FIELDS)

        payload = {
            'query': to_bytes(query, 'ascii', 'ignore').strip(),
            'variables': '{}',
            'operationName': None
        }
        payload['query'] = to_text(payload['query'], 'ascii')

        rr = requests.post(self.baseurl, headers=self.headers, data=json.dumps(payload))
        data = rr.json()

        node = data['data']['repository'][otype]
        if node is None:
            return

        self.update_node(node, otype, owner, repo)

        return node

    def update_node(self, node, node_type, owner, repo):
        node['state'] = node['state'].lower()
        node['created_at'] = node.get('createdAt')
        node['updated_at'] = node.get('updatedAt')

        if 'repository' not in node:
            node['repository'] = {}

        if 'nameWithOwner' not in node['repository']:
            node['repository']['nameWithOwner'] = '%s/%s' % (owner, repo)

        node['type'] = node_type

    def get_usernames_from_filename_blame(self, owner, repo, branch, filepath):
        template = Template(QUERY_TEMPLATE_BLAME)
        committers = defaultdict(set)
        emailmap = {}

        query = template.substitute(owner=owner, repo=repo, branch=branch, path=filepath)

        payload = {
            'query': to_text(
                to_bytes(query, 'ascii', 'ignore'),
                'ascii',
            ).strip(),
            'variables': '{}',
            'operationName': None
        }
        response = self.requests(payload)
        data = response.json()

        nodes = data['data']['repository']['ref']['target']['blame']['ranges']
        """
        [
            'commit':
            {
                'oid': 'a3132e5dd6acc526ce575f6db134169c7090f72d',
                'author':
                {
                    'email': 'user@mail.example',
                    'user': {'login': 'user'}
                }
            }
        ]
        """
        for node in nodes:
            node = node['commit']
            if not node['author']['user']:
                continue
            github_id = node['author']['user']['login']
            committers[github_id].add(node['oid'])
            # emails come from 'git log --follow' but all github id aren't fetch:
            # - GraphQL/git 'blame' don't list all commits
            # - GraphQL 'history' neither because 'history' is like 'git log' but without '--follow'
            email = node['author'].get('email')
            if email and email not in emailmap:
                emailmap[email] = github_id

        for github_id, commits in committers.items():
            committers[github_id] = list(commits)
        return committers, emailmap

    def requests(self, payload):
        exc = None
        for i in range(5):
            response = requests.post(self.baseurl, headers=self.headers, data=json.dumps(payload))
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                exc = e
                time.sleep(2)
                continue

            # GitHub GraphQL will happily return a 200 result with errors. One
            # must dig through the data to see if there were errors.
            errors = response.json().get('errors')
            if errors:
                msgs = ', '.join([e['message'] for e in errors])
                exc = requests.exceptions.InvalidSchema('Error(s) from graphql: %s' % msgs)
                time.sleep(2)
                continue

            return response

        raise exc
