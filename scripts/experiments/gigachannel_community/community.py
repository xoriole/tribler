import json
import time
from datetime import datetime

from pony.orm import db_session

from ipv8.lazy_community import lazy_wrapper
from scripts.experiments.common.database import get_database
from scripts.experiments.gigachannel_community.entities import define_remote_select_query_entity_binding
from tribler.core.components.gigachannel.community.gigachannel_community import GigaChannelCommunity
from tribler.core.components.metadata_store.remote_query_community.remote_query_community import RemoteSelectPayload


class CustomGigaChannelCommunity(GigaChannelCommunity):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # define bindings for tables and generate the mappings for the tables
        self.db = get_database()
        self.RemoteSelectQueryEntity = define_remote_select_query_entity_binding(self.db)
        self.db.generate_mapping(create_tables=True)

    @lazy_wrapper(RemoteSelectPayload)
    async def on_remote_select(self, peer, request_payload):
        self.logger.info(f"{datetime.now().isoformat()}: peer[{peer.address.ip}:{peer.address.port}] sent query: {request_payload.json}")
        self.logger.info(f"Number of peers: {len(self.get_peers())}")
        query_json = json.loads(request_payload.json)
        if "txt_filter" in query_json:
            received_at = int(time.time())
            with db_session:
                self.RemoteSelectQueryEntity(peer_pk=peer.public_key.key_to_bin(),
                                             peer_ip=peer.address.ip,
                                             peer_port=peer.address.port,
                                             received_at=received_at,
                                             json=query_json)
