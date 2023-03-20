import asyncio
import datetime
import random
from binascii import unhexlify
from typing import List, Tuple

import libtorrent as lt

from aioudp import UDPServer

from scripts.dht.dht_manager import DHTHealthManager
from tribler.core.utilities.unicode import hexlify
from tribler.core.utilities.utilities import bdecode_compat


class MyUDPServer:
    def __init__(self, server, loop):
        self.server = server
        self.loop = loop
        # Subscribe for incoming udp packet event
        self.server.subscribe(self.on_datagram_received)
        asyncio.ensure_future(self.do_send(), loop=self.loop)
        self.tid_to_infohash = dict()
        self.infohash_to_tid = dict()
        self.infohash_to_nodes = dict()
        self.dht_health_manager = DHTHealthManager()

    def decode_nodes(self, nodes: bytes) -> List[Tuple[str, str]]:
        decoded_nodes = []
        for i in range(0, len(nodes), 26):
            node_id = nodes[i:i + 20].hex()
            ip_bytes = nodes[i + 20:i + 24]
            ip_addr = '.'.join(str(byte) for byte in ip_bytes)
            port = int.from_bytes(nodes[i + 24:i + 26], byteorder='big')
            decoded_nodes.append((node_id, f'{ip_addr}:{port}'))
        return decoded_nodes

    async def on_datagram_received(self, data, addr):
        # Override virtual method and process incoming data
        # print("\n", datetime.datetime.now(), addr, data)
        # print(f"received data here: {data}")

        decoded = bdecode_compat(data)
        if not decoded:
            return

        # print(f"decoded: {decoded}")

        # We are sending a raw DHT message - notify the DHTHealthManager of the outstanding request.
        if decoded.get(b'y') == b'q' \
                and decoded.get(b'q') == b'get_peers' and decoded[b'a'].get(b'scrape') == 1:
            print(f"got sent dht request")
            # self.dht_health_manager.requesting_bloomfilters(decoded[b't'],
            #                                                 decoded[b'a'][b'info_hash'])

        if b'r' in decoded:
            tid = decoded[b't']
            infohash = self.tid_to_infohash.get(tid, None)
            if not infohash:
                # print(f"received dht response for non-existing infohash; skipping...")
                return

            if b'nodes' in decoded[b'r']:
                b_nodes = decoded[b'r'][b'nodes']
                decoded_nodes = self.decode_nodes(b_nodes)
                # print(decoded_nodes)
                for (_node_id, ip_port_str) in decoded_nodes:
                    ip_port_split = ip_port_str.split(":")
                    port = int(ip_port_split[1])

                    sent_nodes = self.infohash_to_nodes.get(infohash, [])
                    if ip_port_str not in sent_nodes or len(sent_nodes) < 10:
                        # send request to node
                        payload = self.compose_dht_get_peers_request(infohash, add=True)
                        node_tuple = (ip_port_split[0], port)
                        await self.send_dht_get_peers_request(node_tuple, payload)
                        # self.dht_health_manager.requesting_bloomfilters(decoded[b't'],
                        #                                                 decoded[b'a'][b'info_hash'])
                        sent_nodes.append(ip_port_str)
                        self.infohash_to_nodes[infohash] = sent_nodes

            # We received a raw DHT message - decode it and check whether it is a BEP33 message.
            if b'BFsd' in decoded[b'r'] and b'BFpe' in decoded[b'r']:
                print(f">> got dht response with BFsd:{decoded[b'r'][b'BFsd']} and BFpe:{decoded[b'r'][b'BFpe']}")
                self.dht_health_manager.received_bloomfilters(decoded[b't'],
                                                              bytearray(decoded[b'r'][b'BFsd']),
                                                              bytearray(decoded[b'r'][b'BFpe']))

            b_values = decoded[b'r'].get(b'values', [])
            if b_values:
                # print(f">> got dht peers: {decoded[b'r'][b'values']}")
                for b_value in b_values:
                    ip_bytes = b_value[:4]
                    ip_addr = '.'.join(str(byte) for byte in ip_bytes)
                    port = int.from_bytes(b_value[4:], byteorder='big')
                    # print(f"peer: {ip_addr}:{port}")

    def compose_dht_get_peers_request(self, infohash, target=None, add=False):
        tid = self.tid_to_infohash.get(infohash, None)
        if not tid:
            tid = random.randint(1, 256).to_bytes(2, 'big')
            self.tid_to_infohash[tid] = infohash
            self.infohash_to_tid[infohash] = tid

        target = bytes.fromhex(infohash)
        request = {
            't': tid,
            'y': b'q',
            'q': b'get_peers',
            'a': {
                'id': bytes.fromhex(infohash),
                'info_hash': target,
                'noseed': 1,
                'scrape': 1
            }
        }
        payload = lt.bencode(request)
        if add:
            self.dht_health_manager.requesting_bloomfilters(request['t'],
                                                            request['a']['info_hash'])
        return payload

    async def send_dht_get_peers_request(self, node_ip_port_tuple, payload):
        await asyncio.sleep(0.001)
        # Enqueue data for send
        self.server.send(payload, node_ip_port_tuple)


    async def do_send(self):
        while True:
            # Any payload
            # payload = b'd1:ad2:id20:k\xe7\x90\xcd\x0c_R\xfe\x82\xeb\xa8 x\x14\xb4-\x8e0\xe5\x086:target20:\x11\x8e\xcc,\x89\xa4\x99\xf98E\x98\x7f!\xa7w\rz\x1b\x14de1:q9:find_node1:t2:#K1:y1:qe'
            # infohash = "f07e0b0584745b7bcb35e98097488d34e68623d0"
            infohash = "2c6b6858d61da9543d4231a71db4b1c9264b0685"
            # payload = b'd1:ad2:id20:f07e0b0584745b7bcb35e98097488d34e68623d0:find1:t2:aa1:y1:qe'
            #
            tid = 1
            #
            # target = bytes.fromhex(infohash)
            # request = {
            #     't': tid.to_bytes(2, 'big'),
            #     'y': b'q',
            #     'q': b'find_node',
            #     'a': {
            #         'id': bytes.fromhex(infohash),
            #         'target': target
            #     }
            # }
            # payload = lt.bencode(request)

            self.dht_health_manager.register_health_request(bytes.fromhex(infohash))

            payload = self.compose_dht_get_peers_request(infohash)

            # Delay for prevent tasks concurency
            await asyncio.sleep(0.001)

            # Enqueue data for send
            router_ip_port_tuple = ("router.bittorrent.com", 6881)
            await self.send_dht_get_peers_request(router_ip_port_tuple, payload)
            # self.dht_health_manager.requesting_bloomfilters(decoded[b't'],
            #                                                 decoded[b'a'][b'info_hash'])

            # self.server.send(payload, ("router.bittorrent.com", 6881))

            # self.dht_health_manager.register_task(f"lookup_{infohash}", self.finalize_lookup, infohash, delay=15)
            break

    def finalize_lookup(self, infohash):
        """
        Finalize the lookup of the provided infohash and invoke the appropriate deferred.
        :param infohash: The infohash of the lookup we finialize.
        """
        # health = self.dht_health_manager.finalize_lookup(unhexlify(infohash))
        health = self.dht_health_manager.health_result.get(unhexlify(infohash), None)
        print(f"bep33 health info: {health}")
        if not health:
            print(f"all healths: {self.dht_health_manager.health_result}")

async def main(loop):
    # Bandwidth speed is 100 bytes per second
    udp = UDPServer()
    udp.run("0.0.0.0", 12346, loop=loop)

    server = MyUDPServer(server=udp, loop=loop)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(loop))
    loop.run_forever()