from functools import wraps
import logging


class LogExec(object):
    def __init__(self, logger: logging.Logger, subcommand: str):
        self.subcommand = subcommand
        self.logger = logger

    def __call__(self, f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            self.logger.info("Start %s" % self.subcommand)
            ret = f(*args, **kwargs)
            if ret:
                self.logger.warn("Failed %s" % self.subcommand)
                return ret
            self.logger.info("Finished %s" % self.subcommand)
        return wrapper


def initLog():
    FORMAT = '%(asctime)-15s [%(levelname)-8s] %(message)s'
    logging.basicConfig(format=FORMAT, level='INFO')
