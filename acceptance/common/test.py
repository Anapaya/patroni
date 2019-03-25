import logging
import json
import sys
import time
from typing import Tuple

from plumbum import cli
from plumbum import local
from plumbum.cmd import (
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

    def leader_name(self):
        _, li = self.leader_info()
        return self._leader_name(li)

    def _leader_name(self, li) -> str:
        return str(li['Value'], 'utf8') if li and 'Value' in li else ''

    def psql(self, query: str, host: str) -> str:
        res = self.dc('exec', '-T', 'psql', 'psql', '-t', '-c', query, self.postgres_url(host))
        return res.strip()

    def test_write_to(self, host: str, val: int):
        logger.info("Test %s is writable", host)
        query = 'INSERT INTO test (val) VALUES (%s);' % val
        self.psql(query, host)

    def test_read_from(self, host: str, expected: str):
        logger.info("Test %s sees data", host)
        query = 'SELECT MAX(val) FROM test;'
        result = ''
        for _ in range(0, 5):
            try:
                result = self.psql(query, host)
                break
            except ProcessExecutionError:
                time.sleep(0.5)
                pass
        if result != expected:
            logger.error("Wrong result: %s, expected %s", result, expected)
            sys.exit(1)

    def test_not_writable(self, host: str):
        logger.info("Test %s is not writable", host)
        query = 'INSERT INTO test (val) VALUES (2);'
        self.dc('exec', '-T', 'psql', 'psql', '-q', '-c', query, self.postgres_url(host), retcode=1)

    def leader_info(self, index: int = 0) -> Tuple[int, str]:
        return self.consul1.kv.get('service/ptest/leader', index=index)

    def wait_for_leader(self, index: int) -> str:
        index, li = self.leader_info(index)
        ln = self._leader_name(li)
        for _ in range(0, 20):
            if ln:
                logger.info("Found leader: %s", ln)
                return ln
            time.sleep(1)
            index, li = self.leader_info(index)
            ln = self._leader_name(li)
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
