from threading import Thread
from typing import Any
from typing import Callable
from typing import Optional

from host import Result
from logger import logger


class ReturnValueThread(Thread):
    def __init__(
        self,
        target: Optional[Callable[..., Result]],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] = {},
        cleanup_action: Optional[Callable[..., Result]] = None,
        cleanup_args: tuple[Any, ...] = (),
        cleanup_kwargs: dict[str, Any] = {},
    ) -> None:
        super().__init__()
        self._target = target
        self._args = args
        self._kwargs = kwargs
        self._cleanup_action = cleanup_action
        self._cleanup_args = cleanup_args
        self._cleanup_kwargs = cleanup_kwargs
        self.result: Optional[Result] = None
        self.cleanup_result: Optional[Result] = None

    def run(self) -> None:
        if self._target is None:
            logger.error("Called ReturnValueThread with target=None")
            return
        try:
            self.result = self._target(*self._args, **self._kwargs)
        except Exception as e:
            logger.error(f"Thread with target {self._target} experienced exception {e}")

    def force_terminate(self) -> None:
        logger.info("Force terminate called")
        try:
            if self._cleanup_action:
                cleanup_result = self._cleanup_action(
                    *self._cleanup_args, **self._cleanup_kwargs
                )
                logger.info(
                    f"Cleanup result:{cleanup_result.out}, errcode:{cleanup_result.returncode}, err:{cleanup_result.err}"
                )
            else:
                logger.info("No cleanup_action provided")
        except Exception as e:
            logger.info(f"Exception during cleanup_action execution: {e}")

    def join_with_result(self, timeout: Optional[float] = None) -> Optional[Result]:
        super().join(timeout)
        if self.is_alive():
            logger.info(f"Thread did not terminate within the timeout time: {timeout}")
            self.force_terminate()
        return self.result
