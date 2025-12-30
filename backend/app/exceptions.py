class TaskSetupError(Exception):
    """Base exception for errors during task setup."""

    pass


class JobAlreadyCancellingError(TaskSetupError):
    """Raised when trying to start a job that is already in CANCELLING state."""

    pass


class JobAlreadyTerminalError(TaskSetupError):
    """Raised when trying to start a job that is already in a terminal state."""

    pass


class JobNotFoundErrorForSetup(TaskSetupError):
    """Raised when the job is not found during setup."""

    pass
