#!/usr/bin/env python
# Post message to Slack

import argparse
import ConfigParser
import os
import requests

from subprocess import Popen, PIPE


def get_config(args):

    ansibullbot_user = 'ansibot'
    if args.user:
        ansibullbot_user = args.user

    config_file_path = os.path.join(os.path.expanduser('~' + ansibullbot_user), '.ansibullbot.cfg')
    if args.config_file:
        config_file_path = args.config_file

    ini_file = ConfigParser.ConfigParser()
    ini_file.read(config_file_path)
    return ini_file


def parse_args():
    description = 'Post a status message to #monitoring channel in Ansible Slack.\n'
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument('--message', '-m', type=str, help='Message to post')
    parser.add_argument('--config-file', '-f', type=str, help='Path to config file')
    parser.add_argument('--user', '-u', type=str, help='User account that runs Ansibullbot')
    parser.add_argument('--email-trace', '-e', dest='email_trace', default=False, action='store_true', help='Send an email containing the latest stack trace.')

    args = parser.parse_args()
    return args


def send_email(email):

    # Get the last few lines of the file
    with open('/var/log/ansibullbot.log', 'r') as log_file:
        log_file.seek(0, 2)
        log_length = log_file.tell()
        log_file.seek(max(log_length - 4096, 0), 0)
        lines = log_file.readlines()

    # Return lines before and after the error message
    block = []
    for i in range(len(lines)):
        if 'ERROR Uncaught exception' in lines[i]:
            block = lines[max(0, i - 20):min(len(lines), i + 20)]

    # Turn the list into a string
    message = ''.join(block)

    # Send email only if there is a recent stack trace
    if len(message) > 0:
        print(email)
        p = Popen(['mail', '-s', 'Ansibullbot Stack Trace', '-r', 'Ansibullbot<noreply@ansibullbot.eng.ansible.com>', email],
                  stdin=PIPE,
                  stdout=PIPE,
                  stderr=PIPE,
                  )
        p.communicate(input=message)


def main():
    args = parse_args()
    ini_file = get_config(args)
    url = ini_file.get('defaults', 'slack_url')
    email = ini_file.get('defaults', 'email')

    message = 'Ansibullbot restarted'
    if args.message:
        message = args.message

    requests.post(url, json={'text': message})

    if args.email_trace:
        send_email(email)


if __name__ == '__main__':
    main()
