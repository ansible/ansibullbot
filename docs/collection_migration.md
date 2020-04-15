# COLLECTIONS

## What is this all about?

Here are some links to read through and familiarize yourself with ...

* https://www.ansible.com/blog/getting-started-with-ansible-collections
* https://docs.ansible.com/ansible/devel/user_guide/collections_using.html
* https://docs.ansible.com/ansible/devel/dev_guide/developing_collections.html
* https://github.com/ansible-collections/overview/blob/master/README.rst

## Why is ansibot directing me here?

A. You made a change or filed an issue for a plugin|module file that no longer exists in github.com:ansible/ansible.

or

B. You created a new module.

## What if ansibot made a mistake in deciding my issue or PR was for a file in a collection?

Comment "!needs_collection_redirect" in the issue and the bot will override the redirect.

## What should I do now?

1. Determine which collection+repo the file should live in now.
2. Migrate your PR or issue to the new repo

## How do I migrate my issue to another repo?

Github only allows issue migration between repos in the same organization. Most collections are in the ansible-collections org so we are unable
to migrate them automatically from ansible/ansible. The simplest approach is to just open a new issue in the new repo.

## How do I migrate my PR to another repo?

A tool exists to assist with migrating ansible/ansible PRs, but is waiting on the community team to deploy. In the meantime, you
can either recreate your PR in the new repo, or try to setup the tool on your own.

https://github.com/ansible/prmove

## Why did the bot close my issue or PR?

For the reasons stated above, we will not be auto-migrating all the issues and PRs and need to take action to make sure they are being
filed in the appropriate repositories.

Pull requests do not need to be open when migrating, and there is no other reason to keep them open in the ansible/ansible repo.

## What if none of this makes sense to me?

Please reach out via the typical communication channels: https://docs.ansible.com/ansible/latest/community/communication.html
