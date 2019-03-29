#!/usr/bin/env python3

import logging
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
        initial_leader, initial_replica = self.util.initial_check()

        # Now kill the replica
        logger.info("Killing %s", initial_replica)
        self.util.dc('kill', initial_replica)
        time.sleep(1)
        self.util.test_write_to(initial_leader, 2)

        # Restart and check that we can see the data.
        logger.info("Restart %s", initial_replica)
        self.dc('up', '-d', initial_replica)
        self.util.test_read_from(self.util.wait_for_replica(), "2")


if __name__ == "__main__":
    initLog()
    Test()
