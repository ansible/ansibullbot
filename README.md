[![Run Status](https://api.shippable.com/projects/573f79d02a8192902e20e350/badge?branch=master)](https://app.shippable.com/github/ansible/ansibullbot/dashboard) [![Coverage Badge](https://api.shippable.com/projects/573f79d02a8192902e20e350/coverageBadge?branch=master)](https://app.shippable.com/github/ansible/ansibullbot/dashboard)

See the Ansibullbot Project Board for what is being worked on:  [![Project Board](https://img.shields.io/github/issues/ansible/ansibullbot.svg)](https://github.com/ansible/ansibullbot/projects/1)

# User Guide


If you are looking for help, please see the [ISSUE HELP](ISSUE_HELP.md)


# Ansibull Github Issue/Pullrequest Bot

```
$ ./triage.py --help
usage: triage.py [-h] [--skip_no_update] [--skip_no_update_timeout]
                 [--collect_only] [--skip_module_repos] [--module_repos_only]
                 [--force_rate_limit] [--sort {asc,desc}] [--logfile LOGFILE]
                 [--daemonize] [--daemonize_interval DAEMONIZE_INTERVAL]
                 [--skiprepo SKIPREPO] [--repo REPO] [--only_prs]
                 [--only_issues] [--only_open] [--only_closed] [--verbose]
                 [--dry-run] [--force] [--safe_force] [--debug] [--pause]
                 [--ignore_state] [--issue_component_matching] [--pr PR]
                 [--start-at START_AT] [--no_since]

Triage issue and pullrequest queues for Ansible. (NOTE: only useful if you
have commit access to the repo in question.)

optional arguments:
  -h, --help            show this help message and exit
  --skip_no_update      skip processing if updated_at hasn't changed
  --skip_no_update_timeout
                        ignore skip if last process is X days old
  --collect_only        stop after caching issues
  --skip_module_repos   ignore the module repos
  --module_repos_only   only process the module repos
  --force_rate_limit    debug: force the rate limit
  --sort {asc,desc}     Direction to sort issues [desc=9-0 asc=0-9]
  --logfile LOGFILE     Send logging to this file
  --daemonize           run in a continuos loop
  --daemonize_interval DAEMONIZE_INTERVAL
                        seconds to sleep between loop iterations
  --skiprepo SKIPREPO   Github repo to skip triaging
  --repo REPO, -r REPO  Github repo to triage (defaults to all)
  --only_prs            Triage pullrequests only
  --only_issues         Triage issues only
  --only_open           Triage open issues|prs only
  --only_closed         Triage closed issues|prs only
  --verbose, -v         Verbose output
  --dry-run, -n         Don't make any changes
  --force, -f           Do not ask questions
  --safe_force          Prompt only on specific actions
  --debug, -d           Debug output
  --pause, -p           Always pause between prs|issues
  --ignore_state        Do not skip processing closed issues
  --issue_component_matching
                        Try to enumerate the component labels for issues
  --pr PR, --id PR      Triage only the specified pr|issue (separated by
                        commas)
  --start-at START_AT, --resume_id START_AT
                        Start triage at the specified pr|issue
  --no_since            Do not use the since keyword to fetch issues
```

