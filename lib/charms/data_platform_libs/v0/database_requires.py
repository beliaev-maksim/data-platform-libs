# Copyright 2022 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Relation 'requires' side abstraction for database relation.

This library is a uniform interface to a selection of common database
metadata, with added custom events that add convenience to database management,
and methods to consume the application related data.

Following an example of using the DatabaseCreatedEvent, in the context of the
application charm code:

```python

from charms.data_platform_libs.v0.database_requires import (
    DatabaseCreatedEvent,
    DatabaseRequires,
)

class ApplicationCharm(CharmBase):
    # Application charm that connects to database charms.

    def __init__(self, *args):
        super().__init__(*args)

        # Charm events defined in the database requires charm library.
        self.database = DatabaseRequires(self, relation_name="database", database_name="database")
        self.framework.observe(self.database.on.database_created, self._on_database_created)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        # Handle the created database

        # Create configuration file for app
        config_file = self._render_app_config_file(
            event.username,
            event.password,
            event.endpoints,
        )

        # Start application with rendered configuration
        self._start_application(config_file)

        # Set active status
        self.unit.status = ActiveStatus("received database credentials")
```

As shown above, the library provides some custom events to handle specific situations,
which are listed below:

— database_created: event emitted when the requested database is created.
— endpoints_changed: event emitted when the read/write endpoints of the database have changed.
— read_only_endpoints_changed: event emitted when the read-only endpoints of the database
  have changed. Event is not triggered if read/write endpoints changed too.

If it is needed to connect multiple database clusters to the same relation endpoint
the application charm can implement the same code as if it would connect to only
one database cluster (like the above code example).

To differentiate multiple clusters connected to the same relation endpoint
the application charm can use the name of the remote application:

```python

def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
    # Get the remote app name of the cluster that triggered this event
    cluster = event.relation.app.name
```

It is also possible to provide an alias for each different database cluster/relation.

So, it is possible to differentiate the clusters in two ways.
The first is to use the remote application name, i.e., `event.relation.app.name`, as above.

The second way is to use different event handlers to handle each cluster events.
The implementation would be something like the following code:

```python

from charms.data_platform_libs.v0.database_requires import (
    DatabaseCreatedEvent,
    DatabaseRequires,
)

class ApplicationCharm(CharmBase):
    # Application charm that connects to database charms.

    def __init__(self, *args):
        super().__init__(*args)

        # Define the cluster aliases and one handler for each cluster database created event.
        self.database = DatabaseRequires(
            self,
            relation_name="database",
            database_name="database",
            relations_aliases = ["cluster1", "cluster2"],
        )
        self.framework.observe(
            self.database.on.cluster1_database_created, self._on_cluster1_database_created
        )
        self.framework.observe(
            self.database.on.cluster2_database_created, self._on_cluster2_database_created
        )

    def _on_cluster1_database_created(self, event: DatabaseCreatedEvent) -> None:
        # Handle the created database on the cluster named cluster1

        # Create configuration file for app
        config_file = self._render_app_config_file(
            event.username,
            event.password,
            event.endpoints,
        )
        ...

    def _on_cluster2_database_created(self, event: DatabaseCreatedEvent) -> None:
        # Handle the created database on the cluster named cluster2

        # Create configuration file for app
        config_file = self._render_app_config_file(
            event.username,
            event.password,
            event.endpoints,
        )
        ...

```
"""

import json
import logging
from abc import ABC, ABCMeta, abstractmethod
from collections import namedtuple
from datetime import datetime
from typing import List, Optional

from ops.charm import (
    CharmEvents,
    RelationChangedEvent,
    RelationEvent,
    RelationJoinedEvent,
)
from ops.framework import EventSource, Object, _Metaclass
from ops.model import Relation

# The unique Charmhub library identifier, never change it
LIBID = "0241e088ffa9440fb4e3126349b2fb62"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version.
LIBPATCH = 4

logger = logging.getLogger(__name__)


class BaseEvent(RelationEvent):
    """Base class for events."""

    @property
    def username(self) -> Optional[str]:
        """Returns the created username."""
        return self.relation.data[self.relation.app].get("username")

    @property
    def password(self) -> Optional[str]:
        """Returns the password for the created user."""
        return self.relation.data[self.relation.app].get("password")

    @property
    def tls(self) -> Optional[str]:
        """Returns whether TLS is configured."""
        return self.relation.data[self.relation.app].get("tls")

    @property
    def tls_ca(self) -> Optional[str]:
        """Returns TLS CA."""
        return self.relation.data[self.relation.app].get("tls-ca")


# Database events


class DatabaseEvent(RelationEvent):
    """Base class for database events."""

    @property
    def endpoints(self) -> Optional[str]:
        """Returns a comma separated list of read/write endpoints."""
        return self.relation.data[self.relation.app].get("endpoints")

    @property
    def read_only_endpoints(self) -> Optional[str]:
        """Returns a comma separated list of read only endpoints."""
        return self.relation.data[self.relation.app].get("read-only-endpoints")

    @property
    def replset(self) -> Optional[str]:
        """Returns the replicaset name.

        MongoDB only.
        """
        return self.relation.data[self.relation.app].get("replset")

    @property
    def uris(self) -> Optional[str]:
        """Returns the connection URIs.

        MongoDB, Redis, OpenSearch.
        """
        return self.relation.data[self.relation.app].get("uris")

    @property
    def version(self) -> Optional[str]:
        """Returns the version of the database.

        Version as informed by the database daemon.
        """
        return self.relation.data[self.relation.app].get("version")


class DatabaseCreatedEvent(BaseEvent, DatabaseEvent):
    """Event emitted when a new database is created for use on this relation."""


class DatabaseEndpointsChangedEvent(BaseEvent, DatabaseEvent):
    """Event emitted when the read/write endpoints are changed."""


class DatabaseReadOnlyEndpointsChangedEvent(BaseEvent, DatabaseEvent):
    """Event emitted when the read only endpoints are changed."""


class DatabaseEvents(CharmEvents):
    """Database events.

    This class defines the events that the database can emit.
    """

    database_created = EventSource(DatabaseCreatedEvent)
    endpoints_changed = EventSource(DatabaseEndpointsChangedEvent)
    read_only_endpoints_changed = EventSource(DatabaseReadOnlyEndpointsChangedEvent)


# Kafka events


class KafkaEvent(RelationEvent):
    """Base class for Kafka events."""

    @property
    def bootstrap_server(self) -> Optional[str]:
        """Returns a a comma-seperated list of broker uris."""
        return self.relation.data[self.relation.app].get("endpoints")

    @property
    def consumer_group_prefix(self) -> Optional[str]:
        """Returns the consumer-group-prefix."""
        return self.relation.data[self.relation.app].get("consumer-group-prefix")

    @property
    def zookeeper_uris(self) -> Optional[str]:
        """Returns a comma separated list of Zookeeper uris."""
        return self.relation.data[self.relation.app].get("zookeeper-uris")


class TopicCreatedEvent(BaseEvent, KafkaEvent):
    """Event emitted when a new topic is created for use on this relation."""


class BootstrapServerChangedEvent(BaseEvent, KafkaEvent):
    """Event emitted when the bootstrap server is changed."""


class KakfaCredentialsChangedEvent(BaseEvent, KafkaEvent):
    """Event emitted when the Kafka credentials(username or password) are changed."""


class KafkaEvents(CharmEvents):
    """Kafka events.

    This class defines the events that the Kafka can emit.
    """

    topic_created = EventSource(TopicCreatedEvent)
    bootstrap_server_changed = EventSource(BootstrapServerChangedEvent)
    credentials_changed = EventSource(KakfaCredentialsChangedEvent)


# Zookeeper events


class ZookeeperEvent(RelationEvent):
    """Base class for Zookeeper events."""

    @property
    def endpoints(self) -> Optional[str]:
        """Returns a comma separated list of read/write endpoints."""
        return self.relation.data[self.relation.app].get("endpoints")


class ChrootCreatedEvent(BaseEvent, ZookeeperEvent):
    """Event emitted when a new chroot is created for use on this relation."""


class ZookeeperEndpointsChangedEvent(BaseEvent, ZookeeperEvent):
    """Event emitted when the endpoints are changed."""


class ZookeeperCredentialsChangedEvent(BaseEvent, ZookeeperEvent):
    """Event emitted when the Kafka credentials(username or password) are changed."""


class ZookeeperEvents(CharmEvents):
    """Zookeeper events.

    This class defines the events that the Zookeeper can emit.
    """

    chroot_created = EventSource(ChrootCreatedEvent)
    endpoints_changed = EventSource(ZookeeperEndpointsChangedEvent)
    credentials_changed = EventSource(ZookeeperCredentialsChangedEvent)


Diff = namedtuple("Diff", "added changed deleted")
Diff.__doc__ = """
A tuple for storing the diff between two data mappings.

— added — keys that were added.
— changed — keys that still exist but have new values.
— deleted — keys that were deleted.
"""


class _AbstractMetaclass(ABCMeta, _Metaclass):
    pass


class BaseRequires(Object, ABC, metaclass=_AbstractMetaclass):
    """Requires-side of the database relation."""

    def __init__(
        self,
        charm,
        relation_name: str,
        extra_user_roles: str = None,
    ):
        """Manager of base client relations."""
        super().__init__(charm, relation_name)
        self.charm = charm
        self.extra_user_roles = extra_user_roles
        self.local_app = self.charm.model.app
        self.local_unit = self.charm.unit
        self.relation_name = relation_name
        self.framework.observe(
            self.charm.on[relation_name].relation_joined, self._on_relation_joined_event
        )
        self.framework.observe(
            self.charm.on[relation_name].relation_changed, self._on_relation_changed_event
        )

    @abstractmethod
    def _on_relation_joined_event(self, event: RelationJoinedEvent) -> None:
        """Event emitted when the application joins the database relation."""
        raise NotImplementedError

    @abstractmethod
    def _on_relation_changed_event(self, event: RelationChangedEvent) -> None:
        raise NotImplementedError

    def fetch_relation_data(self) -> dict:
        """Retrieves data from relation.

        This function can be used to retrieve data from a relation
        in the charm code when outside an event callback.

        Returns:
            a dict of the values stored in the relation data bag
                for all relation instances (indexed by the relation ID).
        """
        data = {}
        for relation in self.relations:
            data[relation.id] = {
                key: value for key, value in relation.data[relation.app].items() if key != "data"
            }
        return data

    def _update_relation_data(self, relation_id: int, data: dict) -> None:
        """Updates a set of key-value pairs in the relation.

        This function writes in the application data bag, therefore,
        only the leader unit can call it.

        Args:
            relation_id: the identifier for a particular relation.
            data: dict containing the key-value pairs
                that should be updated in the relation.
        """
        if self.local_unit.is_leader():
            relation = self.charm.model.get_relation(self.relation_name, relation_id)
            relation.data[self.local_app].update(data)

    def _diff(self, event: RelationChangedEvent) -> Diff:
        """Retrieves the diff of the data in the relation changed databag.

        Args:
            event: relation changed event.

        Returns:
            a Diff instance containing the added, deleted and changed
                keys from the event relation databag.
        """
        # Retrieve the old data from the data key in the local unit relation databag.
        old_data = json.loads(event.relation.data[self.local_unit].get("data", "{}"))
        # Retrieve the new data from the event relation databag.
        new_data = {
            key: value for key, value in event.relation.data[event.app].items() if key != "data"
        }

        # These are the keys that were added to the databag and triggered this event.
        added = new_data.keys() - old_data.keys()
        # These are the keys that were removed from the databag and triggered this event.
        deleted = old_data.keys() - new_data.keys()
        # These are the keys that already existed in the databag,
        # but had their values changed.
        changed = {
            key for key in old_data.keys() & new_data.keys() if old_data[key] != new_data[key]
        }

        # TODO: evaluate the possibility of losing the diff if some error
        # happens in the charm before the diff is completely checked (DPE-412).
        # Convert the new_data to a serializable format and save it for a next diff check.
        event.relation.data[self.local_unit].update({"data": json.dumps(new_data)})

        # Return the diff with all possible changes.
        return Diff(added, changed, deleted)

    @property
    def relations(self) -> List[Relation]:
        """The list of Relation instances associated with this relation_name."""
        return list(self.charm.model.relations[self.relation_name])


# Database Requires


class DatabaseRequires(BaseRequires):
    """Requires-side of the database relation."""

    on = DatabaseEvents()

    def __init__(
        self,
        charm,
        relation_name: str,
        database_name: str,
        extra_user_roles: str = None,
        relations_aliases: List[str] = None,
    ):
        """Manager of database client relations."""
        super().__init__(charm, relation_name, extra_user_roles)
        self.database = database_name
        self.relations_aliases = relations_aliases

        # Define custom event names for each alias.
        if relations_aliases:
            # Ensure the number of aliases does not exceed the maximum
            # of connections allowed in the specific relation.
            relation_connection_limit = self.charm.meta.requires[relation_name].limit
            if len(relations_aliases) != relation_connection_limit:
                raise ValueError(
                    f"The number of aliases must match the maximum number of connections allowed in the relation. "
                    f"Expected {relation_connection_limit}, got {len(relations_aliases)}"
                )

            for relation_alias in relations_aliases:
                self.on.define_event(f"{relation_alias}_database_created", DatabaseCreatedEvent)
                self.on.define_event(
                    f"{relation_alias}_endpoints_changed", DatabaseEndpointsChangedEvent
                )
                self.on.define_event(
                    f"{relation_alias}_read_only_endpoints_changed",
                    DatabaseReadOnlyEndpointsChangedEvent,
                )

    def _assign_relation_alias(self, relation_id: int) -> None:
        """Assigns an alias to a relation.

        This function writes in the unit data bag.

        Args:
            relation_id: the identifier for a particular relation.
        """
        # If no aliases were provided, return immediately.
        if not self.relations_aliases:
            return

        # Return if an alias was already assigned to this relation
        # (like when there are more than one unit joining the relation).
        if (
            self.charm.model.get_relation(self.relation_name, relation_id)
            .data[self.local_unit]
            .get("alias")
        ):
            return

        # Retrieve the available aliases (the ones that weren't assigned to any relation).
        available_aliases = self.relations_aliases[:]
        for relation in self.charm.model.relations[self.relation_name]:
            alias = relation.data[self.local_unit].get("alias")
            if alias:
                logger.debug("Alias %s was already assigned to relation %d", alias, relation.id)
                available_aliases.remove(alias)

        # Set the alias in the unit relation databag of the specific relation.
        relation = self.charm.model.get_relation(self.relation_name, relation_id)
        relation.data[self.local_unit].update({"alias": available_aliases[0]})

    def _emit_aliased_event(self, event: RelationChangedEvent, event_name: str) -> None:
        """Emit an aliased event to a particular relation if it has an alias.

        Args:
            event: the relation changed event that was received.
            event_name: the name of the event to emit.
        """
        alias = self._get_relation_alias(event.relation.id)
        if alias:
            getattr(self.on, f"{alias}_{event_name}").emit(
                event.relation, app=event.app, unit=event.unit
            )

    def _get_relation_alias(self, relation_id: int) -> Optional[str]:
        """Returns the relation alias.

        Args:
            relation_id: the identifier for a particular relation.

        Returns:
            the relation alias or None if the relation was not found.
        """
        for relation in self.charm.model.relations[self.relation_name]:
            if relation.id == relation_id:
                return relation.data[self.local_unit].get("alias")
        return None

    def _on_relation_joined_event(self, event: RelationJoinedEvent) -> None:
        """Event emitted when the application joins the database relation."""
        # If relations aliases were provided, assign one to the relation.
        self._assign_relation_alias(event.relation.id)

        # Sets both database and extra user roles in the relation
        # if the roles are provided. Otherwise, sets only the database.
        if self.extra_user_roles:
            self._update_relation_data(
                event.relation.id,
                {
                    "database": self.database,
                    "extra-user-roles": self.extra_user_roles,
                },
            )
        else:
            self._update_relation_data(event.relation.id, {"database": self.database})

    def _on_relation_changed_event(self, event: RelationChangedEvent) -> None:
        """Event emitted when the database relation has changed."""
        # Check which data has changed to emit customs events.
        diff = self._diff(event)

        # Check if the database is created
        # (the database charm shared the credentials).
        if "username" in diff.added and "password" in diff.added:
            # Emit the default event (the one without an alias).
            logger.info("database created at %s", datetime.now())
            self.on.database_created.emit(event.relation, app=event.app, unit=event.unit)

            # Emit the aliased event (if any).
            self._emit_aliased_event(event, "database_created")

            # To avoid unnecessary application restarts do not trigger
            # “endpoints_changed“ event if “database_created“ is triggered.
            return

        # Emit an endpoints changed event if the database
        # added or changed this info in the relation databag.
        if "endpoints" in diff.added or "endpoints" in diff.changed:
            # Emit the default event (the one without an alias).
            logger.info("endpoints changed on %s", datetime.now())
            self.on.endpoints_changed.emit(event.relation, app=event.app, unit=event.unit)

            # Emit the aliased event (if any).
            self._emit_aliased_event(event, "endpoints_changed")

            # To avoid unnecessary application restarts do not trigger
            # “read_only_endpoints_changed“ event if “endpoints_changed“ is triggered.
            return

        # Emit a read only endpoints changed event if the database
        # added or changed this info in the relation databag.
        if "read-only-endpoints" in diff.added or "read-only-endpoints" in diff.changed:
            # Emit the default event (the one without an alias).
            logger.info("read-only-endpoints changed on %s", datetime.now())
            self.on.read_only_endpoints_changed.emit(
                event.relation, app=event.app, unit=event.unit
            )

            # Emit the aliased event (if any).
            self._emit_aliased_event(event, "read_only_endpoints_changed")


class KafkaRequires(BaseRequires):
    """Requires-side of the Kafka relation."""

    on = KafkaEvents()

    def __init__(self, charm, relation_name: str, topic: str, extra_user_roles: str = None):
        """Manager of Kafka client relations."""
        # super().__init__(charm, relation_name)
        super().__init__(charm, relation_name, extra_user_roles)
        self.charm = charm
        self.topic = topic

    def _on_relation_joined_event(self, event: RelationJoinedEvent) -> None:
        """Event emitted when the application joins the Kafka relation."""
        # Sets both topic and extra user roles in the relation
        # if the roles are provided. Otherwise, sets only the topic.
        self._update_relation_data(
            event.relation.id,
            {
                "topic": self.topic,
                "extra-user-roles": self.extra_user_roles,
            }
            if self.extra_user_roles is not None
            else {"topic": self.topic},
        )

    def _on_relation_changed_event(self, event: RelationChangedEvent) -> None:
        """Event emitted when the Kafka relation has changed."""
        # Check which data has changed to emit customs events.
        diff = self._diff(event)

        # Check if the topic is created
        # (the Kafka charm shared the credentials).
        if "username" in diff.added and "password" in diff.added:
            # Emit the default event (the one without an alias).
            logger.info("topic created at %s", datetime.now())
            self.on.topic_created.emit(event.relation, app=event.app, unit=event.unit)

            # To avoid unnecessary application restarts do not trigger
            # “endpoints_changed“ event if “topic_created“ is triggered.
            return

        # Emit an endpoints (bootstap-server) changed event if the Kakfa endpoints
        # added or changed this info in the relation databag.
        if "endpoints" in diff.added or "endpoints" in diff.changed:
            # Emit the default event (the one without an alias).
            logger.info("endpoints changed on %s", datetime.now())
            self.on.bootstrap_server_changed.emit(
                event.relation, app=event.app, unit=event.unit
            )  # here check if this is the right design
            return

        # Emit a read only credential changed event if the kafka credentials
        # changed this info in the relation databag.
        if "username" in diff.changed or "password" in diff.changed:

            logger.info("credential changed on %s", datetime.now())
            self.on.credentials_changed.emit(event.relation, app=event.app, unit=event.unit)
            return


class ZookeeperRequires(BaseRequires):
    """Requires-side of the Kafka relation."""

    on = ZookeeperEvents()

    def __init__(self, charm, relation_name: str, chroot: str, extra_user_roles: str = None):
        """Manager of Kafka client relations."""
        # super().__init__(charm, relation_name)
        super().__init__(charm, relation_name, extra_user_roles)
        self.charm = charm
        self.chroot = chroot

    def _on_relation_joined_event(self, event: RelationJoinedEvent) -> None:
        """Event emitted when the application joins the zookeeper relation."""
        # Sets both Zookeeper and extra user roles in the relation
        # if the roles are provided. Otherwise, sets only the chroot.

        self._update_relation_data(
            event.relation.id,
            {
                "chroot": self.chroot,
                "extra-user-roles": self.extra_user_roles,
            }
            if self.extra_user_roles is not None
            else {"topic": self.chroot},
        )

    def _on_relation_changed_event(self, event: RelationChangedEvent) -> None:
        """Event emitted when the Zookeeper relation has changed."""
        # Check which data has changed to emit customs events.
        diff = self._diff(event)

        # Check if the topic is created
        # (the Zookeeper charm shared the credentials).
        if "username" in diff.added and "password" in diff.added:
            # Emit the default event (the one without an alias).
            logger.info("chroot created at %s", datetime.now())
            self.on.chroot_created.emit(event.relation, app=event.app, unit=event.unit)

            # To avoid unnecessary application restarts do not trigger
            # “endpoints_changed“ event if “chroot_created“ is triggered.
            return

        # Emit an endpoints changed event if the Zookeeper endpoints
        # added or changed this info in the relation databag.
        if "endpoints" in diff.added or "endpoints" in diff.changed:
            # Emit the default event (the one without an alias).
            logger.info("endpoints changed on %s", datetime.now())
            self.on.endpoints_changed.emit(event.relation, app=event.app, unit=event.unit)
            return

        # Emit a read only credential changed event if the Zookeeper credentials
        # changed this info in the relation databag.
        if "username" in diff.changed or "password" in diff.changed:

            logger.info("credential changed on %s", datetime.now())
            self.on.credentials_changed.emit(event.relation, app=event.app, unit=event.unit)
            return
