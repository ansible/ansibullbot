[![Stories in Ready](https://badge.waffle.io/ansibull/ansibullbot.png?label=ready&title=Ready)](https://waffle.io/ansibull/ansibullbot)
# Ansibull PR Bot

```
usage: triage.py [-h] [--gh-user GH_USER] [--gh-pass GH_PASS]
                 [--gh-token GH_TOKEN] [--dry-run] [--only_prs]
                 [--only_issues] [--verbose] [--force] [--debug] [--pause]
                 [--pr PR] [--start-at START_AT]
                 {core,extras}

Triage various PR queues for Ansible. (NOTE: only useful if you have commit
access to the repo in question.)

positional arguments:
  {core,extras}         Repo to be triaged

optional arguments:
  -h, --help            show this help message and exit
  --gh-user GH_USER, -u GH_USER
                        Github username or token of triager
  --gh-pass GH_PASS, -P GH_PASS
                        Github password of triager
  --gh-token GH_TOKEN, -T GH_TOKEN
                        Github token of triager
  --dry-run, -n         Do not apply any changes.
  --only_prs            Triage pullrequests only
  --only_issues         Triage issues only
  --verbose, -v         Verbose output
  --force, -f           Do not ask questions
  --debug, -d           Debug output
  --pause, -p           Always pause between PRs
  --pr PR               Triage only the specified pr
  --start-at START_AT   Start triage at the specified pr
```
