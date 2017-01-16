[![Stories in Ready](https://badge.waffle.io/ansibull/ansibullbot.png?label=ready&title=Ready)](https://waffle.io/ansibull/ansibullbot)
# Ansibull Github Issue/Pullrequest Bot

```
$ ./triage.py --help
usage: triage.py [-h] [--skip-no-update] [--collect_only]
                 [--skip_module_repos] [--module_repos_only]
                 [--force_rate_limit] [--sort {asc,desc}] [--logfile LOGFILE]
                 [--daemonize] [--daemonize_interval DAEMONIZE_INTERVAL]
                 [--skiprepo SKIPREPO] [--repo REPO] [--gh-user GH_USER]
                 [--gh-pass GH_PASS] [--gh-token GH_TOKEN] [--dryrun]
                 [--only_prs] [--only_issues] [--only_open] [--only_closed]
                 [--verbose] [--dry-run] [--force] [--safe_force] [--debug]
                 [--pause] [--pr PR] [--start-at START_AT] [--no_since]

Triage issue and pullrequest queues for Ansible. (NOTE: only useful if you
have commit access to the repo in question.)

optional arguments:
  -h, --help            show this help message and exit
  --skip-no-update      skip processing if updated_at hasn't changed
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
  --gh-user GH_USER, -u GH_USER
                        Github username or token of triager
  --gh-pass GH_PASS, -P GH_PASS
                        Github password of triager
  --gh-token GH_TOKEN, -T GH_TOKEN
                        Github token of triager
  --dryrun, -n          Do not apply any changes.
  --only_prs            Triage pullrequests only
  --only_issues         Triage issues only
  --only_open           Triage open issues|prs only
  --only_closed         Triage closed issues|prs only
  --verbose, -v         Verbose output
  --dry-run             Ignore all actions
  --force, -f           Do not ask questions
  --safe_force          Prompt only on specific actions
  --debug, -d           Debug output
  --pause, -p           Always pause between prs|issues
  --pr PR, --id PR      Triage only the specified pr|issue
  --start-at START_AT, --resume_id START_AT
                        Start triage at the specified pr|issue
  --no_since            Do not use the since keyword to fetch issues
```

If you are looking for help, please see the [ISSUE HELP](ISSUE_HELP.md)
