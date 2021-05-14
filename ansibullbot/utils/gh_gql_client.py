# https://developer.github.com/v4/explorer/
# https://developer.github.com/v4/guides/forming-calls/

import jinja2
import json
import logging
import requests
from collections import defaultdict
from operator import itemgetter

from tenacity import retry, wait_random, stop_after_attempt
from ansibullbot._text_compat import to_bytes, to_text
from ansibullbot.utils.receiver_client import post_to_receiver

import ansibullbot.constants as C


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
    repository(owner:"{{ OWNER }}", name:"{{ REPO }}") {
        {{ OBJECT_TYPE }}({{ OBJECT_PARAMS }}) {
            pageInfo {
                startCursor
                endCursor
                hasNextPage
                hasPreviousPage
            }
            edges {
                node {
                {{ FIELDS }}
                }
            }
        }
    }
}
"""

QUERY_TEMPLATE_SINGLE_NODE = """
{
    repository(owner:"{{ OWNER }}", name:"{{ REPO }}") {
          {{ OBJECT_TYPE }}({{ OBJECT_PARAMS }}){
            {{ FIELDS }}
        }
    }
}
"""

QUERY_TEMPLATE_BLAME = """
query {
  repository(owner: "{{ OWNER }}", name: "{{ REPO }}") {
    ... on Repository {
      ref(qualifiedName: "{{ BRANCH }}") {
        target {
          ... on Commit {
            blame(path: "{{ PATH }}") {
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
        self.environment = jinja2.Environment()

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

    def get_last_number(self, repo_path):
        """Return the very last issue/pr number opened for a repo
        """
        owner = repo_path.split('/', 1)[0]
        repo = repo_path.split('/', 1)[1]

        isummaries = self.get_summaries(owner, repo, otype='issues',
                                        last='last: 1', first=None, states=None,
                                        paginate=False)
        psummaries = self.get_summaries(owner, repo, otype='pullRequests',
                                        last='last: 1', first=None, states=None,
                                        paginate=False)

        if isummaries[-1]['number'] > psummaries[-1]['number']:
            return isummaries[-1]['number']
        else:
            return psummaries[-1]['number']

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

        templ = self.environment.from_string(QUERY_TEMPLATE)

        # after: "$endCursor"
        after = None

        '''
        # first: 100
        first = 'first: 100'
        # states: OPEN
        states = 'states: OPEN'
        '''

        nodes = []
        pagecount = 0
        while True:
            logging.debug('%s/%s %s pagecount:%s nodecount: %s' %
                          (owner, repo, otype, pagecount, len(nodes)))

            issueparams = ', '.join([x for x in [states, first, last, after] if x])
            query = templ.render(OWNER=owner, REPO=repo, OBJECT_TYPE=otype, OBJECT_PARAMS=issueparams, FIELDS=QUERY_FIELDS)

            payload = {
                #u'query': to_bytes(query, 'ascii', 'ignore').strip(),
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

        template = self.environment.from_string(QUERY_TEMPLATE_SINGLE_NODE)

        query = template.render(OWNER=owner, REPO=repo, OBJECT_TYPE=otype, OBJECT_PARAMS='number: %s' % number, FIELDS=QUERY_FIELDS)

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

        template = self.environment.from_string(QUERY_TEMPLATE_BLAME)
        committers = defaultdict(set)
        emailmap = {}

        query = template.render(OWNER=owner, REPO=repo, BRANCH=branch, PATH=filepath)

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

    @retry(wait=wait_random(min=1, max=2), stop=stop_after_attempt(5))
    def requests(self, payload):
        response = requests.post(self.baseurl, headers=self.headers, data=json.dumps(payload))
        response.raise_for_status()
        # GitHub GraphQL will happily return a 200 result with errors. One
        # must dig through the data to see if there were errors.
        errors = response.json().get('errors')
        if errors:
            msgs = ', '.join([e['message'] for e in errors])
            raise requests.exceptions.InvalidSchema(
                'Error(s) from graphql: %s' % msgs)
        return response


###################################
# TESTING ...
###################################
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    client = GithubGraphQLClient(C.DEFAULT_GITHUB_TOKEN)
    summaries = client.get_all_summaries('ansible', 'ansible')
    ln = client.get_last_number('ansible/ansible')
