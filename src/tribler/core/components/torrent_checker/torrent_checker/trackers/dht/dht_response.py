import libtorrent

from tribler.core.components.torrent_checker.torrent_checker.trackers.dht import dht_utils


class DhtResponse:

    def __init__(self, byte_response: bytes):
        self.response = byte_response
        self.decoded = libtorrent.bdecode(byte_response)

    def is_valid(self):
        return self.decoded is not None

    def get_peers(self):
        pass

    def is_reply(self):
        return b'r' in self.decoded

    @property
    def transaction_id(self):
        return self.decoded[b't']

    def has_nodes(self):
        return self.decoded.get(b'r', {}).get(b'nodes', None) is not None

    @property
    def nodes(self):
        dht_response = self.decoded[b'r']
        if b'nodes' in dht_response:
            b_nodes = dht_response[b'nodes']
            return dht_utils.decode_nodes(b_nodes)

        return []

    @property
    def bloom_filters(self):
        dht_response = self.decoded[b'r']
        if b'BFsd' in dht_response and b'BFpe' in dht_response:
            return dht_response[b'BFsd'], dht_response[b'BFpe']
        return bytearray(256), bytearray(256)

    def has_bloom_filters(self):
        dht_response = self.decoded[b'r']
        return b'BFsd' in dht_response and b'BFpe' in dht_response
