
# Ansibot Help

Making progress in resolving issues for modules depends upon your interaction! Please be sure to respond to requests or additional information as needed.

If at anytime you think this bot is misbehaving, please leave a comment containing the keyword `bot_broken` and an Ansible staff member will intervene.

## For issue submitters
Please note that if you have a question about how to use this feature or module with Ansible, that's probably something you should ask on the ansible-project mailing list, rather than submitting a bug report. For more details, please see http://docs.ansible.com/ansible/community.html#i-ve-got-a-question .

If the feature/module maintainer or ansibot needs further information, please respond to the request, so that you can help us to help you!

The bot requires a minimal subset of information from the issue template 
* issue type
* component name
* ansible version
* summary

If any of those items are missing or empty, ansibot will keep the issue in a "needs info" state until the data is provided in the issue's description. The bot is expecting an issue description styled after the default issue template, so please use that whenever possible.

Expect the bot to do a few things:

1. Add common labels such as needs_triage, bug_report, feature_idea, etc.

  These labels are determined by templated data in the description. Please fill out the templates as accurately as possible so that the appropriate labels are used.

  **needs_triage** will be added if your issue is being labeled for the first time. We (ansible staff and maintainers) use this label to find issues that need a human first touch. We'll remove it once we've given the issue a quick look for any labeling problems or missing data.

2. Notify and assign the maintainer(s) of the relevant file(s) or module(s).

  Notifications will happen via a comment with the '@<NAME>' syntax. If you know of other interested parties, feel free to ping them in a comment or in your issue description.

To streamline the maintenance process, we've added some commands to the ansibot that you can use to help direct the work flow. Using the automation is simply a matter of adding one of the following commands in your comments:

* **bot_broken** - Use this command if you think the ansibot is misbehaving, and an Ansible staff member will investigate.

## For pullrequest submitters
Expect the bot to do a few things:

1. All of the items described in the "for issue submitters" section.

2. Add labels indicating the status of the pullrequest.

  * **needs_rebase** - Your pullrequest is out of sync with ansible/ansible's devel branch. Please review http://docs.ansible.com/ansible/dev_guide/developing_rebasing.html for further information.
  * **needs_revision** - Either your pullrequest fails continuous integration tests or a maintainer has requested a review/revision of the code. This label can be cleared by fixing any failed tests or by commenting "ready_for_review"

Please prefix your pullrequest's title with **WIP** if you are not yet finished making changes. This will tell the bot to ignore the needs_rebase and shipit workflows until you remove it from the title.

If you are finished committing to your pullrequest or have made changes due to a request, please use the **ready_for_review** command.

To streamline the maintenance process, we've added some commands to the ansibot that you can use to help direct the work flow. Using the automation is simply a matter of adding one of the following commands in your comments:

* **bot_broken** - Use this command if you think the ansibot is misbehaving, and an Ansible staff member will investigate.
* **ready_for_review** - If you are finished making commits to your pullrequest or have made changes due to a request, please use this command to trigger a review from the maintainer(s).

### When will your PR be merged?

#### New Modules

New modules require two **shipits** from anyone in the community before the bot will label it "shipit". At that point, the module will be merged once a member of the Ansible organization has reviewed it and decided to include it.

#### Existing Modules

Module's have metadata with a "supported_by" field per the (metadata proposal)[https://github.com/ansible/proposals/issues/30]. The possible values of supported_by are:
* unmaintained: no community members are responsible for this module, so changes will have to be reviewed by the core team until someone volunteers to maintain it. See "core".
* core: Members of the Ansible organization typically do all the maintainence on this module, so only they can approve changes. Expect review to take longer than most other modules because of the volume the core team has on a daily basis.
* commiter: These modules are developed and maintained by the community, but the Ansible core team needs to approve changes. Once two community members give "shipit", the core team will be alerted to review.
* community: These modules are also developed, maintained and supported by the community. If you are a maintainer for the module, use the "shipit" command to have the PR automerged, otherwise the bot will wait for shipits from 2 maintainers and then automerge.

NOTE: If you have changes to other files in the PR, the supported_by field is ignored because the Ansible core team *must* approve those changes.

#### Non-module changes

The ansible core team approves these pullrequests and it may take some time for them to get to your request. 

## For community maintainers
Thanks in advance for taking a look at issues+pullrequests and for your ongoing maintainince. If you are unable to troubleshoot or review this issue/pullrequest with the information provided, please ping the submitter of the issue in a comment to let them know. 

To streamline the maintenance process, we've added some commands to the ansibot that you can use to help direct the work flow. Using the automation is simply a matter of adding one of the following commands in your comments:

* **shipit** - If you approve of the code in this pullrequest, use this command to have it  merged.
* **bot_broken** - Use this command if you think the ansibot is misbehaving, and an Ansible staff member will investigate.
* **bot_skip** - Ansible staff members use this to have the bot skip triaging an issue.
* **needs_info** - Use this command if you need more information from the submitter. We will notify the submitter and apply the needs_info label.
* **!needs_info** - If you do not need any more information and just need time to work the issue, leave a comment that contains the command `!needs_info` and the *needs_info* label will be replaced with `waiting_on_maintainer`.
* **needs_revision** - Use this command if you would like the submitter to make changes.
* **!needs_revision** - If you want to clear the needs_revision label, use this command.
* **needs_rebase** - Use this command if the submitters branch is out of date. The bot should automatically apply this label, so you may never need to use it.
* **!needs_rebase** - Clear the needs_rebase label.
* **notabug** - If you believe this is not a bug, please leave a comment stating `notabug`, along with any additional information as to why it is not, and we will close this issue.
* **bug_resolved** - If you believe this issue is resolved, please leave a comment stating bug_resolved, and we will close this issue. 
* **resolved_by_pr** - If you believe this issue has been resolved by a pull request, please leave a comment stating `resolved_by_pr` followed by the pull request number. 
* **wontfix** - If this is a bug that you can't or won't fix, please leave a comment including the word `wontfix`, along with an explanation for why it won't be fixed.
* **needs_contributor** - If this bug or feature request is something that you want implemented but do not have the time or expertise to do, comment with `needs_contributor`, and the issue will be put into a `waiting_on_contributor` state.
* **duplicate_of** - If this bug or feature request is a duplicate of another issue, comment with `duplicate_of` followed by the issue number that it duplicates, and the issue will be closed.

## For anyone else
Reactions help us determine how many people are interested in a pullrequest or have run across a similar bug. Please leave a +1 reaction if that applies to you. Any additional details you can provide, such as your usecase, environment, steps to reproduce, or workarounds you have found, can help out with resolving issues or getting pullrequests merged.
