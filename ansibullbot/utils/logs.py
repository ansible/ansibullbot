import logging
import logging.handlers
import os


def set_logger(debug=False, logfile=None):
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(process)d %(filename)s:%(funcName)s:%(lineno)d %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if logfile:
        file_handler = logging.handlers.WatchedFileHandler(logfile)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
