#!/usr/bin/env python

# This is a triager for the combined repos that should have happend
# in the 12-2016 timeframe.
#   https://groups.google.com/forum/#!topic/ansible-devel/mIxqxXRsmCI
#   https://groups.google.com/forum/#!topic/ansible-devel/iJouivmSSk4
#   https://github.com/ansible/proposals/issues/30

# Key features:
#   * daemonize mode that can continuously loop and process w/out scripts
#   * closed issues will also be processed (pygithub will kill ratelimits for
#     this, so use a new caching+index tool)
#   * open issues in ansible-modules-[core|extras] will be closed with a note
#     about pr|issue mover
#   * maintainers can be assigned to more than just the files in
#     ansibullbot.ansible/modules
#   * closed issues with active comments will be locked with msg about opening
#     new
#   * closed issues where submitter issues "reopen" command will be reopened
#   * false positives on module issue detection can be corrected by a wide range
#     of people
#   * more people (not just maintainers) should have access to a subset of bot
#     commands
#   * a generic label add|remove command will allow the community to fill in
#     where the bot can't
#   * different workflows should be a matter of enabling different plugins

import json
import logging
import os
import shutil

from ansibullbot.ansibletriager import AnsibleTriager
from ansibullbot.plugins import get_component_match_facts

basepath = os.path.dirname(__file__).split('/')
libindex = basepath[::-1].index('ansibullbot')
libindex = (len(basepath) - 1) - libindex
basedir = '/'.join(basepath[0:libindex])
TEMPLATES = os.path.join(basedir, 'templates')

class HistoryMock:

    def get_component_commands(self, botnames=None):
        return []


class IssueMock:

    _component = None

    def is_issue(self):
        return True
    def is_pullrequest(self):
        return False

    @property
    def title(self):
        return ''

    @property
    def body(self):
        return ''

    @property
    def comments(self):
        return []

    @property
    def files(self):
        return [self._component]

    @property
    def history(self):
        return HistoryMock()

    @property
    def template_data(self):
        return {
            'component_raw': self._component,
            'component name': self._component
        }


class AnsibleSupportReport(AnsibleTriager):

    def __init__(self):
        super().__init__()

    @classmethod
    def create_parser(cls):

        parser = AnsibleTriager.create_parser()

        # report specific
        parser.add_argument("--dest", required=True,
                            help="store the results in this directory")

        return parser

    def run(self):
        '''Emit an html report of each file and it's metadata'''
        component_facts = {}

        filenames = sorted(self.gitrepo.files)
        filenames = [x for x in filenames if not x.startswith('/')]
        filenames = [x for x in filenames if not '__pycache__' in x]
        filenames = [x for x in filenames if not x.endswith('.pyo')]
        filenames = [x for x in filenames if not x.endswith('.pyo')]

        for fn in filenames:
            logging.debug(fn)
            iw = IssueMock()
            iw._component = fn
            try:
                facts = get_component_match_facts(iw, self.component_matcher, [])
                component_facts[fn] = {}
                component_facts[fn]['component'] = facts['component_name']
                component_facts[fn]['support'] = facts['component_matches'][0]['support']
                labels = facts['component_matches'][0]['labels'][:]
                labels += facts['component_labels']
                labels = sorted(set(labels))
                component_facts[fn]['labels'] = ','.join(labels)
                component_facts[fn]['maintainers'] = \
                        ','.join(facts['component_matches'][0]['maintainers'])

            except Exception as e:
                component_facts[fn] = {'error': '%s' % e}
                logging.error(fn)
                logging.error(e)

        logging.info('done matching')

        logging.info('building report in %s' % self.args.dest)
        dest = os.path.expanduser(self.args.dest)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        skel = os.path.join(TEMPLATES, 'metareport')
        shutil.copytree(skel, dest)

        with open(os.path.join(dest, 'data.json'), 'w') as f:
            f.write(json.dumps(list(component_facts.values())))
