import logging

from . import common


def test_logger_1() -> None:
    name = "foo.1"
    logger = common.ExtendedLogger(name)
    assert isinstance(logger, logging.Logger)
    assert isinstance(logger, common.ExtendedLogger)
    assert logger.name == name
    assert logger.wrapped_logger is logging.getLogger(name)

    common.log_config_logger(logging.DEBUG, logger)
    assert logger.level == logging.DEBUG
    assert logger.wrapped_logger.level == logging.DEBUG

    common.log_config_logger(logging.INFO, logger, logger.wrapped_logger)
    assert logger.level == logging.INFO
    assert logger.wrapped_logger.level == logging.INFO
    assert logging.getLogger(name).level == logging.INFO

    assert logger.handlers is logger.wrapped_logger.handlers
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], common._LogHandler)

    logger.info(f"test {name}")
