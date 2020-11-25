from abc import ABCMeta, abstractmethod, abstractproperty
from six import with_metaclass


class BaseCI(with_metaclass(ABCMeta, object)):
    """An interface that each CI provider that bot could use must implement.
    """

    name = None

    @abstractproperty
    def state(self):
        """

        :rtype: str or None
        """
        raise NotImplementedError

    @abstractproperty
    def updated_at(self):
        """Timestamp of last job completion for given PR number.

        :rtype: datetime.datetime
        """
        raise NotImplementedError

    @abstractmethod
    def get_last_full_run_date(self):
        """Timestamp of last full run. Maps partial re-runs back to their full
        run.

        :rtype: datetime.datetime
        """
        raise NotImplementedError

    @abstractmethod
    def get_test_results(self):
        """Get test results of given run_id and figure out a ci_verified out
        of it.

        :type run_id: str
        :rtype: tuple(bool, list)
        """
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
