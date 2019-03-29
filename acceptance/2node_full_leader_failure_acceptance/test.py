#!/usr/bin/env python3

import logging
import time

from acceptance.common.log import LogExec, initLog
from acceptance.common import test

test.TEST_NAME = "2node_full_leader_failure"
logger = logging.getLogger(__name__)


class Test(test.Base):
    """
    Test that we can kill the full leader node, i.e. consul and patroni and recover from it.
    """


@Test.subcommand("run")
class TestRun(test.Base):
    util = test.Util(None)

    @LogExec(logger, "run")
    def main(self):
        self.util = test.Util(self.dc)
        initial_leader, initial_replica = self.util.initial_check()

        self.kill_node(initial_leader)
        self.util.wait_until_role(initial_replica, 'master')

        # wait a little so that we can "stabilize" in this state.
        time.sleep(3)
        self.util.test_write_to(initial_replica, 2)

        self.restore_node(initial_leader)
        # wait a bit so that the node is back up before we ping it.
        time.sleep(6)
        self.util.wait_until_role(initial_replica, 'master')

        self.util.test_read_from(initial_replica, "2")
        self.util.wait_until_role(initial_leader, 'replica')
        # Wait until update propagated
        for _ in range(0, 10):
            result = self.util.read_from(initial_leader)
            if result == "2":
                break
            time.sleep(1)
        self.util.test_read_from(initial_leader, "2")

        logger.info("Test successful")

    def kill_node(self, patroni_name: str):
        leader_idx = patroni_name[len('patroni_server'):]
        consul = 'consul_server%s' % leader_idx
        logger.info("Killing node %s", leader_idx)
        self.util.dc('kill', consul)
        self.util.dc('kill', patroni_name)

    def restore_node(self, patroni_name: str):
        leader_idx = patroni_name[len('patroni_server'):]
        consul = 'consul_server%s' % leader_idx
        logger.info("Restart node %s", leader_idx)
        self.util.dc('up', '-d', consul)
        self.util.dc('up', '-d', patroni_name)


if __name__ == "__main__":
    initLog()
    Test()
