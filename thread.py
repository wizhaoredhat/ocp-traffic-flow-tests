from threading import Thread
from logger import logger

class ReturnValueThread(Thread):
    def __init__(self, *args, **kwargs):
        self._target = None
        self._args = args
        self._kwargs = kwargs
        super().__init__(*args, **kwargs)
        self.result = None

    def run(self):
        if self._target is None:
            return
        try:
            self.result = self._target(*self._args, **self._kwargs)
        except Exception as e:
            logger.error(e)
            pass

    def join(self, *args, **kwargs):
        super().join(*args, **kwargs)
        return self.result
