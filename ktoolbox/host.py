import dataclasses
import logging
import os
import shlex
import subprocess
import sys
import threading
import typing

from abc import ABC
from abc import abstractmethod
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import Optional
from typing import Union

from .logger import logger

INTERNAL_ERROR_PREFIX = "Host.run(): "
INTERNAL_ERROR_RETURNCODE = 1


_lock = threading.Lock()

_unique_log_id_value = 0

# Same as common.KW_ONLY_DATACLASS, but we should not use common module here.
# See common.KW_ONLY_DATACLASS why this is used.
KW_ONLY_DATACLASS = {"kw_only": True} if "kw_only" in dataclass.__kwdefaults__ else {}


def _normalize_cmd(
    cmd: Union[str, Iterable[str]],
) -> Union[str, tuple[str, ...]]:
    if isinstance(cmd, str):
        return cmd
    else:
        return tuple(cmd)


def _normalize_env(
    env: Optional[Mapping[str, Optional[str]]],
) -> Optional[dict[str, Optional[str]]]:
    if env is None:
        return None
    return dict(env)


def _cmd_to_logstr(cmd: Union[str, tuple[str, ...]]) -> str:
    return repr(_cmd_to_shell(cmd))


def _cmd_to_shell(cmd: Union[str, Iterable[str]]) -> str:
    if isinstance(cmd, str):
        return cmd
    return shlex.join(cmd)


def _cmd_to_argv(cmd: Union[str, Iterable[str]]) -> tuple[str, ...]:
    if isinstance(cmd, str):
        return ("/bin/sh", "-c", cmd)
    return tuple(cmd)


def _unique_log_id() -> int:
    # For each run() call, we log a message when starting the command and when
    # completing it. Add a unique number to those logging statements, so that
    # we can easier find them in a large log.
    with _lock:
        global _unique_log_id_value
        _unique_log_id_value += 1
        return _unique_log_id_value


T = typing.TypeVar("T", bound=Union[str, bytes])


@dataclass(frozen=True)
class _BaseResult(ABC, typing.Generic[T]):
    # _BaseResult only exists to have the first 3 parameters positional
    # arguments and the subsequent parameters (in BaseResult) marked as
    # KW_ONLY_DATACLASS. Once we no longer support Python 3.9, the classes
    # can be merged.
    out: T
    err: T
    returncode: int


@dataclass(frozen=True, **KW_ONLY_DATACLASS)
class BaseResult(_BaseResult[T]):
    # In most cases, "success" is the same as checking for returncode zero.  In
    # some cases, it can be overwritten to be of a certain value.
    forced_success: Optional[bool] = dataclasses.field(
        default=None,
        # kw_only=True <- use once we upgrade to 3.10 and drop KW_ONLY_DATACLASS.
    )

    @property
    def success(self) -> bool:
        if self.forced_success is not None:
            return self.forced_success
        return self.returncode == 0

    def debug_str(self) -> str:
        if self.forced_success is None or self.forced_success == (self.returncode == 0):
            if self.success:
                status = "success"
            else:
                status = f"failed (exit {self.returncode})"
        else:
            if self.forced_success:
                status = f"success [forced] (exit {self.returncode})"
            else:
                status = "failed [forced] (exit 0)"

        out = ""
        if self.out:
            out = f"; out={repr(self.out)}"

        err = ""
        if self.err:
            err = f"; err={repr(self.err)}"

        return f"{status}{out}{err}"

    def debug_msg(self) -> str:
        return f"cmd {self.debug_str()}"


@dataclass(frozen=True)
class Result(BaseResult[str]):
    def dup_with_forced_success(self, forced_success: bool) -> "Result":
        if forced_success == self.success:
            return self
        return Result(
            self.out,
            self.err,
            self.returncode,
            forced_success=forced_success,
        )


@dataclass(frozen=True)
class BinResult(BaseResult[bytes]):
    def decode(self, errors: str = "strict") -> Result:
        return Result(
            self.out.decode(errors=errors),
            self.err.decode(errors=errors),
            self.returncode,
        )

    def dup_with_forced_success(self, forced_success: bool) -> "BinResult":
        if forced_success == self.success:
            return self
        return BinResult(
            self.out,
            self.err,
            self.returncode,
            forced_success=forced_success,
        )

    @staticmethod
    def internal_failure(msg: str) -> "BinResult":
        return BinResult(
            b"",
            (INTERNAL_ERROR_PREFIX + msg).encode(errors="surrogateescape"),
            INTERNAL_ERROR_RETURNCODE,
        )


class Host(ABC):
    def __init__(
        self,
        *,
        sudo: bool = False,
    ) -> None:
        self._sudo = sudo

    @abstractmethod
    def pretty_str(self) -> str:
        pass

    def _prepare_run(
        self,
        *,
        sudo: bool,
        cwd: Optional[str],
        cmd: Union[str, Iterable[str]],
        env: Optional[Mapping[str, Optional[str]]],
    ) -> tuple[
        Union[str, tuple[str, ...]],
        Optional[dict[str, Optional[str]]],
        Optional[str],
    ]:
        if not sudo:
            return (
                _normalize_cmd(cmd),
                _normalize_env(env),
                cwd,
            )

        cmd2 = ["sudo", "-n"]

        if env:
            for k, v in env.items():
                assert k == shlex.quote(k)
                assert "=" not in k
                if v is not None:
                    cmd2.append(f"{k}={v}")

        if cwd is not None:
            # sudo's "--chdir" option often does not work based on the sudo
            # configuration.  Instead, change the directory inside the shell
            # script.
            cmd = f"cd {shlex.quote(cwd)} || exit 1 ; {_cmd_to_shell(cmd)}"

        cmd2.extend(_cmd_to_argv(cmd))

        return tuple(cmd2), None, None

    @typing.overload
    def run(
        self,
        cmd: Union[str, Iterable[str]],
        *,
        text: typing.Literal[True] = True,
        env: Optional[Mapping[str, Optional[str]]] = None,
        sudo: Optional[bool] = None,
        cwd: Optional[str] = None,
        log_prefix: str = "",
        log_level: int = logging.DEBUG,
        log_level_result: Optional[int] = None,
        log_level_fail: Optional[int] = None,
        check_success: Optional[Callable[[Result], bool]] = None,
        die_on_error: bool = False,
        decode_errors: Optional[str] = None,
    ) -> Result:
        pass

    @typing.overload
    def run(
        self,
        cmd: Union[str, Iterable[str]],
        *,
        text: typing.Literal[False],
        env: Optional[Mapping[str, Optional[str]]] = None,
        sudo: Optional[bool] = None,
        cwd: Optional[str] = None,
        log_prefix: str = "",
        log_level: int = logging.DEBUG,
        log_level_result: Optional[int] = None,
        log_level_fail: Optional[int] = None,
        check_success: Optional[Callable[[BinResult], bool]] = None,
        die_on_error: bool = False,
        decode_errors: Optional[str] = None,
    ) -> BinResult:
        pass

    @typing.overload
    def run(
        self,
        cmd: Union[str, Iterable[str]],
        *,
        text: bool = True,
        env: Optional[Mapping[str, Optional[str]]] = None,
        sudo: Optional[bool] = None,
        cwd: Optional[str] = None,
        log_prefix: str = "",
        log_level: int = logging.DEBUG,
        log_level_result: Optional[int] = None,
        log_level_fail: Optional[int] = None,
        check_success: Optional[
            Union[Callable[[Result], bool], Callable[[BinResult], bool]]
        ] = None,
        die_on_error: bool = False,
        decode_errors: Optional[str] = None,
    ) -> Union[Result, BinResult]:
        pass

    def run(
        self,
        cmd: Union[str, Iterable[str]],
        *,
        text: bool = True,
        env: Optional[Mapping[str, Optional[str]]] = None,
        sudo: Optional[bool] = None,
        cwd: Optional[str] = None,
        log_prefix: str = "",
        log_level: int = logging.DEBUG,
        log_level_result: Optional[int] = None,
        log_level_fail: Optional[int] = None,
        check_success: Optional[
            Union[Callable[[Result], bool], Callable[[BinResult], bool]]
        ] = None,
        die_on_error: bool = False,
        decode_errors: Optional[str] = None,
    ) -> Union[Result, BinResult]:
        log_id = _unique_log_id()

        if sudo is None:
            sudo = self._sudo

        real_cmd, real_env, real_cwd = self._prepare_run(
            sudo=sudo,
            cwd=cwd,
            cmd=cmd,
            env=env,
        )

        if log_level >= 0:
            logger.log(
                log_level,
                f"{log_prefix}cmd[{log_id};{self.pretty_str()}]: call {_cmd_to_logstr(real_cmd)}",
            )

        bin_result = self._run(
            cmd=real_cmd,
            env=real_env,
            cwd=real_cwd,
        )

        # The remainder is only concerned with printing a nice logging message and
        # (potentially) decode the binary output.

        str_result: Optional[Result] = None
        unexpected_binary = False
        is_binary = True
        decode_exception: Optional[Exception] = None
        if text:
            # The caller requested string (Result) output. "decode_errors" control what we do.
            #
            # - None (the default). We effectively use "errors='replace'"). On any encoding
            #   error we log an ERROR message.
            # - otherwise, we use "decode_errors" as requested. An encoding error will not
            #   raise the log level, but we will always log the result. We will even log
            #   the result if the decoding results in an exception (see decode_exception).
            try:
                # We first always try to decode strictly to find out whether
                # it's valid utf-8.
                str_result = bin_result.decode(errors="strict")
            except UnicodeError as e:
                if decode_errors == "strict":
                    decode_exception = e
                is_binary = True
            else:
                is_binary = False

            if decode_exception is not None:
                # We had an error. We keep this and re-raise later.
                pass
            elif not is_binary and (
                decode_errors is None
                or decode_errors in ("strict", "ignore", "replace", "surrogateescape")
            ):
                # We are good. The output is not binary, and the caller did not
                # request some unusual decoding. We already did the decoding.
                pass
            elif decode_errors is not None:
                # Decode again, this time with the decoding option requested
                # by the caller.
                try:
                    str_result = bin_result.decode(errors=decode_errors)
                except UnicodeError as e:
                    decode_exception = e
            else:
                # We have a binary and the caller didn't specify a special
                # encoding. We use "replace" fallback, but set a flag that
                # we have unexpected_binary (and lot an ERROR below).
                str_result = bin_result.decode(errors="replace")
                unexpected_binary = True

        if check_success is None:
            result_success = bin_result.success
        else:
            result_success = True
            if text:
                str_check = typing.cast(Callable[[Result], bool], check_success)
                if str_result is None:
                    # This can only happen in text mode when the caller specified
                    # a "decode_errors" that resulted in a "decode_exception".
                    # The function will raise an exception, and we won't call
                    # the check_success() handler.
                    #
                    # Avoid this by using text=False or a "decode_errors" value
                    # that does not fail.
                    result_success = False
                elif not str_check(str_result):
                    result_success = False
            else:
                bin_check = typing.cast(Callable[[BinResult], bool], check_success)
                if not bin_check(bin_result):
                    result_success = False

        status_msg = ""
        if log_level_fail is not None and not result_success:
            result_log_level = log_level_fail
        elif log_level_result is not None:
            result_log_level = log_level_result
        else:
            result_log_level = log_level

        if die_on_error and not result_success:
            if result_log_level < logging.ERROR:
                result_log_level = logging.ERROR
            status_msg += " [FATAL]"

        if text and is_binary:
            status_msg += " [BINARY]"

        if decode_exception:
            # We caught an exception during decoding. We still want to log the result,
            # before re-raising the exception.
            #
            # We don't increase the logging level, because the user requested a special
            # "decode_errors". A decoding error is expected, we just want to log about it
            # (with the level we would have).
            status_msg += " [DECODE_ERROR]"

        if unexpected_binary:
            status_msg += " [UNEXPECTED_BINARY]"
            if result_log_level < logging.ERROR:
                result_log_level = logging.ERROR

        if str_result is not None:
            str_result = str_result.dup_with_forced_success(result_success)
        bin_result = bin_result.dup_with_forced_success(result_success)

        if result_log_level >= 0:
            if is_binary:
                # Note that we log the output as binary if either "text=False" or if
                # the output was not valid utf-8. In the latter case, we will still
                # return a string Result (or re-raise decode_exception).
                debug_str = bin_result.debug_str()
            else:
                assert str_result is not None
                debug_str = str_result.debug_str()

            logger.log(
                result_log_level,
                f"{log_prefix}cmd[{log_id};{self.pretty_str()}]: └──> {_cmd_to_logstr(real_cmd)}:{status_msg} {debug_str}",
            )

        if decode_exception:
            raise decode_exception

        if die_on_error and not result_success:
            import traceback

            logger.error(
                f"FATAL ERROR. BACKTRACE:\n{''.join(traceback.format_stack())}"
            )
            sys.exit(-1)

        if str_result is not None:
            return str_result
        return bin_result

    @abstractmethod
    def _run(
        self,
        *,
        cmd: Union[str, tuple[str, ...]],
        env: Optional[dict[str, Optional[str]]],
        cwd: Optional[str],
    ) -> BinResult:
        pass

    def file_exists(self, path: Union[str, os.PathLike[Any]]) -> bool:
        return self.run(["test", "-e", str(path)], log_level=-1, text=False).success


class LocalHost(Host):
    def pretty_str(self) -> str:
        return "localhost"

    def _run(
        self,
        *,
        cmd: Union[str, tuple[str, ...]],
        env: Optional[dict[str, Optional[str]]],
        cwd: Optional[str],
    ) -> BinResult:
        full_env: Optional[dict[str, str]] = None
        if env is not None:
            full_env = os.environ.copy()
            for k, v in env.items():
                if v is None:
                    full_env.pop(k, None)
                else:
                    full_env[k] = v

        try:
            res = subprocess.run(
                cmd,
                shell=isinstance(cmd, str),
                capture_output=True,
                env=full_env,
                cwd=cwd,
            )
        except Exception as e:
            # We get an FileNotFoundError if cwd directory does not exist or if
            # the binary does not exist (with shell=False). We get a PermissionError
            # if we don't have permissions.
            #
            # Generally, we don't want to report errors via exceptions, because
            # you won't get the same exception with shell=True. Instead, we
            # only report errors via BinResult().
            #
            # Usually we avoid creating an artificial BinResult. In this case
            # there is no choice.
            return BinResult.internal_failure(str(e))

        return BinResult(res.stdout, res.stderr, res.returncode)

    def file_exists(self, path: Union[str, os.PathLike[Any]]) -> bool:
        return os.path.exists(path)


local = LocalHost()


def host_or_local(host: Optional[Host]) -> Host:
    if host is None:
        return local
    return host
