#!/usr/bin/env python
# Post message to Slack

import argparse
import os
import requests

try:
    import configparser
except ImportError:
    import ConfigParser as configparser


def get_config(args):

    ansibullbot_user = 'ansibot'
    if args.user:
        ansibullbot_user = args.user

    config_file_path = os.path.join(os.path.expanduser('~' + ansibullbot_user), '.ansibullbot.cfg')
    if args.config_file:
        config_file_path = args.config_file

    ini_file = configparser.ConfigParser()
    ini_file.read(config_file_path)
    return ini_file


def parse_args():
    description = 'Post a status message to #monitoring channel in Ansible Slack.\n'
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument('--message', '-m', type=str, help='Message to post')
    parser.add_argument('--config-file', '-f', type=str, help='Path to config file')
    parser.add_argument('--user', '-u', type=str, help='User account that runs Ansibullbot')

    args = parser.parse_args()
    return args


def main():
    args = parse_args()
    ini_file = get_config(args)
    url = ini_file.get('defaults', 'slack_url')

    message = 'Ansibullbot restarted'
    if args.message:
        message = args.message

    requests.post(url, json={'text': message})


if __name__ == '__main__':
    main()
