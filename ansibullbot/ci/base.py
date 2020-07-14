from abc import ABCMeta, abstractmethod, abstractproperty
from six import with_metaclass


class BaseCI(with_metaclass(ABCMeta, object)):
    """An interface that each CI provider that bot could use must implement.
    """

    @abstractproperty
    def required_file(self):
        """Return a file name of the file that the CI provider requires to be
        present on a brach for it to be able to run.

        :rtype: str
        """
        raise NotImplementedError

    # FIXME abstract class attribute?
    state_context = None
    #@abstractproperty
    #def state_context(self):
    #    """Return a context of the CI provider.

    #    :rtype: str
    #    """
    #    raise NotImplementedError

    @abstractmethod
    def update(self):
        """Fetch the latest data from the CI provider.
        """
        raise NotImplementedError

    @abstractmethod
    def get_last_completion_date(self, pr_number):
        """Timestamp of last job completion for given PR number.

        :type pr_number: str
        :rtype: datetime.datetime
        """
        raise NotImplementedError

    @abstractmethod
    def get_last_full_run_date(self, states):
        """Timestamp of last full run. Maps partial re-runs back to their full
        run.

        :type states: list(dict)
        :rtype: datetime.datetime
        """
        raise NotImplementedError

    # FIXME figure out how to do this with other CI providers
    #@abstractmethod
    #def get_processed_run(self, run):
    #    raise NotImplementedError

    @abstractmethod
    def get_test_results(self, run_id):
        """Get test results of given run_id and figure out a ci_verified out
        of it.

        :type run_id: str
        :rtype: tuple(bool, list)
        """
        # FIXME this needs to be split into two methods
        raise NotImplementedError

    @abstractmethod
    def rebuild(self, run_id, failed_only=False):
        """Rebuild jobs. All by default, optionally failed jobs only.

        :type run_id: str
        """
        raise NotImplementedError

    def rebuild_failed(self, run_id):
        self.rebuild(run_id, failed_only=True)

    @abstractmethod
    def cancel(self, run_id):
        """Cancel jobs.

        :type run_id: str
        """
        raise NotImplementedError

    @abstractmethod
    def cancel_on_branch(self, branch):
        """Cancel all jobs on a given branch.

        :type branch: str
        """
        raise NotImplementedError
