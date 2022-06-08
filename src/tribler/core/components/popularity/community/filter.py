from typing import Any

from cuckoo.filter import ScalableCuckooFilter

# Filter parameters
FILTER_CAPACITY = 1000
FILTER_ERROR_RATE = 0.00001
FILTER_BUCKET_SIZE = 6


class PerPeerFilter:
    """
    PerPeerFilter maintains a dictionary of scalable cuckoo filter per peer. This cuckoo filter can be used to store
    membership data eg. infohash of torrents. This filter reduces the need for storing every single data item while
    checking if a certain item already exists.

    Check out:
    - https://www.cs.cmu.edu/~dga/papers/cuckoo-conext2014.pdf
    - https://pypi.org/project/scalable-cuckoo-filter/
    """
    def __init__(self):
        self.filters = {}

    def _new_filter(self):
        return ScalableCuckooFilter(initial_capacity=FILTER_CAPACITY,
                                    error_rate=FILTER_ERROR_RATE,
                                    bucket_size=FILTER_BUCKET_SIZE)

    def add(self, peer, items: Any):
        """
        Adds a list of items to the cuckoo filter of the peer.
        """
        filter = self.filters.get(peer.mid, self._new_filter())

        items = items if isinstance(items, list) else [items]
        for item in items:
            item_key = self.get_item_key(item)
            if not filter.contains(item_key):
                filter.insert(item_key)

        self.filters[peer.mid] = filter

    def item_exists(self, peer, key):
        """
        Checks if the key exists in the filter associated with the peer.
        """
        filter = self.filters.get(peer.mid, None)
        return filter and filter.contains(key)

    def get_item_key(self, item: Any):
        """
        Returns the key derived from the item that will be used in the cuckoo filter.
        """
        return item

    def filter(self, peer, items: list):
        """
        Returns items that are not present in the filter.
        """
        filter = self.filters.get(peer.mid, None)
        if not filter:
            return items

        return [item for item in items if not filter.contains(self.get_item_key(item))]

    def prune(self, peers):
        """
        Prune filters associated with peers that are not present anymore.
        """
        peer_mids = [peer.mid for peer in peers]
        for key in list(self.filters):
            if key not in peer_mids:
                self.filters.pop(key, None)

    def num_peers(self):
        """
        Returns the number of peers in the filter.
        """
        return len(self.filters)

    def peer_exists(self, peer):
        """
        Checks if the given peer exists in the filter.
        """
        return peer.mid in self.filters


class PerPeerTorrentFilter(PerPeerFilter):
    """
    PerPeerTorrentFilter is a specific peer filter that maintains the filter for torrent health data
    received from popularity community. The key used in this filter is infohash of the torrent.
    """

    def get_item_key(self, item: Any):
        infohash, seeders, leechers, last_check = item
        return infohash
