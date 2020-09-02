[![Build Status](https://dev.azure.com/ansible/ansibullbot/_apis/build/status/ansible.ansibullbot?branchName=master)](https://dev.azure.com/ansible/ansibullbot/_build/latest?definitionId=12&branchName=master) [![codecov](https://codecov.io/gh/ansible/ansibullbot/branch/master/graph/badge.svg)](https://codecov.io/gh/ansible/ansibullbot)

See the Ansibullbot Project Board for what is being worked on:  [![Project Board](https://img.shields.io/github/issues/ansible/ansibullbot.svg)](https://github.com/ansible/ansibullbot/projects/1)

# User Guide


If you are looking for help, please see the [ISSUE HELP](ISSUE_HELP.md)


# Ansibull Github Issue/Pullrequest Bot

```
$ ./triage.py --help

usage: triage_ansible.py [-h] [--cachedir CACHEDIR_BASE] [--logfile LOGFILE]
                         [--daemonize]
                         [--daemonize_interval DAEMONIZE_INTERVAL] [--debug]
                         [--verbose] [--dry-run] [--force] [--pause]
                         [--force_rate_limit] [--force_description_fixer]
                         [--dump_actions] [--botmetafile BOTMETAFILE]
                         [--repo {ansible/ansible-modules-core,ansible/ansible-modules-extras}]
                         [--skip_no_update] [--skip_no_update_timeout]
                         [--collect_only] [--skip_module_repos]
                         [--module_repos_only] [--sort {asc,desc}]
                         [--skiprepo SKIPREPO] [--only_prs] [--only_issues]
                         [--only_open] [--only_closed] [--safe_force]
                         [--safe_force_script SAFE_FORCE_SCRIPT]
                         [--ignore_state] [--ignore_bot_broken]
                         [--ignore_module_commits] [--pr PR]
                         [--start-at START_AT] [--resume] [--no_since]

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
  --verbose, -v         Verbose output
  --dry-run, -n         Don't make any changes
  --force, -f           Do not ask questions
  --pause, -p           Always pause between prs|issues
  --force_rate_limit    debug: force the rate limit
  --force_description_fixer
                        Always invoke the description fixer
  --dump_actions        serialize the actions to disk [/tmp/actions]
  --botmetafile BOTMETAFILE
                        Use this filepath for botmeta instead of from the repo
  --repo {ansible/ansible-modules-core,ansible/ansible-modules-extras}, -r {ansible/ansible-modules-core,ansible/ansible-modules-extras}
                        Github repo to triage (defaults to all)
  --skip_no_update      skip processing if updated_at hasn't changed
  --skip_no_update_timeout
                        ignore skip logic if last processed >=7 days ago
  --collect_only        stop after caching issues
  --skip_module_repos   ignore the module repos
  --module_repos_only   only process the module repos
  --sort {asc,desc}     Direction to sort issues [desc=9-0 asc=0-9]
  --skiprepo SKIPREPO   Github repo to skip triaging
  --only_prs            Triage pullrequests only
  --only_issues         Triage issues only
  --only_open           Triage open issues|prs only
  --only_closed         Triage closed issues|prs only
  --safe_force          Prompt only on specific actions
  --safe_force_script SAFE_FORCE_SCRIPT
                        Script to check safe force
  --ignore_state        Do not skip processing closed issues
  --ignore_bot_broken   Do not skip processing bot_broken|bot_skip issues
  --ignore_module_commits
                        Do not enumerate module commit logs
  --pr PR, --id PR      Triage only the specified pr|issue (separated by
                        commas)
  --start-at START_AT, --resume_id START_AT
                        Start triage at the specified pr|issue
  --resume              pickup right after where the bot last stopped
  --no_since            Do not use the since keyword to fetch issues
```

