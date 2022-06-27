from pony import orm
from pony.orm import Json


def define_remote_select_query_entity_binding(db):
    class RemoteSelectQueryEntity(db.Entity):
        rowid = orm.PrimaryKey(int, auto=True)

        peer_pk = orm.Required(bytes, index=True)
        peer_ip = orm.Required(str, index=True)
        peer_port = orm.Required(int, index=True)
        received_at = orm.Optional(int, size=64, default=0, index=True)

        json = orm.Required(Json)
    return RemoteSelectQueryEntity