import os
import sys

from typing import Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import jinja2util  # noqa: E402


def test_j2_render() -> None:
    def _r(contents: str, **kwargs: Any) -> str:
        return jinja2util.j2_render_data(contents, kwargs)

    assert _r("", a="1") == ""
    assert _r("val: {{a}}", a=1) == "val: 1"
    assert _r("val: {{a}}", a="1") == "val: 1"
    assert _r("val: {{a}}", a="a") == "val: a"
    assert _r("val: {{a}}", a="a b") == "val: a b"
    assert _r("val: {{a|tojson}}", a=1) == "val: 1"
    assert _r("val: {{a|tojson}}", a="1") == 'val: "1"'
    assert _r("val: {{a|tojson}}", a="a") == 'val: "a"'
    assert _r("val: {{a|tojson}}", a="a b") == 'val: "a b"'
