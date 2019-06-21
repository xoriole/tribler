import base64
import glob
from Tribler.pyipv8.ipv8 import overlay
from binascii import unhexlify

from Tribler.pyipv8.ipv8.keyvault.crypto import default_eccrypto

PREFIX = "Version-"
print glob.glob("*.txt")

with open("%s%s" % (PREFIX, "fingerprint.txt"), "wb") as outfile:
    for filename in sorted(glob.glob("*.txt")):
        # print filename
        if not filename.startswith(PREFIX):
            with open(filename, "r") as infile:
                for line in infile:
                    splits = line.split(":")
                    master_peer = splits[1].strip()
                    print "%s:%s:%s" % (splits[0], master_peer, len(master_peer))
                    if len(master_peer) == 40:
                        community_id = base64.b64encode(unhexlify(master_peer))
                    else:
                        community_id = base64.b64encode(default_eccrypto.key_from_public_bin(unhexlify(master_peer)).key_to_hash())
                    outfile.write("%s:%s:%s\n" % (filename[:-4], splits[0], community_id))
