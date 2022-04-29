from dataclasses import dataclass


@dataclass
class EVASettings:
    # A single block size in bytes. Please keep in mind that  ipv8 adds approx. 177 bytes to each packet.
    block_size: int = 1000
    # Count of consecutive blocks to send
    window_size: int = 16
    # A started id that will be used to assigning protocol's messages ids
    start_message_id: int = 186
    # An interval until the next attempt to retransmit will be made
    retransmit_enabled: bool = True
    # A limit for retransmit attempts
    retransmit_attempt_count: int = 3
    # An interval after which the next attempt to retransmit will perform
    retransmit_interval_in_sec: float = 3.0
    # An interval after which the next scheduled transfer will be send
    scheduled_send_interval_in_sec: float = 5.0
    # An interval after which the transfer will be considered as "dead" and will be terminated
    timeout_interval_in_sec: float = 10.0
    # Limit for binary data size. If this limit will be exceeded, the exception will be returned through a registered
    # error handler
    binary_size_limit: int = 1024 * 1024 * 1024
    # The flag indicating is termination-by-timeout mechanism enabled or not
    terminate_by_timeout_enabled: bool = True
    # An upper limit of simultaneously served peers. The reason for introducing this parameter is to have a tool for
    # limiting socket load which could lead to packet loss.
    max_simultaneous_transfers: int = 10
