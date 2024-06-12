import threading

from typing import ClassVar
from typing import Optional

from threading import Barrier


# Singleton class, synchronizes threads using barriers and events
# https://docs.python.org/3/library/threading.html
class SyncManager:
    _instance: ClassVar[Optional["SyncManager"]] = None
    _lock: ClassVar[threading.RLock] = threading.RLock()
    start_barrier: Barrier

    def __new__(cls, barrier_size: int) -> "SyncManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SyncManager, cls).__new__(cls)
                cls._initialize(barrier_size)
        return cls._instance

    @staticmethod
    def _initialize(barrier_size: int) -> None:
        assert (
            SyncManager._instance is not None
        ), "SyncManager._instance is not initialized"
        SyncManager._instance.start_barrier = Barrier(barrier_size)

    @classmethod
    def reset(cls, barrier_size: int) -> None:
        assert barrier_size >= 0, "barrier_size must be non-negative"
        with cls._lock:
            if cls._instance is None:
                cls.__new__(cls, barrier_size)
            else:
                cls._initialize(barrier_size)

    # .wait() on a barrier decrements it
    # once the barrier hits 0, all waiting threads are simultaneously unblocked
    @classmethod
    def wait_on_barrier(cls) -> None:
        if cls._instance and cls._instance.start_barrier:
            cls._instance.start_barrier.wait()
