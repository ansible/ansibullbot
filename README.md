[![Build Status](https://dev.azure.com/ansible/ansibullbot/_apis/build/status/ansible.ansibullbot?branchName=devel)](https://dev.azure.com/ansible/ansibullbot/_build/latest?definitionId=12&branchName=devel) [![codecov](https://codecov.io/gh/ansible/ansibullbot/branch/devel/graph/badge.svg)](https://codecov.io/gh/ansible/ansibullbot)

See the Ansibullbot Project Board for what is being worked on:  [![Project Board](https://img.shields.io/github/issues/ansible/ansibullbot.svg)](https://github.com/ansible/ansibullbot/projects/1)

# User Guide


If you are looking for help, please see the [ISSUE HELP](ISSUE_HELP.md)


# Ansibull Github Issue/Pullrequest Bot

```
$ ./triage_ansible.py --help
usage: triage_ansible.py [-h] [--cachedir CACHEDIR_BASE] [--logfile LOGFILE]
                         [--daemonize]
                         [--daemonize_interval DAEMONIZE_INTERVAL] [--debug]
                         [--dry-run] [--force] [--pause] [--dump_actions]
                         [--botmetafile BOTMETAFILE]
                         [--repo {ansible/ansible}] [--skip_no_update]
                         [--collect_only] [--sort {asc,desc}]
                         [--skiprepo SKIPREPO] [--only_prs] [--only_issues]
                         [--only_closed]
                         [--ignore_state] [--ignore_bot_broken]
                         [--ignore_module_commits] [--pr PR]
                         [--start-at START_AT] [--resume] [--last LAST]
                         [--commit ANSIBLE_COMMIT] [--ignore_galaxy]
                         [--ci {azp}]

Triage issue and pullrequest queues for Ansible. (NOTE: only useful if you
have commit access to the repo in question.)

optional arguments:
  -h, --help            show this help message and exit
  --cachedir CACHEDIR_BASE
  --logfile LOGFILE     Send logging to this file
  --daemonize           run in a continuos loop
  --daemonize_interval DAEMONIZE_INTERVAL
                        seconds to sleep between loop iterations
  --debug, -d           Debug output
  --dry-run, -n         Don't make any changes
  --force, -f           Do not ask questions
  --pause, -p           Always pause between prs|issues
  --dump_actions        serialize the actions to disk [/tmp/actions]
  --botmetafile BOTMETAFILE
                        Use this filepath for botmeta instead of from the
                        repo
  --repo {ansible/ansible}, -r {ansible/ansible}
                        Github repo to triage (defaults to all)
  --skip_no_update      skip processing if updated_at hasn't changed
  --collect_only        stop after caching issues
  --sort {asc,desc}     Direction to sort issues [desc=9-0 asc=0-9]
  --skiprepo SKIPREPO   Github repo to skip triaging
  --only_prs            Triage pullrequests only
  --only_issues         Triage issues only
  --only_closed         Triage closed issues|prs only
  --ignore_state        Do not skip processing closed issues
  --ignore_bot_broken   Do not skip processing bot_broken|bot_skip issues
  --ignore_module_commits
                        Do not enumerate module commit logs
  --pr PR, --id PR      Triage only the specified pr|issue (separated by
                        commas)
  --start-at START_AT   Start triage at the specified pr|issue
  --resume              pickup right after where the bot last stopped
  --last LAST           triage the last N issues or PRs
  --commit ANSIBLE_COMMIT
                        Use a specific commit for the indexers
  --ignore_galaxy       do not index or search for components in galaxy
  --ci {azp}            Specify a CI provider that repo uses
```
