from threading import Thread
from logger import logger
from typing import Any, Callable, Optional


class ReturnValueThread(Thread):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._target: Optional[Callable[..., Any]] = None
        self._args: tuple = args
        self._kwargs: dict = kwargs
        super().__init__(*args, **kwargs)
        self.result: Optional[Any] = None

    def run(self) -> None:
        if self._target is None:
            return
        try:
            self.result = self._target(*self._args, **self._kwargs)
        except Exception as e:
            logger.error(e)
            pass

    def join(self, *args: Any, **kwargs: Any) -> Optional[Any]:
        super().join(*args, **kwargs)
        return self.result
