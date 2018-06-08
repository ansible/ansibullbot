# Ansibullbot Contributor's Guide

## Getting started

1. Fork this repo
2. Clone your fork
3. Create a feature branch
4. Install the python requirements
5. Create the config file
6. sudo touch /var/log/ansibullbot.log
7. sudo chmod 777 /var/log/ansibullbot.log

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


## Updating Ansible Playbooks and Roles used by Ansibullbot ##

Ansibullbot is deployed and managed using [Ansible](https://www.ansible.com) and [Ansible Tower](https://www.ansible.com/tower). There are several roles used by Ansibullbot, each of which is a [git submodule](https://git-scm.com/book/en/v2/Git-Tools-Submodules).

When making changes anything besides the roles, make the changes to this repository and submit a pull request.

When making changes to roles, first submit pull request to the role repository and ensure it is merged to the pull request repository. Then, submit a pull request to this repository updating the submodule to the include the new commit.

To update the role submodule and include it in your pull request:

1. Run `git submodule update --remote [path to role]` to pull in the latest role commits.
1. `git add [path to role]`
1. Commit and push the branch to your fork
2. Submit the pull request
