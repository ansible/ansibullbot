import logging
import os

from logging.handlers import WatchedFileHandler


def set_logger(debug=False, logfile=None):

    logFormatter = \
            logging.Formatter("%(asctime)s %(levelname)s %(filename)s:%(funcName)s:%(lineno)d %(message)s")
    rootLogger = logging.getLogger()

    if debug:
        logging.level = logging.DEBUG
        rootLogger.setLevel(logging.DEBUG)
    else:
        logging.level = logging.INFO
        rootLogger.setLevel(logging.INFO)

    if logfile:
        try:
            logdir = os.path.dirname(logfile)
            if logdir and not os.path.isdir(logdir):
                os.makedirs(logdir)
            fileHandler = WatchedFileHandler(logfile)
            fileHandler.setFormatter(logFormatter)
            rootLogger.addHandler(fileHandler)
        except Exception as e:
            pass

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

