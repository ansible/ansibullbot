# Ansibullbot Help

Making progress in resolving issues for modules depends upon your interaction! Please be sure to respond to requests or additional information as needed.

If at any time you think this bot is misbehaving (not for test failures), please leave a comment containing the keyword [`bot_broken`](#cmd-bot_broken) and an Ansible staff member will intervene.

#### Table of contents

* [Overview](#overview)
* [For issue submitters](#for-issue-submitters)
* [For pull request submitters](#for-pull-request-submitters)
  * [When will your pull request be merged?](#when-will-your-pull-request-be-merged)
    * [New Modules](#new-modules)
    * [Existing Modules](#existing-modules)
      * [core](#core)
      * [certified](#certified)
      * [community](#community)
      * [network](#network)
    * [Non-module changes](#non-module-changes)
* [For community maintainers](#for-community-maintainers)
* [For anyone else](#for-anyone-else)
* [Commands](#commands)
* [Labels](#labels)
  * [When to use label commands](#when-to-use-label-commands)
  * [How to use label commands](#how-to-use-label-commands)

## Overview

The Ansibull Triage Bot serves many functions:

* Responds quickly to issue and pull request submitters to thank them;
* Identifies the maintainers responsible for reviewing pull requests for any files affected;
* Tracks the current status of pull requests;
* Pings responsible parties to remind them of any actions that they may be responsible for;
* Provides maintainers with the ability to move pull requests through our [workflow](#when-will-your-pull-request-be-merged);
* Identifies issues and pull requests abandoned by their authors so that we can close them;
* Identifies modules abandoned by their maintainers so that we can find new maintainers;
* Automatically labels issues and pull requests based on keywords or affected files.

## For issue submitters
Please note that if you have a question about how to use this feature or module with Ansible, that's probably something you should ask on the [ansible-project](https://groups.google.com/forum/#!forum/ansible-project) mailing list, rather than submitting a bug report. For more details, please see [I’ve Got A Question](http://docs.ansible.com/ansible/community.html#i-ve-got-a-question).

If the feature/module maintainer or ansibullbot needs further information, please respond to the request, so that you can help the devs to help you!

The bot requires a minimal subset of information from the issue template:
* issue type
* component name
* ansible version
* summary

If any of those items are missing or empty, ansibullbot will keep the issue in a `needs_info` state until the data is provided in the issue's description. The bot is expecting an issue description styled after the default issue template, so please use that whenever possible.

Expect the bot to do a few things:

1. Add common [labels](#labels) such as `needs_triage`, `bug_report`, `feature_idea`, etc.

   These labels are determined by templated data in the description. Please fill out the templates as accurately as possible so that the appropriate labels are used.

2. Notify and assign the maintainer(s) of the relevant file(s) or module(s).

   Notifications will happen via a comment with the `@NAME` syntax. If you know of other interested parties, feel free to ping them in a comment or in your issue description.

If you are not sure who the issue is waiting on, please use the [`bot_status`](#cmd-bot_status) command.

## For pull request submitters
Expect the bot to do a few things:

1. All of the items described in the for [issue submitters](#for-issue-submitters) section.

2. Add [labels](#labels) indicating the status of the pull request.

Please prefix your pull request's title with `WIP` if you are not yet finished making changes. This will tell the bot to ignore the [`needs_rebase`](#label-needs_rebase) and [`shipit`](#label-shipit) workflows until you remove it from the title.

If you are finished committing to your pull request or have made changes due to a request, please use the [`ready_for_review`](#cmd-ready_for_review) command.

If you are not sure who the pull request is waiting on, please use the [`bot_status`](#cmd-bot_status) command.

### When will your pull request be merged?

:information_source: `Approve` pull request status is ignored, [`shipit`](#cmd-shipit) command is used by maintainer to approve a pull request. The bot automatically adds a [`shipit`](#label-shipit) label to the pull request when the required number of [`shipit`](#cmd-shipit) commands has been reached.

The bot will label a pull request with [`shipit`](#label-shipit) when at least **two** [`shipit`] commands are issued, the following rules describe how [`shipit`](#cmd-shipit) commands are count:

* [`shipit`](#cmd-shipit) issued by a module maintainer or a maintainer of a module in the same namespace or a core team member are always taken in account
* when the submitter is a module maintainer or a maintainer of a module in the same namespace or a core team member, their [`shipit`](#cmd-shipit) is automatically counted
* [`shipit`](#cmd-shipit) issued by anyone else is taken in account when both conditions are met:
  * at least one module maintainer or a maintainer of a module in the same namespace or a core team member has approved the pull request with a [`shipit`](#cmd-shipit) command
  * at least three people which aren't maintainer nor core team member have approved the pull request using the [`shipit`](#cmd-shipit)

#### New Modules

Once the pull request labeled with [`shipit`](#label-shipit), the module will be merged once a member of the Ansible organization has reviewed it and decided to include it.

:information_source: If you are a maintainer of a module in the same namespace, only one `shipit` is required.

#### Existing Modules

Module's have metadata with a [`supported_by`](http://docs.ansible.com/ansible/devel/dev_guide/developing_modules_documenting.html#ansible-metadata-block) field per the [metadata proposal](https://github.com/ansible/proposals/issues/30).

:information_source: If you have **changes to other files in the pull request**, the `supported_by` property is ignored because the Ansible core team **must** approve those changes. When other changes are line deletions in `ansible/test/*/*.txt` files, the `supported_by` property isn't ignored.

:information_source: if the pull request has more than one committer, then number of commits must be equal to number of authors and lower than 11.

The possible values of `supported_by` are:

##### core

Members of the Ansible Core Team typically do all the maintenance on this module, so only they can approve changes. Expect reviews to take longer than most other modules because of the volume the core team has on a daily basis.

##### certified

These modules are developed and maintained by the community, but the Ansible core team needs to approve changes. Once the pull request is labeled with [`shipit`](#label-shipit), the core team will be alerted to review.

##### community

These modules are also developed, maintained and supported by the community. If you are a module maintainer, a maintainer of a module in the same namespace, or a core team member use the [`shipit`](#cmd-shipit) command to approve the pull request. The bot will wait for the pull request being labeled with [`shipit`](#label-shipit), then automerge.

:information_source: If you are maintainer of the module or maintainer of a module in the same namespace, only one [`shipit`](#cmd-shipit) is required.

##### network

Members of the Ansible Network Team typically do all the maintenance on this module, so only they can approve changes.

#### Non-module changes

The ansible core team approves these pull requests and it may take some time for them to get to your request.

## For community maintainers

:information_source: `Approve` pull request status is ignored, [`shipit`](#cmd-shipit) command must be used in order to approve a pull request.

Thanks in advance for taking a look at issues and pull requests and for your ongoing maintenance. If you are unable to troubleshoot or review this issue/pull request with the information provided, please ping the submitter of the issue in a comment to let them know.

## For anyone else
Reactions help us determine how many people are interested in a pull request or have run across a similar bug. Please leave a +1 [reaction](https://github.com/blog/2119-add-reactions-to-pull-requests-issues-and-comments) (:+1:) if that applies to you. Any additional details you can provide, such as your usecase, environment, steps to reproduce, or workarounds you have found, can help out with resolving issues or getting pull requests merged.

## Commands

To streamline the maintenance process, we've added some commands to Ansibullbot that you can use to help direct the work flow. Using the automation is simply a matter of adding one of the following commands in your comments:

Command | Scope | Allowed | Description
--- | --- | --- | ---
**<a name="cmd-bot_broken">bot_broken</a>** | issues pull requests | anyone | Use this command if you think the bot is misbehaving (not for test failures), and an Ansible staff member will investigate.
**<a name="cmd-bot_skip">bot_skip</a>** | issues pull requests | staff | Ansible staff members use this to have the bot skip triaging an issue.
**<a name="cmd-bot_status">bot_status</a>** | pull requests | submitters maintainers | Use this command if you would like the bot to comment with some helpful metadata about the issue.
**<a name="cmd-needs_info">needs_info</a>** | issues pull requests | maintainers past committers | Use this command if you need more information from the submitter. We will notify the submitter and apply the [`needs_info`](#label-needs_info) label.
**<a name="cmd-!needs_info">!needs_info</a>** | issues pull requests | maintainers past committers | If you do not need any more information and just need time to work the issue, leave a comment that contains the command `!needs_info` and the [`needs_info`](#label-needs_info) label will be replaced with [`waiting_on_maintainer`](#label-waiting_on_maintainer).
**<a name="cmd-needs_revision">needs_revision</a>** | pull requests | maintainers | Use this command if you would like the submitter to make changes.
**<a name="cmd-!needs_revision">!needs_revision</a>** | pull requests | maintainers | If you want to clear the [`needs_revision`](#label-needs_revision) label, use this command.
**<a name="cmd-needs_rebase">needs_rebase</a>** | pull requests | maintainers | Use this command if the submitters branch is out of date. The bot should automatically apply this label, so you may never need to use it.
**<a name="cmd-!needs_rebase">!needs_rebase</a>** | pull requests | maintainers | Clear the [`needs_rebase`](#label-needs_rebase) label.
**<a name="cmd-notabug">notabug</a>** | issues | maintainers | If you believe this is not a bug, please leave a comment stating `notabug`, along with any additional information as to why it is not, and we will close this issue.
**<a name="cmd-bug_resolved">bug_resolved</a>** | issues | maintainers | If you believe this issue is resolved, please leave a comment stating `bug_resolved`, and we will close this issue.
**<a name="cmd-resolved_by_pr">resolved_by_pr</a>** | issues | maintainers | If you believe this issue has been resolved by a pull request, please leave a comment stating `resolved_by_pr` followed by the pull request number.
**<a name="cmd-wontfix">wontfix</a>** | issues | maintainers | If this is a bug that you can't or won't fix, please leave a comment including the word `wontfix`, along with an explanation for why it won't be fixed.
**<a name="cmd-needs_contributor">needs_contributor</a>** | issues | maintainers | If this bug or feature request is something that you want implemented but do not have the time or expertise to do, comment with `needs_contributor`, and the issue will be put into a [`waiting_on_contributor`](#label-waiting_on_contributor) state.
**<a name="cmd-duplicate_of">duplicate_of</a>** | issues | maintainers | If this bug or feature request is a duplicate of another issue, comment with `duplicate_of` followed by the issue number that it duplicates, and the issue will be closed.
**<a name="cmd-close_me">close_me</a>** | issues | maintainers | If the issue can be closed for a reason you will specify in the comment, use this command.
**<a name="cmd-ready_for_review">ready_for_review</a>** | pull requests | submitters | If you are finished making commits to your pull request or have made changes due to a request, please use this command to trigger a review from the maintainer(s).
**<a name="cmd-shipit">shipit</a>** | pull requests | maintainers | If you approve the code in this pull request, use this command to have it merged. Note that Github `Approve` pull request status is ignored. Nonetheless `shipit` in review summary of commented or approved review is taken in account. In place of `shipit`, `+1` and `LGTM` can be used too. Note that these commands must not be surrounded by any character, spaces excepted.
**<a name="cmd-add-label">+label</a>** | issues pull requests | staff maintainers | Add a whitelisted label. See [When to use label commands](#when-to-use-label-commands).
**<a name="cmd-remove-label">-label</a>** | issues pull requests | staff maintainers | Remove a whitelisted label. See [When to use label commands](#when-to-use-label-commands).
**<a name="cmd-rebuild_merge">rebuild_merge</a>** | pull requests | staff | Allow core team members to trigger CI, then the pull request is automatically merged if CI results are successful.
**<a name="cmd-rebuild">/rebuild</a>** | pull requests | anyone | Allows anyone to re-trigger CI.
**<a name="cmd-rebuild_failed">/rebuild_failed</a>** | pull requests | anyone | Allows anyone to re-trigger CI only on failed jobs [this is usually much faster than /rebuild].
**<a name="cmd-component">!component</a>** | issues | anyone | Set, append or remove a file from the matched components. To set, use `!component =lib/ansible/foo/bar`. To add, use `!component +lib/ansible/foo/bar`. To remove, use `!component -lib/ansible/foo/bar`.
**<a name="cmd-waffling">!waffling</a>** | all | maintainers | Disable waffling detection on a label. To use `!waffling <labelname>` on a separate line in a comment.

## Labels

The bot adds many labels on issues and pull requests.

Label | Scope | Prevent automerge | Description
--- | --- | --- | ---
**<a name="label-automerge">automerge</a>** | pull requests | no | Identify pull requests automatically merged by the bot.
**<a name="label-backport">backport</a>** | pull requests | yes | Added to pull requests which don't target `devel` branch.
**<a name="label-bot_broken">bot_broken</a>** | pull requests | yes | Allow to identify pull requests for which [`bot_broken`](#cmd-bot_broken) had been used.
**<a name="label-bug">bug</a>** | issues pull requests | no | Added to issues or pull requests reporting/fixing bugs.
**<a name="label-c:_name_">c:_name_</a>** | issues pull requests | no | Categorize issues or pull requests by their relevant source code files.
**<a name="label-ci_verified">ci_verified</a>** | pull requests | yes | Identify pull requests for which CI failed. A pull request must successfully pass CI in order to be merged.
**<a name="label-committer_review">committer_review</a>** | pull requests | no | In order to be merged, these pull requests must follow the [certified](#certified) review workflow.
**<a name="label-community_review">community_review</a>** | pull requests | no | In order to be merged, these pull requests must follow the [community](#community) review workflow.
**<a name="label-core_review">core_review</a>** | pull requests | no | In order to be merged, these pull requests must follow the [core](#core) review workflow.
**<a name="label-docs">docs</a>** | issues pull requests | no | Identify issues or pull requests related to documentation.
**<a name="label-docsite_pr">docsite_pr</a>** | pull requests | no | Identify pull requests created through documentation's "Edit on GitHub" link
**<a name="label-easyfix">easyfix</a>** | issue or pull requests | no | Identify easy entrance point for people who are looking to start contributing.
**<a name="label-feature">feature</a>** | issues pull requests | no | Added to issues or pull requests requesting/adding new features.
**<a name="label-filament">filament</a>** | pull requests | no | Identify pull requests related to [Ansible Lightbulb](https://github.com/ansible/lightbulb) project.
**<a name="label-merge_commit">merge_commit</a>** | pull requests | no | Added to pull requests containing at least one merge commit. Pull requests must not contain merge commit.
**<a name="label-module">module</a>** | pull requests | no | Identify pull requests updating existing modules.
**<a name="label-needs_ci">needs_ci</a>** | pull requests | no | Identify pull requests for which CI status is missing. When a pull request is closed and reopened or when new commits are updated, the CI is triggered again.
**<a name="label-needs_info">needs_info</a>** | issues | yes | Identify issues for which reviewer requested further information.
**<a name="label-needs_maintainer">needs_maintainer</a>** | pull requests | no | Ansibullbot is unable to identify authors or maintainers of the related module. Check `author` field format in [`DOCUMENTATION block`](http://docs.ansible.com/ansible/devel/dev_guide/developing_modules_documenting.html#documentation-block).
**<a name="label-needs_rebase">needs_rebase</a>** | pull requests | yes | Pull requests which are out of sync with ansible/ansible's `devel` branch. Please review the [rebase guide](http://docs.ansible.com/ansible/devel/dev_guide/developing_rebasing.html) for further information.
**<a name="label-needs_revision">needs_revision</a>** | pull requests | yes | Used for pull request which fail continuous integration tests or if a maintainer has requested a review/revision of the code. This label can be cleared by fixing any failed tests or by commenting [`ready_for_review`](#cmd-ready_for_review).
**<a name="label-needs_template">needs_template</a>** | issues pull requests | no | Label added when description is incomplete. See [issue template](https://raw.githubusercontent.com/ansible/ansible/devel/.github/ISSUE_TEMPLATE.md), pull request [template](https://raw.githubusercontent.com/ansible/ansible/devel/.github/PULL_REQUEST_TEMPLATE.md).
**<a name="label-needs_triage">needs_triage</a>** | issues pull requests | no | This label will be added if your issue is being labeled for the first time. We (ansible staff and maintainers) use this label to find issues that need a human first touch. We'll remove it once we've given the issue a quick look for any labeling problems or missing data.
**<a name="label-needs_verified">needs_verified</a>** | issues | no | This label implies a maintainer needs to check if the issue can be reproduced in the latest version.
**<a name="label-new_module">new_module</a>** | pull requests | yes | Identify pull requests adding new module.
**<a name="label-owner_pr">owner_pr</a>** | pull requests | no | Identify pull requests made by module maintainers.
**<a name="label-shipit">shipit</a>** | pull requests | no | Identify pull requests for which the required number of `shipit` has been reached. For [community](#community) reviewed pull requests, if `automerge` workflow applies, then pull request should be automatically merged. For all other cases, merge should be performed by a core team members. If your pull request gets no comment and becomes tagged with [`stale_review`](#label-stale_review), you can add it to the [IRC core team meeting agenda](https://github.com/ansible/community/blob/master/meetings/core-team.yaml) to receive more comments.
**<a name="label-stale_ci">stale_ci</a>** | pull requests | yes | Added when the last CI result is older than one week. When a pull request is closed and reopened, the CI is triggered again. In some case, the bot will automatically trigger the CI when a pull request is labeled with both [`shipit`](#label-shipit) and `stale_ci`.
**<a name="label-stale_review">stale_review</a>** | pull requests | no | Added when submitter made some updates after a reviewer requested some changes, if the submitter updates are older than seven days and the reviewer didn't update their review.
**<a name="label-test">test</a>** | pull requests | no | Identify pull requests related to tests.
**<a name="label-waiting_on_contributor">waiting_on_contributor</a>** | issues pull requests | no | Identify issues for which help is needed
**<a name="label-WIP">WIP</a>** | pull requests | yes | Identify pull requests which are not ready (from the submitter point of view) to be merged.

Some labels are used to categorize issues and pull requests:

* Pull requests related to [test](https://github.com/ansible/community/wiki):
  * `test`

* Namespace labels:
  * `aci`
  * `avi`
  * `aws`
  * `azure`
  * `cloud`
  * `cloudstack`
  * `digital_ocean`
  * `docker`
  * `f5`
  * `gce`
  * `infoblox`
  * `jboss`
  * `meraki`
  * `netapp`
  * `networking`
  * `nxos`
  * `openstack`
  * `ovirt`
  * `ucs`
  * `vmware`
  * `windows`

* Module labels:
  * `m:unarchive`
  * `m:xml`

### When to use label commands

The `+label` and `-label` commands are restricted to a subset of available labels and are not meant to replace the other bot commands:

* `affects_X.Y` -- indicates that the issue is relevant to a particular ansible *major.minor* version.
* `c:...` -- these labels categorize issues or pull requests by their relevant source code files.
* `easyfix` -- indicates that the issue an easy entrance point for people who are looking to start contributing.
* `m:...` -- these labels categorize issues or pull requests by their module name.
* `module` -- classifies the issue as a module related issue.
* `needs_triage` -- a human being still needs to validate the issue is properly labeled and has all the information required.
* `test` and namespace labels

### How to use label commands

To use the commands, please type the command and label on one line each in a comment.
Example:
```
-label needs_triage
+label cloud
+label gce
```
