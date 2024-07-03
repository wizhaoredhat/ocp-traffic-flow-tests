import os
import pytest
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import testType  # noqa: E402
import tftbase  # noqa: E402


def test_handlers() -> None:
    for test_type in tftbase.TestType:
        if test_type == tftbase.TestType.HTTP:
            with pytest.raises(ValueError):
                testType.TestTypeHandler.get(test_type)
            continue
        h = testType.TestTypeHandler.get(test_type)
        assert isinstance(h, testType.TestTypeHandler)
        assert h.test_type == test_type
