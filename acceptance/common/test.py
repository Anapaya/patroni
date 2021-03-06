import logging
import json
import sys
import time
from typing import Tuple

from plumbum import cli
from plumbum import local
from plumbum.cmd import (
    curl,
    mkdir,
)
from plumbum.commands import ProcessExecutionError
from plumbum.path.utils import copy

from consul import Consul

from acceptance.common.log import LogExec
from acceptance.common.tools import DC, container_ip

TEST_NAME = "NOT_SET"  # must be set by users of the Base class.
logger = logging.getLogger(__name__)


class Base(cli.Application):
    dc = DC('')  # Just init so mypy knows the type.
    tst_dir = local.path()  # Just init so mypy knows the type.

    @cli.switch("--artifacts-dir", str, envname="ARTIFACTS_DIR", mandatory=True)
    def artifacts_dir(self, a_dir: str):
        patroni_files = '%s/%s/patroni_files' % (a_dir, TEST_NAME)
        self.tst_dir = local.path(patroni_files)
        self.dc = DC(self.tst_dir)

    def cmd_teardown(self):
        self.dc.collect_logs(self.tst_dir / 'logs' / 'docker')
        self.dc('down')

    def cmd_dc(self, *args):
        for line in self.dc(*args).splitlines():
            print(line)

    def cmd_collect_logs(self):
        self.dc.collect_logs()

    def cmd_setup(self, init_sql: str = 'acceptance/common/initsql'):
        logger.info("Setup %s", TEST_NAME)
        mkdir('-p', self.tst_dir)
        copy(local.path("acceptance/common") // "patroni*.yml", self.tst_dir)
        copy(local.path("acceptance/common/setup_cluster"), self.tst_dir)
        sql_files = local.path(init_sql) // "*.sql"
        copy(sql_files, self.tst_dir / 'initsql')
        logger.info("Build image")
        self.dc('build')
        logger.info("Starting containers")
        self.dc('up', '-d')
        # TODO(lukedirtwalker) check logs instead of sleep.
        logger.info("Waiting for patroni to be ready")
        time.sleep(20)


@Base.subcommand("setup")
class TestSetup(Base):
    @LogExec(logger, "setup")
    def main(self):
        self.cmd_setup()


@Base.subcommand("teardown")
class TestTeardown(Base):
    @LogExec(logger, "teardown")
    def main(self):
        self.cmd_teardown()


@Base.subcommand("dc")
class TestDc(Base):
    def main(self, *args):
        self.cmd_dc(*args)


@Base.subcommand("collect_logs")
class TestCollectLogs(Base):
    def main(self):
        self.cmd_collect_logs()


class Util(object):
    def __init__(self, dc: DC):
        if not dc:
            return
        self.dc = dc
        self.consul1 = Consul(host=container_ip('consul_server1'))

    def postgres_url(self, host: str) -> str:
        return 'postgres://postgres:password@%s:5432/postgres' % host

    def leader_name(self, li=None) -> str:
        if not li:
            _, li = self.leader_info()
        return str(li['Value'], 'utf8') if li and 'Value' in li else ''

    def psql(self, query: str, host: str) -> str:
        res = self.dc('exec', '-T', 'psql', 'psql', '-t', '-c', query, self.postgres_url(host))
        return res.strip()

    def test_write_to(self, host: str, val: int):
        logger.info("Test %s is writable", host)
        query = 'INSERT INTO test (val) VALUES (%s);' % val
        self.psql(query, host)

    def read_from(self, host: str) -> str:
        query = 'SELECT MAX(val) FROM test;'
        result = ''
        for _ in range(0, 5):
            try:
                result = self.psql(query, host)
                break
            except ProcessExecutionError:
                time.sleep(0.5)
                pass
        return result

    def test_read_from(self, host: str, expected: str):
        logger.info("Test %s sees data", host)
        result = self.read_from(host)
        if result != expected:
            logger.error("Wrong result: %s, expected %s", result, expected)
            sys.exit(1)

    def read_until_expected(self, host: str, expected: str, max_repeats: int = 10):
        """
        Reads repeadetly from the DB until the expected result is returned or it tried 'max_repeats'
        times.
        """
        for _ in range(0, max_repeats):
            result = self.read_from(host)
            if result == expected:
                break
            time.sleep(1)
        self.test_read_from(host, expected)

    def test_not_writable(self, host: str):
        logger.info("Test %s is not writable", host)
        query = 'INSERT INTO test (val) VALUES (2);'
        self.dc('exec', '-T', 'psql', 'psql', '-q', '-c', query, self.postgres_url(host), retcode=1)

    def leader_info(self, index: int = 0) -> Tuple[int, str]:
        return self.consul1.kv.get('service/ptest/leader', index=index)

    def wait_for_leader(self, index: int) -> str:
        index, li = self.leader_info(index)
        ln = self.leader_name(li)
        for _ in range(0, 20):
            if ln:
                logger.info("Found leader: %s", ln)
                return ln
            time.sleep(1)
            index, li = self.leader_info(index)
            ln = self.leader_name(li)
        logger.error("Didn't find new leader in time")
        sys.exit(1)

    def wait_for_replica(self) -> str:
        _, members = self.consul1.kv.get('service/ptest/members', recurse=True)
        replica = self.first_replica(members)
        for _ in range(0, 20):
            if replica:
                rn = replica['Key'][len('service/ptest/members/'):]
                logger.info("Found replica: %s", rn)
                return rn
            time.sleep(1)
            _, members = self.consul1.kv.get('service/ptest/members', recurse=True)
            replica = self.first_replica(members)
        logger.error("Didn't find replica in time")
        sys.exit(1)

    def first_replica(self, members):
        for m in members:
            member = json.loads(str(m['Value'], 'utf8'))
            if 'role' in member and member['role'] == 'replica':
                return m
        return None

    def initial_check(self) -> Tuple[str, str]:
        """
        Checks initial connectivity return (leader,replica) tuple.
        """
        logger.info("Find leader in consul")
        initial_leader = self.leader_name()
        if not initial_leader:
            logger.error("Failed to find leader")
            sys.exit(1)

        self.test_write_to(initial_leader, 1)
        initial_replica = self.wait_for_replica()
        self.test_read_from(initial_replica, "1")
        self.test_not_writable(initial_replica)
        return initial_leader, initial_replica

    def wait_until_role(self, name: str, role: str):
        """
        Waits until the node has the given role in the patroni API.
        """
        ip = container_ip(name)
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
        """
        Returns the node info from the patroni API.
        """
        # retcode 7 means the server is not reachable.
        out = curl('-sS', 'http://%s:8008' % ip, retcode=(0, 7))
        if not out:
            return None
        return json.loads(out)

    def kill_consul(self, patroni_name: str):
        leader_idx = patroni_name[len('patroni_server'):]
        consul = 'consul_server%s' % leader_idx
        logger.info("Killing %s", consul)
        self.dc('kill', consul)

    def restore_consul(self, patroni_name: str):
        leader_idx = patroni_name[len('patroni_server'):]
        consul = 'consul_server%s' % leader_idx
        logger.info("Restart %s", consul)
        self.dc('up', '-d', consul)

    def kill_node(self, patroni_name: str):
        leader_idx = patroni_name[len('patroni_server'):]
        consul = 'consul_server%s' % leader_idx
        logger.info("Killing node %s", leader_idx)
        self.dc('kill', consul)
        self.dc('kill', patroni_name)

    def restore_node(self, patroni_name: str):
        leader_idx = patroni_name[len('patroni_server'):]
        consul = 'consul_server%s' % leader_idx
        logger.info("Restart node %s", leader_idx)
        self.dc('up', '-d', consul)
        self.dc('up', '-d', patroni_name)
