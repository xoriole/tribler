from pony import orm


def define_torrent_health_binding(db):
    class TorrentHealthEntity(db.Entity):
        rowid = orm.PrimaryKey(int, auto=True)

        peer_pk = orm.Required(bytes, index=True)
        peer_ip = orm.Required(str, index=True)
        peer_port = orm.Required(int, index=True)
        received_at = orm.Optional(int, size=64, default=0, index=True)

        infohash = orm.Required(str, index=True)
        seeders = orm.Optional(int, default=0)
        leechers = orm.Optional(int, default=0)
        last_check = orm.Optional(int, size=64, default=0, index=True)
    return TorrentHealthEntity


def define_peer_binding(db):
    class PeerEntity(db.Entity):
        rowid = orm.PrimaryKey(int, auto=True)
        pk = orm.Required(bytes, unique=True, index=True)
        ip = orm.Required(str, index=True)
        port = orm.Required(int, index=True)

        version = orm.Optional(str, index=True)
        platform = orm.Optional(str, index=True)

        first_known = orm.Required(int, size=64, default=0)
        last_known = orm.Required(int, size=64, default=0)
    return PeerEntity


def define_checked_torrents_binding(db):
    class CheckedTorrentsEntity(db.Entity):
        rowid = orm.PrimaryKey(int, auto=True)
        infohash = orm.Required(str, index=True)
        seeders = orm.Optional(int, default=0)
        leechers = orm.Optional(int, default=0)
        last_checked = orm.Optional(int, size=64, default=0, index=True)
        num_received = orm.Optional(int, size=16, default=0, index=True)

        seeders_by_crawler = orm.Optional(int, default=0)
        leechers_by_crawler = orm.Optional(int, default=0)
        last_checked_by_crawler = orm.Optional(int, size=64, default=0, index=True)

    return CheckedTorrentsEntity

def define_message_record_binding(db):
    class MessageRecordEntity(db.Entity):
        rowid = orm.PrimaryKey(int, auto=True)
        peer_pk = orm.Required(bytes, index=True)
        received_ts = orm.Required(int, size=64, default=0, index=True)
        type = orm.Optional(str, index=True)
        size = orm.Required(int)
    return MessageRecordEntity
