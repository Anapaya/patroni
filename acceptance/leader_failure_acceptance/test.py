#!/usr/bin/env python3

import logging
import time

from acceptance.common.log import LogExec, initLog
from acceptance.common import test

test.TEST_NAME = "leader_failure"
logger = logging.getLogger(__name__)


class Test(test.Base):
    """
    Test that we can kill the patroni leader node and the cluster will fail over to the second node.
    """


@Test.subcommand("run")
class TestRun(test.Base):
    util = test.Util(None)

    @LogExec(logger, "run")
    def main(self):
        self.util = test.Util(self.dc)
        initial_leader, initial_replica = self.util.initial_check()

        self.test_switch_leader(initial_leader, 2)
        time.sleep(10)  # let the cluster stabilize again.
        self.test_switch_leader(initial_replica, 3)

    def test_switch_leader(self, current_leader: str, expected_val):
        modify_idx, _ = self.util.leader_info()
        old_leader = current_leader
        logger.info("Killing %s", old_leader)
        self.dc('kill', old_leader)
        new_leader = self.util.wait_for_leader(modify_idx)

        self.util.test_write_to(new_leader, expected_val)

        logger.info("Restart %s", old_leader)
        self.dc('up', '-d', old_leader)
        self.util.test_read_from(self.util.wait_for_replica(), str(expected_val))


if __name__ == "__main__":
    initLog()
    Test()
