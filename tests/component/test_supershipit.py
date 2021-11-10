import glob
import json
import os

import pytest
import yaml

from tests.utils.componentmocks import BotMockManager
from tests.utils.componentmocks import get_custom_timestamp

from ansibullbot.ansibletriager import AnsibleTriager


class TestSuperShipit:
    # FIXME a hack to create the log file which **several** of other tests rely on
    def test_presupershipit(self):
        with BotMockManager() as mm:
            os.system('touch %s' % os.path.join(mm.cachedir, 'bot.log'))

    @pytest.mark.skip(reason="automerge is disabled now and this is not really an unit test.")
    def test_supershipit(self, *args, **kwargs):
        with BotMockManager() as mm:
            botmeta = {
                'automerge': True,
                'files': {
                    'lib/ansible/modules/foo/bar.py': {
                        'support': 'community',
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
                '--cachedir=%s' % mm.cachedir,
                '--logfile=%s' % os.path.join(mm.cachedir, 'bot.log'),
                '--no_since',
                '--force',
                '--botmetafile=%s' % bmfile,
                '--ignore_galaxy',
                '--ci=azp',
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

            ts = get_custom_timestamp()

            # this one should get automerged because it only DELETEs from ignore.txt
            mm.issuedb.add_issue(body='\n'.join(body), number=1, itype='pull', login='profleonard', created_at=ts)
            mm.issuedb.add_issue_file('test/sanity/ignore.txt', number=1, deletions=1, created_at=ts)
            mm.issuedb.add_issue_comment('shipit', login='jiffy', number=1)

            # this one should NOT get automerged because it ADDs to ignore.txt
            mm.issuedb.add_issue(body='\n'.join(body), number=2, itype='pull', login='profleonard', created_at=ts)
            mm.issuedb.add_issue_file('test/sanity/ignore.txt', number=2, additions=1, created_at=ts)
            mm.issuedb.add_issue_comment('shipit', login='jiffy', number=2)

            AT = AnsibleTriager(args=bot_args)
            AT.run()

            # /tmp/ansibot.test.isxYlS/ansible/ansible/issues/1/meta.json                
            metafiles = glob.glob('%s/*/meta.json' % os.path.join(mm.cachedir, 'ansible', 'ansible', 'issues'))
            metafiles = sorted(metafiles)
            for mf in metafiles:

                number = int(mf.split('/')[-2])

                with open(mf) as f:
                    meta = json.loads(f.read())

                print(mf)
                print('shipit: %s' % ('shipit' in meta['actions']['newlabel']))
                print('automerge: %s' % ('automerge' in meta['actions']['newlabel']))
                print('merge: %s' % meta['actions']['merge'])
                print('mergeable: %s' % meta['mergeable'])
                print('mergeable_state: %s' % meta['mergeable_state'])
                print('automege: %s' % meta['automerge'])
                print('automerge_status: %s' % meta['automerge_status'])

                if number == 1:
                    assert meta['actions']['merge']
                if number == 2:
                    assert not meta['actions']['merge']
