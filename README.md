# Ansibull PR Bot

```
usage: prbot.py [-h] [--verbose] [--debug] [--pr PR]
                ghuser ghpass {core,extras}

Triage various PR queues for Ansible.

positional arguments:
  ghuser         Github username of triager
  ghpass         Github password of triager
  {core,extras}  Repo to be triaged

optional arguments:
  -h, --help     show this help message and exit
  --verbose, -v  Verbose output
  --debug, -d    Debug output
  --pr PR        Triage only the specified pr
```
