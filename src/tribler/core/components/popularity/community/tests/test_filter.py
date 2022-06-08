import os
import random
from typing import List

from ipv8.keyvault.crypto import default_eccrypto
from ipv8.peer import Peer
from tribler.core.components.popularity.community.filter import PerPeerFilter


def get_random_peers(count=1):
    peers: list[Peer] = []
    for _ in range(count):
        test_key = default_eccrypto.generate_key(u"very-low")
        random_ip = ".".join(map(str, (random.randint(0, 255) for _ in range(4))))
        random_port = random.randint(1024, 65535)
        peer = Peer(test_key, (random_ip, random_port))
        peers.append(peer)
    return peers


def generate_items(count=1):
    return [os.urandom(8) for _ in range(count)]


def test_add_item_to_filter():
    filter = PerPeerFilter()
    peer = get_random_peers()[0]

    items = generate_items(10)
    filter.add(peer, items)

    for item in items:
        filter.item_exists(peer, item)


def test_filter_items():
    filter = PerPeerFilter()
    peer = get_random_peers()[0]

    item_set1 = generate_items(10)
    item_set2 = generate_items(10)

    # Add item set 1 but not set 2 to test filtering
    filter.add(peer, item_set1)

    # Since item set 1 is added, filtering the same should not return any items.
    filtered_items = filter.filter(peer, item_set1)
    assert len(filtered_items) == 0

    # Since item set 2 is not added, all the items should be returned unfiltered.
    filtered_items = filter.filter(peer, item_set2)
    assert len(filtered_items) == len(item_set2)


def test_prune_peers():
    filter = PerPeerFilter()
    num_peers = 10
    peers = get_random_peers(num_peers)
    for peer_index in range(num_peers):
        filter.add(peers[peer_index], generate_items(1))
    assert filter.num_peers() == len(peers)

    # Assuming first half peers are disconnected and needs to be pruned
    current_peers = peers[5:]
    filter.prune(current_peers)

    assert filter.num_peers() == len(current_peers)
