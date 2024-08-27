import functools
import os
import pathlib
import pytest
import sys

from . import host


@functools.cache
def has_sudo(rsh: host.Host) -> bool:
    r = rsh.run("sudo -n whoami")
    return r == host.Result("root\n", "", 0)


def skip_without_sudo(rsh: host.Host) -> None:
    if not has_sudo(rsh):
        pytest.skip(
            "sudo on {rsh.pretty_str()} does not seem to work passwordless ({r})"
        )


def test_host_result_bin() -> None:
    res = host.local.run("echo -n out; echo -n err >&2", text=False)
    assert res == host.BinResult(b"out", b"err", 0)


def test_host_result_surrogateescape() -> None:
    res = host.local.run("echo -n hi", decode_errors="surrogateescape")
    assert res == host.Result("hi", "", 0)

    cmd = ["bash", "-c", "printf $'xx<\\325>'"]

    res_bin = host.local.run(cmd, text=False)
    assert res_bin == host.BinResult(b"xx<\325>", b"", 0)

    res = host.local.run(cmd, decode_errors="surrogateescape")
    assert res == host.Result("xx<\udcd5>", "", 0)
    with pytest.raises(UnicodeEncodeError):
        res.out.encode()
    assert res.out.encode(errors="surrogateescape") == b"xx<\325>"

    res_bin = host.local.run(["bash", "-c", 'printf "xx<\udcd5>"'], text=False)
    assert res_bin == host.BinResult(b"xx<\325>", b"", 0)

    res_bin = host.local.run(["echo", "-n", "xx<\udcd5>"], text=False)
    assert res_bin == host.BinResult(b"xx<\325>", b"", 0)

    cmd2 = b'echo -n "xx<\325>"'.decode(errors="surrogateescape")
    res_bin = host.local.run(cmd2, text=False)
    assert res_bin == host.BinResult(b"xx<\325>", b"", 0)

    t = False
    res_any = host.local.run(cmd2, text=t)
    assert isinstance(res_any, host.BinResult)
    assert res_any == host.BinResult(b"xx<\325>", b"", 0)

    res = host.local.run(cmd2)
    assert res == host.Result("xx<�>", "", 0)

    res = host.local.run(cmd2, decode_errors="surrogateescape")
    assert res == host.Result("xx<\udcd5>", "", 0)

    res_bin = host.local.run(["bash", "-c", cmd2], text=False)
    assert res_bin == host.BinResult(b"xx<\325>", b"", 0)


def test_host_result_str() -> None:
    res = host.local.run("echo -n out; echo -n err >&2", text=True)
    assert res == host.Result("out", "err", 0)

    res = host.local.run("echo -n out; echo -n err >&2")
    assert res == host.Result("out", "err", 0)


def test_host_various_results() -> None:
    res = host.local.run('printf "foo:\\705x"')
    assert res == host.Result("foo:\ufffdx", "", 0)

    # The result with decode_errors="replace" is the same as if decode_errors
    # is left unspecified. However, the latter case will log an ERROR message
    # when seeing unexpected binary. If you set decode_errors, you expect
    # binary, and no error message is logged.
    res = host.local.run('printf "foo:\\705x"', decode_errors="replace")
    assert res == host.Result("foo:\ufffdx", "", 0)

    res = host.local.run('printf "foo:\\705x"', decode_errors="ignore")
    assert res == host.Result("foo:x", "", 0)

    with pytest.raises(UnicodeDecodeError):
        res = host.local.run('printf "foo:\\705x"', decode_errors="strict")

    res = host.local.run('printf "foo:\\705x"', decode_errors="backslashreplace")
    assert res == host.Result("foo:\\xc5x", "", 0)

    binres = host.local.run('printf "foo:\\705x"', text=False)
    assert binres == host.BinResult(b"foo:\xc5x", b"", 0)


def test_host_check_success() -> None:

    res = host.local.run("echo -n foo", check_success=lambda r: r.success)
    assert res == host.Result("foo", "", 0)
    assert res.success

    res = host.local.run("echo -n foo", check_success=lambda r: r.out != "foo")
    assert res == host.Result("foo", "", 0, forced_success=False)
    assert not res.success

    binres = host.local.run(
        "echo -n foo", text=False, check_success=lambda r: r.out != b"foo"
    )
    assert binres == host.BinResult(b"foo", b"", 0, forced_success=False)
    assert not binres.success

    res = host.local.run("echo -n foo; exit 74", check_success=lambda r: r.success)
    assert res == host.Result("foo", "", 74)
    assert not res.success

    res = host.local.run("echo -n foo; exit 74", check_success=lambda r: r.out == "foo")
    assert res == host.Result("foo", "", 74, forced_success=True)
    assert res.success

    binres = host.local.run(
        "echo -n foo; exit 74", text=False, check_success=lambda r: r.out == b"foo"
    )
    assert binres == host.BinResult(b"foo", b"", 74, forced_success=True)
    assert binres.success


def test_host_file_exists() -> None:
    assert host.local.file_exists(__file__)
    assert host.Host.file_exists(host.local, __file__)
    assert host.local.file_exists(os.path.dirname(__file__))
    assert host.Host.file_exists(host.local, os.path.dirname(__file__))

    assert host.local.file_exists(pathlib.Path(__file__))
    assert host.Host.file_exists(host.local, pathlib.Path(__file__))


def test_result_typing() -> None:
    host.Result("out", "err", 0)
    host.Result("out", "err", 0, forced_success=True)
    host.BinResult(b"out", b"err", 0)
    host.BinResult(b"out", b"err", 0, forced_success=True)

    if sys.version_info >= (3, 10):
        with pytest.raises(TypeError):
            host.Result("out", "err", 0, True)
        with pytest.raises(TypeError):
            host.BinResult(b"out", b"err", 0, True)
    else:
        host.Result("out", "err", 0, True)
        host.BinResult(b"out", b"err", 0, True)


def test_env() -> None:
    res = host.local.run('echo ">>$FOO<<"', env={"FOO": "xx1"})
    assert res == host.Result(">>xx1<<\n", "", 0)


def test_cwd() -> None:
    res = host.local.run("pwd", cwd="/usr/bin")
    assert res == host.Result("/usr/bin\n", "", 0)

    res = host.local.run(["pwd"], cwd="/usr/bin")
    assert res == host.Result("/usr/bin\n", "", 0)

    res = host.local.run("pwd", cwd="/usr/bin/does/not/exist")
    assert res.out == ""
    assert res.returncode == 1
    assert "/usr/bin/does/not/exist" in res.err

    res = host.local.run("pwd", cwd="/root")
    if res == host.Result("/root\n", "", 0):
        # We have permissions to access the directory.
        pass
    else:
        assert res.out == ""
        assert res.returncode == 1
        assert "/root" in res.err


def test_sudo() -> None:
    skip_without_sudo(host.local)

    rsh = host.LocalHost(sudo=True)

    assert rsh.run("whoami") == host.Result("root\n", "", 0)

    assert rsh.run(["whoami"]) == host.Result("root\n", "", 0)

    res = rsh.run('echo ">>$FOO<"', env={"FOO": "xx1"})
    assert res == host.Result(">>xx1<\n", "", 0)

    res = rsh.run(
        ["bash", "-c", 'echo ">>$FOO2<" >&2; exit 55'], env={"FOO2": "xx1", "F1": None}
    )
    assert res == host.Result("", ">>xx1<\n", 55)

    res = rsh.run("pwd", cwd="/usr/bin")
    assert res == host.Result("/usr/bin\n", "", 0)

    res = rsh.run(["pwd"], cwd="/usr/bin")
    assert res == host.Result("/usr/bin\n", "", 0)

    res = rsh.run("echo hi; whoami >&2; pwd", cwd="/usr/bin")
    assert res == host.Result("hi\n/usr/bin\n", "root\n", 0)

    res = rsh.run(["bash", "-c", "echo hi; whoami >&2; pwd"], cwd="/usr/bin")
    assert res == host.Result("hi\n/usr/bin\n", "root\n", 0)

    res = rsh.run("pwd", cwd="/usr/bin/does/not/exist")
    assert res.out == ""
    assert res.returncode == 1
    assert "/usr/bin/does/not/exist" in res.err

    res = rsh.run("pwd", cwd="/root")
    assert res == host.Result("/root\n", "", 0)
