#!/usr/bin/env python3

import logging
import sys
import time

from acceptance.common.log import LogExec, initLog
from acceptance.common import test

test.TEST_NAME = "follower_failure"
logger = logging.getLogger(__name__)


class Test(test.Base):
    """
    Test that we can kill the patroni follower node and the cluster will continue to work.
    """


@Test.subcommand("run")
class TestRun(test.Base):
    util = test.Util(None)

    @LogExec(logger, "run")
    def main(self):
        self.util = test.Util(self.dc)
        logger.info("Find leader in consul")
        ln = self.util.leader_name()
        if not ln:
            logger.error("Failed to find leader")
            sys.exit(1)

        self.util.test_write_to(ln, 1)
        replica = self.util.wait_for_replica()
        self.util.test_read_from(replica, "1")
        self.util.test_not_writable(replica)

        # Now kill the replica
        logger.info("Killing %s", replica)
        self.util.dc('kill', replica)
        time.sleep(1)
        self.util.test_write_to(ln, 2)

        # Restart and check that we can see the data.
        logger.info("Restart %s", replica)
        self.dc('up', '-d', replica)
        self.util.test_read_from(self.util.wait_for_replica(), "2")


if __name__ == "__main__":
    initLog()
    Test()
