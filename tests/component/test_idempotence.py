#!/usr/bin/env python

import glob
import json
import os

from tests.utils.componentmocks import BotMockManager

from ansibullbot.triagers.ansible import AnsibleTriage


class TestIdempotence:

    def test_no_actions_on_second_run(self, *args, **kwargs):

        '''Verify no actions were taken on a subsequent run'''

        with BotMockManager() as mm:

            print(type(mm))
            print(dir(mm))
            print(hasattr(mm, 'issuedb'))
            mm.issuedb.debug = True

            bot_args = [
                '--debug',
                '--verbose',
                #'--only_issues',
                '--ignore_module_commits',
                '--skip_module_repos',
                '--cachedir=%s' % mm.cachedir,
                '--logfile=%s' % os.path.join(mm.cachedir, 'bot.log'),
                '--no_since',
                #'--id=2',
                #'--id=1',
                '--force'
            ]

            # create a bug report
            body = [
                '#### ISSUE TYPE',
                'bug report',
                '#### SUMMARY',
                'does not work.',
                '#### COMPONENT NAME',
                'vmware_guest',
                '#### ANSIBLE VERSION',
                '2.9.0'
            ]
            mm.issuedb.add_issue(body='\n'.join(body), login='profleonard')

            # create a PR that fixes #1
            pbody = body[:]
            pbody[3] = 'fixes #1'
            mm.issuedb.add_issue(body='\n'.join(pbody), itype='pull', login='jeb')
            mm.issuedb.add_cross_reference(number=1, reference=2)

            # add more random issues
            for x in range(0, 5):
                mm.issuedb.add_issue(body='\n'.join(body), login='clouddev')

            # add needs info issue
            mm.issuedb.add_issue(body="I don't like issue templates!", login='clouddev')

            AT = AnsibleTriage(args=bot_args)
            for x in range(0, 2):
                print('################################################################')
                print('                     START RUN')
                print('################################################################')
                AT.run()
                print('################################################################')
                print('                     STOP RUN')
                print('################################################################')

            print('# issuedb %s' % id(mm.issuedb))

            # /tmp/ansibot.test.isxYlS/ansible/ansible/issues/1/meta.json                
            metafiles = glob.glob('%s/*/meta.json' % os.path.join(mm.cachedir, 'ansible', 'ansible', 'issues'))
            metafiles = sorted(metafiles)
            for mf in metafiles:

                with open(mf, 'r') as f:
                    meta = json.loads(f.read())

                print('checking %s' % mf)

                # ensure no actions were created on the last run
                for k,v in meta['actions'].items():
                    assert not v
