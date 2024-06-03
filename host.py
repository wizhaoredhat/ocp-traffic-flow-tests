import json
import os
import shlex
import subprocess
import sys
import typing

from abc import ABC
from abc import abstractmethod
from typing import Any

from logger import logger
from common import Result


class Host(ABC):
    def ipa(self) -> list[dict[str, Any]]:
        r = json.loads(self.run("ip -json a").out)
        return typing.cast(list[dict[str, Any]], r)

    def ipr(self) -> list[dict[str, Any]]:
        r = json.loads(self.run("ip -json r").out)
        return typing.cast(list[dict[str, Any]], r)

    def all_ports(self) -> list[dict[str, Any]]:
        r = json.loads(self.run("ip -json link").out)
        return typing.cast(list[dict[str, Any]], r)

    @abstractmethod
    def run(self, cmd: str, env: dict[str, str] = os.environ.copy()) -> Result:
        pass


class LocalHost(Host):
    def __init__(self) -> None:
        pass

    def run(self, cmd: str, env: dict[str, str] = os.environ.copy()) -> Result:
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
