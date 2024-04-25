from threading import Thread
from logger import logger
from common import Result
from typing import Callable, Any, Optional


class ReturnValueThread(Thread):
    def __init__(self, *args: Any, **kwargs: Any):
        self._target: Callable[..., Result] = None
        self._args = args
        self._kwargs = kwargs
        super().__init__(*args, **kwargs)
        self.result: Optional[Result] = None

    def run(self) -> None:
        if self._target is None:
            logger.error("Called ReturnValueThread with target=None")
            return
        try:
            self.result = self._target(*self._args, **self._kwargs)
        except Exception as e:
            logger.error(f"Thread with target {self._target} experienced exception {e}")

    def join(self, *args: Any, **kwargs: Any) -> Result:
        super().join(*args, **kwargs)
        return self.result
