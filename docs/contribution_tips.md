# Contribution Tips

## Who is this document for?

Anyone who wants to write a patch for the bot

## Development Setup

### Config files

1. `~/.ansibullbot.cfg` The bot needs this file primarily to get it's gitub api tokens. An example is located in https://github.com/ansible/ansibullbot/blob/master/examples/ansibullbot.cfg
2. `~/.ansibullbot` This directory is where the bot writes all the pickle and json and checkouts it uses.

### Caching and RateLimiting

A repo as large as https://github.com/ansible/ansible has so many tickets that it is literally impossible to simply fetch them all, compute a state and then apply changes. The remedy is to cache everything possible and use [conditional requests](https://developer.github.com/v3/#conditional-requests) wherever possible. Even with caching and conditional requests, you will still find undocument rate limits such as IP throttling and random 500 ISEs. To remedy that, we have a [RateLimited decorator](https://github.com/ansible/ansibullbot/blob/master/ansibullbot/decorators/github.py#L109). The decorator is the result of years of trial and error and constant hacking around.

#### Test Proxy

A [proxy](https://github.com/jctanner/github-test-proxy) was created to assist with testing new ansibot changes across a large set of tickets. Typically, the way it's used is to invoke the bot with environment vars to override the github url used by all the underlying requestors.


```
ANSIBULLBOT_GITHUB_URL=http://localhosthost:5000 \
ANSIBULLBOT_SHIPPABLE_URL=http://localhost:5000 \
./triage_ansible.py <args>`
```
