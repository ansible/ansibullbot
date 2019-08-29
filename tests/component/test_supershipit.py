#!/usr/bin/env python

import glob
import json
import os

import yaml

from tests.utils.componentmocks import BotMockManager

from ansibullbot.triagers.ansible import AnsibleTriage


class TestSuperShipit:

    def test_supershipit(self, *args, **kwargs):

        with BotMockManager() as mm:

            #mm.issuedb.debug = True

            botmeta = {
                'automerge': True,
                'files': {
                    'lib/ansible/modules/foo/bar.py': {
                        'maintainers': 'zippy',
                        'supershipit': 'jiffy'
                    }
                },
                'macros': {
                }
            }

            bmfile = os.path.join(mm.cachedir, 'BOTMETA.yml')
            with open(bmfile, 'w') as f:
                f.write(yaml.dump(botmeta))

            bot_args = [
                '--debug',
                '--verbose',
                '--ignore_module_commits',
                '--skip_module_repos',
                '--cachedir=%s' % mm.cachedir,
                '--logfile=%s' % os.path.join(mm.cachedir, 'bot.log'),
                '--no_since',
                '--force',
                '--botmetafile=%s' % bmfile
            ]

            # create a bug report
            body = [
                '#### ISSUE TYPE',
                'bugfix pullrequest',
                '',
                '#### SUMMARY',
                'removing some files from ignore.txt',
                '',
                '#### COMPONENT NAME',
                'vmware_guest',
                '',
                '#### ANSIBLE VERSION',
                '2.9.0'
            ]

            mm.issuedb.add_issue(body='\n'.join(body), itype='pull', login='profleonard')
            mm.issuedb.add_issue_file('test/sanity/ignore.txt', number=1, deletions=1)
            mm.issuedb.add_issue_comment('shipit', login='jiffy', number=1)

            AT = AnsibleTriage(args=bot_args)
            AT.run()

            # /tmp/ansibot.test.isxYlS/ansible/ansible/issues/1/meta.json                
            metafiles = glob.glob('%s/*/meta.json' % os.path.join(mm.cachedir, 'ansible', 'ansible', 'issues'))
            metafiles = sorted(metafiles)
            for mf in metafiles:

                with open(mf, 'r') as f:
                    meta = json.loads(f.read())

                import epdb; epdb.st()

