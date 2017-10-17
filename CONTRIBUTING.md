# Ansibullbot Conributor's Guide

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

1. Download BOTMETA.yml from https://github.com/ansible/ansible to a local directory
2. Edit the file with whatever changes you want to make
3. Run triage_ansible.py with `--botmetafile=<PATHTOFILE>`

If you have a specific issue to test against, use the `--id` parameter to speed up testing.
