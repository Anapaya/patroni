#!/usr/bin/env python3

import logging
import time

from acceptance.common.log import LogExec, initLog
from acceptance.common import test

test.TEST_NAME = "2node_full_follower_failure"
logger = logging.getLogger(__name__)


class Test(test.Base):
    """
    Test that we can kill the full follower node, i.e. consul and patroni and recover from it.
    """


@Test.subcommand("run")
class TestRun(test.Base):
    util = test.Util(None)

    @LogExec(logger, "run")
    def main(self):
        self.util = test.Util(self.dc)
        initial_leader, initial_replica = self.util.initial_check()

        self.util.kill_node(initial_replica)
        # Now give some time so that the leader actually notices the consul problem.
        time.sleep(20)

        self.util.wait_until_role(initial_leader, 'master')
        self.util.test_write_to(initial_leader, 2)

        self.util.restore_node(initial_replica)
        self.util.wait_until_role(initial_leader, 'master')

        self.util.test_read_from(initial_leader, "2")
        self.util.wait_until_role(initial_replica, 'replica')
        self.util.read_until_expected(initial_replica, "2")

        logger.info("Test successful")


if __name__ == "__main__":
    initLog()
    Test()
