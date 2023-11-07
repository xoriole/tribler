import math
from typing import List, Tuple

import libtorrent as lt


def compose_dht_get_peers_payload(transaction_id: bytes, infohash: bytes):
    target = infohash
    request = {
        't': transaction_id,
        'y': b'q',
        'q': b'get_peers',
        'a': {
            'id': infohash,
            'info_hash': target,
            'noseed': 1,
            'scrape': 1
        }
    }
    payload = lt.bencode(request)
    return payload


def decode_nodes(nodes: bytes) -> List[Tuple[str, str, int]]:
    decoded_nodes = []
    for i in range(0, len(nodes), 26):
        node_id = nodes[i:i + 20].hex()
        ip_bytes = nodes[i + 20:i + 24]
        ip_addr = '.'.join(str(byte) for byte in ip_bytes)
        port = int.from_bytes(nodes[i + 24:i + 26], byteorder='big')
        decoded_nodes.append((node_id, ip_addr, port))
    return decoded_nodes


def combine_bloomfilters(bf1, bf2):
    """
    Combine two given bloom filters by ORing the bits.
    :param bf1: The first bloom filter to combine.
    :param bf2: The second bloom filter to combine.
    :return: A bytearray with the combined bloomfilter.
    """
    final_bf_len = min(len(bf1), len(bf2))
    final_bf = bytearray(final_bf_len)
    for bf_index in range(final_bf_len):
        final_bf[bf_index] = bf1[bf_index] | bf2[bf_index]
    return final_bf


def get_size_from_bloomfilter(bf):
    """
    Return the estimated number of items in the bloom filter.
    :param bf: The bloom filter of which we estimate the size.
    :return: A rounded integer, approximating the number of items in the filter.
    """

    def tobits(s):
        result = []
        for c in s:
            num = ord(c) if isinstance(c, str) else c
            bits = bin(num)[2:]
            bits = '00000000'[len(bits):] + bits
            result.extend([int(b) for b in bits])
        return result

    bits_array = tobits(bytes(bf))
    total_zeros = 0
    for bit in bits_array:
        if bit == 0:
            total_zeros += 1

    if total_zeros == 0:
        return 6000  # The maximum capacity of the bloom filter used in BEP33

    m = 256 * 8
    c = min(m - 1, total_zeros)
    return int(math.log(c / float(m)) / (2 * math.log(1 - 1 / float(m))))
