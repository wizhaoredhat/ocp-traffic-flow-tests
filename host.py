import subprocess
from collections import namedtuple
import os
import json
import shlex
import sys
from logger import logger
from abc import ABC, abstractmethod


Result = namedtuple("Result", "out err returncode")


class Host(ABC):
    def ipa(self) -> dict:
        return json.loads(self.run("ip -json a").out)

    def ipr(self) -> dict:
        return json.loads(self.run("ip -json r").out)

    def all_ports(self) -> dict:
        return json.loads(self.run("ip -json link").out)

    @abstractmethod
    def run(self, cmd: str, env: dict = os.environ.copy()) -> Result:
        pass


class LocalHost(Host):
    def __init__(self) -> None:
        pass

    def run(self, cmd: str, env: dict = os.environ.copy()) -> Result:
        args = shlex.split(cmd)
        pipe = subprocess.PIPE
        with subprocess.Popen(args, stdout=pipe, stderr=pipe, env=env) as proc:
            if proc.stdout is None:
                logger.info("Can't find stdout")
                sys.exit(-1)
            if proc.stderr is None:
                logger.info("Can't find stderr")
                sys.exit(-1)
            out = proc.stdout.read().decode("utf-8")
            err = proc.stderr.read().decode("utf-8")
            proc.communicate()
            ret = proc.returncode
        return Result(out, err, ret)

    def file_exists(self, path: str) -> bool:
        return os.path.exists(path)
