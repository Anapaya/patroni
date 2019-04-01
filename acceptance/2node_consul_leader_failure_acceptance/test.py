#!/usr/bin/env python3

import logging
import time

from acceptance.common.log import LogExec, initLog
from acceptance.common import test

test.TEST_NAME = "2node_consul_leader_failure"
logger = logging.getLogger(__name__)


class Test(test.Base):
    """
    Test that we can kill the consul server of the leader node and the other node will take over
    leadership in the 2 node backend.
    """


@Test.subcommand("run")
class TestRun(test.Base):
    util = test.Util(None)

    @LogExec(logger, "run")
    def main(self):
        self.util = test.Util(self.dc)
        initial_leader, initial_replica = self.util.initial_check()

        self.util.kill_consul(initial_leader)
        self.util.wait_until_role(initial_replica, 'master')
        self.util.test_write_to(initial_replica, 2)
        self.util.test_not_writable(initial_leader)
        # TODO(lukedirtwalker): This would need some modifications on the node that hasn't consul.
        # But would it be worth it? Usually the whole node is probably down.
        # self.util.test_read_from(initial_leader, "2")

        # wait a little so that we can "stabilize" in this state.
        time.sleep(3)

        self.util.restore_consul(initial_leader)
        # wait a bit here. Note that on consul the old leader is still stored. It takes a bit until
        # the leader change is reflected in consul. But in the patroni API we will already see the
        # correct node.
        time.sleep(1)
        self.util.wait_until_role(initial_replica, 'master')

        self.util.test_read_from(initial_replica, "2")
        self.util.wait_until_role(initial_leader, 'replica')
        self.util.read_until_expected(initial_leader, "2")

        logger.info("Test successful")


if __name__ == "__main__":
    initLog()
    Test()
