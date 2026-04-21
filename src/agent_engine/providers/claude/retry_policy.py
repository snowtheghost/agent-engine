from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class RetryAction(Enum):
    REVIVAL_ROLLBACK = "revival_rollback"
    RAISE = "raise"


class RetryPolicy:

    def __init__(self) -> None:
        self._revival_step: int = 0

    def reset(self) -> None:
        self._revival_step = 0

    @property
    def revival_step(self) -> int:
        return self._revival_step

    def evaluate(self, is_resuming: bool) -> RetryAction:
        if is_resuming and self._revival_step == 0:
            return RetryAction.REVIVAL_ROLLBACK
        return RetryAction.RAISE

    def advance_revival(self, rollback_succeeded: bool) -> None:
        if rollback_succeeded:
            self._revival_step = 1
        else:
            self._revival_step = 2
