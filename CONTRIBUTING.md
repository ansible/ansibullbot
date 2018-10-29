# Ansibullbot Contributor's Guide

## Python compatibility

Ansibullbot is compatible with both Python 2.7 and Python 3.7.

Usage of unicode strings is required.

## Getting started

1. Fork this repo
2. Clone your fork
3. Create a feature branch
4. Optionally: create a [Python virtual environment](https://realpython.com/python-virtual-environments-a-primer/)
4. Install the python requirements: `pip install -r requirements.txt`
5. Create the log file:
    * either add `--log path/to/file.log` to the `triage_ansible.py` below
    * or use `sudo touch /var/log/ansibullbot.log && sudo chmod 777 /var/log/ansibullbot.log`
6. Create the config file, copy [`examples/ansibullbot.cfg`](https://github.com/ansible/ansibullbot/blob/master/examples/ansibullbot.cfg) to one of these paths:
    * `~/.ansibullbot.cfg`
    * `$CWD/ansibullot.cfg`
    * `/etc/ansibullot/ansibullbot.cfg`
    * define `ANSIBULLBOT_CONFIG` environment variable where the configuration file is located
7. fill in the credentials

## Testing your changes

Run with `verbose`, `debug` and `dry-run` ...

```bash
./triage_ansible.py --debug --verbose --dry-run
```

## Testing changes to BOTMETA.yml

1. Download [`BOTMETA.yml`](https://github.com/ansible/ansible/blob/devel/.github/BOTMETA.yml) to a local directory
2. Edit the file with whatever changes you want to make.
3. Run `triage_ansible.py` with `--botmetafile=<PATHTOFILE>`.

If you have a specific issue to test against, use the `--id` parameter to speed up testing.

## Testing changes related to a single label

The `--id` parameter can take a path to a script. The `scripts` directory is full of scripts that will return json'ified lists of issue numbers. One example is the `scripts/list_open_issues_with_needs_info.sh` script which scrapes the github UI for any issues with the needs_info label. Here's how you might use that to test your changes to ansibullbot against all issues with needs_info ...

```
./triage_ansible.py --debug --verbose --dry-run --id=scripts/list_open_issues_with_needs_info.sh
```


## Updating Ansible Playbooks and Roles used by Ansibullbot ##

Ansibullbot is deployed and managed using [Ansible](https://www.ansible.com) and [Ansible Tower](https://www.ansible.com/tower). There are several roles used by Ansibullbot, each of which is a [git submodule](https://git-scm.com/book/en/v2/Git-Tools-Submodules).

When making changes anything besides the roles, make the changes to this repository and submit a pull request.

When making changes to roles, first submit pull request to the role repository and ensure it is merged to the pull request repository. Then, submit a pull request to this repository updating the submodule to the include the new commit.

To update the role submodule and include it in your pull request:

1. Run `git submodule update --remote [path to role]` to pull in the latest role commits.
1. `git add [path to role]`
1. Commit and push the branch to your fork
2. Submit the pull request
