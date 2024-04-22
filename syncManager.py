import threading
from threading import Barrier, Event


class SyncManager:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls, barrier_size):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SyncManager, cls).__new__(cls)
                cls._initialize(barrier_size)
        return cls._instance

    @staticmethod
    def _initialize(barrier_size):
        SyncManager._instance.start_barrier = Barrier(barrier_size)
        SyncManager._instance.client_finished = Event()
        SyncManager._instance.server_alive = Event()

    @classmethod
    def reset(cls, barrier_size):
        with cls._lock:
            if barrier_size >= 0:
                if cls._instance is None:
                    cls.__new__(cls, barrier_size)
                else:
                    cls._initialize(barrier_size)

    @classmethod
    def client_finished(cls):
        if cls._instance:
            return cls._instance.client_finished

    @classmethod
    def set_client_finished(cls):
        if cls._instance:
            cls._instance.client_finished.set()

    @classmethod
    def set_server_alive(cls):
        if cls._instance:
            cls._instance.server_alive.set()

    @classmethod
    def wait_on_barrier(cls):
        if cls._instance and cls._instance.start_barrier:
            cls._instance.start_barrier.wait()

    @classmethod
    def wait_on_client_finish(cls):
        if cls._instance and cls._instance.client_finished:
            cls._instance.client_finished.wait()

    @classmethod
    def wait_on_server_alive(cls):
        if cls._instance and cls._instance.server_alive:
            cls._instance.server_alive.wait()

    @classmethod
    def client_not_finished(cls):
        if cls._instance and cls._instance.client_finished:
            return not cls._instance.client_finished.is_set()
        return True
