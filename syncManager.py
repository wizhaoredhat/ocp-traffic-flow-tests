import threading
from threading import Barrier, Event
from typing import Optional, ClassVar


# Singleton class, synchronizes threads using barriers and events
# https://docs.python.org/3/library/threading.html
class SyncManager:
    _instance: ClassVar[Optional["SyncManager"]] = None
    _lock: ClassVar[threading.RLock] = threading.RLock()
    start_barrier: Barrier
    client_finished: Event
    server_alive: Event

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
        SyncManager._instance.client_finished = Event()
        SyncManager._instance.server_alive = Event()

    @classmethod
    def reset(cls, barrier_size: int) -> None:
        assert barrier_size >= 0, "barrier_size must be non-negative"
        with cls._lock:
            if cls._instance is None:
                cls.__new__(cls, barrier_size)
            else:
                cls._initialize(barrier_size)

    @classmethod
    def set_client_finished(cls) -> None:
        if cls._instance:
            cls._instance.client_finished.set()

    @classmethod
    def set_server_alive(cls) -> None:
        if cls._instance:
            cls._instance.server_alive.set()

    # .wait() on a barrier decrements it
    # once the barrier hits 0, all waiting threads are simultaneously unblocked
    @classmethod
    def wait_on_barrier(cls) -> None:
        if cls._instance and cls._instance.start_barrier:
            cls._instance.start_barrier.wait()

    @classmethod
    def wait_on_client_finish(cls) -> None:
        if cls._instance and cls._instance.client_finished:
            cls._instance.client_finished.wait()

    @classmethod
    def wait_on_server_alive(cls) -> None:
        if cls._instance and cls._instance.server_alive:
            cls._instance.server_alive.wait()

    @classmethod
    def client_not_finished(cls) -> bool:
        if cls._instance and cls._instance.client_finished:
            return not cls._instance.client_finished.is_set()
        return True
