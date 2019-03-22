from contextlib import redirect_stderr
import sys

from plumbum.cmd import (
    docker,
    docker_compose,
    mkdir,
)
from plumbum import local


def container_ip(container_name: str) -> str:
    """Returns the ip of the given container"""
    return docker('inspect', '-f', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',
                  container_name).rstrip()


class DC(object):
    def __init__(self, base_dir: str, compose_file: str = 'acceptance/common/patroni-dc.yml'):
        self.base_dir = base_dir
        self.compose_file = compose_file

    def __call__(self, *args, **kwargs) -> str:
        """Runs docker compose with the given arguments"""
        with local.env(BASE_DIR=self.base_dir, COMPOSE_FILE=self.compose_file):
            with redirect_stderr(sys.stdout):
                return docker_compose('-p', 'acceptance_patroni', '--no-ansi', *args, **kwargs)

    def collect_logs(self, out_dir: str = 'logs/docker'):
        """Collects the logs from the services into the given directory"""
        out_p = local.path(out_dir)
        mkdir('-p', out_p)
        for svc in self('config', '--services').splitlines():
            dst_f = out_p / '%s.log' % svc
            with open(dst_f, 'w') as log_f:
                log_f.write(self('logs', svc))
