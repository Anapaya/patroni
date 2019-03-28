from __future__ import absolute_import
import logging
from functools import wraps

from patroni.dcs import (
    Cluster,
    consul,
    Member,
    Leader,
    SyncState,
    TimelineHistory,
)

logger = logging.getLogger(__name__)

NO_CONSUL_LEADER = "no consul leader"


def log_invocation(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        static_mode = args[0]._static_mode
        logger.info("%s, static: %s", func.__name__, static_mode)
        return func(*args, **kwargs)
    return wrapper


def try_super(func):
    """
    returns True in _static_mode.
    tries to call the super function.
    if there is no consul leader, returns True.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self._static_mode:
            return True
        try:  # Call the super func
            _super = super(type(self), self)
            return getattr(_super, func.__name__)(*args, **kwargs)
        except consul.ConsulNoClusterLeader:
            logger.warning("%s: %s", func.__name__, NO_CONSUL_LEADER)
            return False
    return wrapper


class Consul2Node(consul.Consul):
    """
    Consul2Node is a special consul version that can deal with consul outage in a 2 node setup. If
    the local consul node is down we don't do anything (leadership is dropped since DCS is not
    accessible). If the local consul is still available but responds with "500 no cluster leader"
    assume we are the only running node, thus we get to be leader.
    NOTE: This only works if you connect to the consul servers directly, not via agents.
    NOTE: This obviously only works if you can never have a split brain. Otherwise have fun ;).
    """

    def __init__(self, config):
        self._static_mode = False
        self._static_cluster = None
        config['consul2node'] = True
        super(Consul2Node, self).__init__(config)

    @try_super
    @log_invocation
    def create_session(self):
        pass

    @log_invocation
    def _load_cluster(self):
        # load cluster is called periodically so we always try to get from consul.
        try:
            cluster = super()._load_cluster()
            if cluster:
                was_static = self._static_mode
                self._static_cluster = cluster
                self._static_mode = False
                if was_static:
                    logger.info("consul back online, losing static mode.")
                    self.attempt_to_acquire_leader()
                    # Drop the leader node.
                    c = cluster
                    return Cluster(c.initialize, c.config, None, c.last_leader_operation, c.members,
                                   c.failover, c.sync, c.history)
            return cluster
        except consul.ConsulNoClusterLeader:
            if self._static_mode:
                return self._static_cluster
            # Enable static mode.
            c = self._static_cluster
            # TODO(lukedirtwalker): maybe keep leader if we already were leader?
            self._static_cluster = Cluster(c.initialize, c.config, None,
                                           c.last_leader_operation, c.members, c.failover,
                                           c.sync, c.history)
            self._static_mode = True
            return self._static_cluster

    @try_super
    @log_invocation
    def touch_member(self, data, permanent=False):
        pass

    @try_super
    @log_invocation
    def _do_refresh_session(self):
        pass

    @try_super
    def register_service(self, service_name, **kwargs):
        pass

    @try_super
    @log_invocation
    def deregister_service(self, service_id):
        pass

    @try_super
    @log_invocation
    def _update_service(self, data):
        pass

    @log_invocation
    def _do_attempt_to_acquire_leader(self, permanent):
        if self._static_mode:
            if not self._static_cluster.leader or self._static_cluster.leader.name != self._name:
                c = self._static_cluster
                member = next((m for m in c.members if m.name == self._name),
                              Member(-1, self._name, None, {}))
                leader = Leader(0, self._session, member)
                self._static_cluster = Cluster(c.initialize, c.config, leader,
                                               c.last_leader_operation, c.members, c.failover,
                                               c.sync, c.history)
            return True
        try:
            return super()._do_attempt_to_acquire_leader(permanent)
        except consul.ConsulNoClusterLeader:
            logger.warning("_do_attempt_to_acquire_leader: %s", NO_CONSUL_LEADER)
            return True

    @log_invocation
    def _write_leader_optime(self, last_operation):
        if self._static_mode:
            c = self._static_cluster
            self._static_cluster = Cluster(c.initialize, c.config, c.leader, last_operation,
                                           c.members, c.failover, c.sync, c.history)
            return True
        try:
            return super()._write_leader_optime(last_operation)
        except consul.ConsulNoClusterLeader:
            logger.warning("_write_leader_optime: %s", NO_CONSUL_LEADER)
            return True

    @try_super
    @log_invocation
    def _update_leader(self):
        pass

    @log_invocation
    def set_history_value(self, value):
        if self._static_mode:
            c = self._static_cluster
            hist = TimelineHistory.from_node(-1, value)
            self._static_cluster = Cluster(c.initialize, c.config, c.leader,
                                           c.last_leader_operation, c.members, c.failover, c.sync,
                                           hist)
            return True
        try:
            return super().set_history_value(value)
        except consul.ConsulNoClusterLeader:
            logger.warning("set_history_value: %s", NO_CONSUL_LEADER)
            return True

    @log_invocation
    def set_sync_state_value(self, value, index=None):
        if self._static_mode:
            c = self._static_cluster
            sync = SyncState.from_node(-1, value)
            self._static_cluster = Cluster(c.initialize, c.config, c.leader,
                                           c.last_leader_operation, c.members, c.failover, sync,
                                           c.history)
            return True
        try:
            return super().set_sync_state_value(value, index)
        except consul.ConsulNoClusterLeader:
            logger.warning("set_sync_state_value: %s", NO_CONSUL_LEADER)
            return True

    @try_super
    @log_invocation
    def delete_sync_state(self, index=None):
        pass

    @try_super
    def watch(self, leader_index, timeout):
        pass
