#!/usr/bin/env python3

import logging
import json
import sys
import time

from plumbum.cmd import (
    curl,
)

from acceptance.common.log import LogExec, initLog
from acceptance.common import test
from acceptance.common.tools import container_ip

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
        logger.info("Find leader in consul")
        initial_leader = self.util.leader_name()
        if not initial_leader:
            logger.error("Failed to find leader")
            sys.exit(1)

        self.util.test_write_to(initial_leader, 1)
        initial_replica = self.util.wait_for_replica()
        self.util.test_read_from(initial_replica, "1")
        self.util.test_not_writable(initial_replica)

        self.kill_consul(initial_leader)
        self.wait_until_role(initial_replica, container_ip(initial_replica))
        self.util.test_write_to(initial_replica, 2)
        self.util.test_not_writable(initial_leader)
        # TODO(lukedirtwalker): This would need some modifications on the node that hasn't consul.
        # But would it be worth it? Usually the whole node is probably down.
        # self.util.test_read_from(initial_leader, "2")

        # wait a little so that we can "stabilize" in this state.
        time.sleep(3)

        self.restore_consul(initial_leader)
        # wait a bit here. Note that on consul the old leader is still stored. It takes a bit until
        # the leader change is reflected in consul. But in the patroni API we will already see the
        # correct node.
        time.sleep(1)
        self.wait_until_role(initial_replica, container_ip(initial_replica))

        self.util.test_read_from(initial_replica, "2")
        self.wait_until_role(initial_leader, container_ip(initial_leader), 'replica')
        # Wait until update propagated
        for _ in range(0, 10):
            result = self.util.read_from(initial_leader)
            if result == "2":
                break
            time.sleep(1)
        self.util.test_read_from(initial_leader, "2")

        logger.info("Test successful")

    def kill_consul(self, patroni_name: str):
        leader_idx = patroni_name[len('patroni_server'):]
        consul = 'consul_server%s' % leader_idx
        logger.info("Killing %s", consul)
        self.util.dc('kill', consul)

    def restore_consul(self, patroni_name: str):
        leader_idx = patroni_name[len('patroni_server'):]
        consul = 'consul_server%s' % leader_idx
        logger.info("Restart %s", consul)
        self.util.dc('up', '-d', consul)

    def wait_until_role(self, name: str, ip: str, role: str = 'master'):
        logger.info("Waiting until %s (%s) has role %s", name, ip, role)
        info = self.patroni_info(ip)
        for _ in range(0, 30):
            if info and info['role'] == role:
                logger.info("%s is now %s", name, role)
                return
            time.sleep(1)
            info = self.patroni_info(ip)
        logger.error("%s didn't become %s in time", name, role)
        sys.exit(1)

    def patroni_info(self, ip: str):
        out = curl('-sS', 'http://%s:8008' % ip)
        if not out:
            return None
        return json.loads(out)


if __name__ == "__main__":
    initLog()
    Test()
