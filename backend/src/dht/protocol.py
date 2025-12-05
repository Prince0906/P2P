"""
Kademlia DHT Protocol

Design Decision: Message Format
===============================

Options Considered:
1. JSON - Human readable, flexible, larger
2. Protocol Buffers - Compact, typed, requires compilation
3. MessagePack - Compact, flexible, no compilation
4. Custom binary - Most compact, hardest to maintain

Decision: JSON over UDP
- Simple to implement and debug
- Human readable for development
- Size overhead acceptable for LAN
- Easy to extend with new message types
- Can upgrade to MessagePack later if needed

Message Types (following Kademlia paper):
- PING: Check if node is alive
- PONG: Response to PING
- FIND_NODE: Find K closest nodes to an ID
- FIND_VALUE: Find value or closest nodes
- STORE: Store a key-value pair
- ANNOUNCE_PEER: Announce we have a file
"""

import json
import asyncio
import struct
import time
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Callable, Awaitable, Tuple
import logging

from .utils import ID_BYTES, generate_node_id, id_to_hex, hex_to_id
from .routing import NodeInfo

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """DHT Protocol message types."""
    # Basic operations
    PING = "PING"
    PONG = "PONG"
    
    # Node lookup
    FIND_NODE = "FIND_NODE"
    FIND_NODE_RESPONSE = "FIND_NODE_RESPONSE"
    
    # Value operations
    FIND_VALUE = "FIND_VALUE"
    FIND_VALUE_RESPONSE = "FIND_VALUE_RESPONSE"
    
    # Storage operations
    STORE = "STORE"
    STORE_RESPONSE = "STORE_RESPONSE"
    
    # File announcement (extension for file sharing)
    ANNOUNCE_PEER = "ANNOUNCE_PEER"
    ANNOUNCE_RESPONSE = "ANNOUNCE_RESPONSE"
    
    # Get peers who have a file
    GET_PEERS = "GET_PEERS"
    GET_PEERS_RESPONSE = "GET_PEERS_RESPONSE"


@dataclass
class Message:
    """
    A DHT protocol message.
    
    Every message contains:
    - type: What kind of message
    - sender_id: Who sent it (node ID)
    - message_id: Unique ID for request/response matching
    - payload: Type-specific data
    """
    type: MessageType
    sender_id: bytes
    message_id: bytes = field(default_factory=lambda: generate_node_id()[:8])
    payload: Dict[str, Any] = field(default_factory=dict)
    
    def to_bytes(self) -> bytes:
        """Serialize message to bytes for transmission."""
        data = {
            'type': self.type.value,
            'sender_id': self.sender_id.hex(),
            'message_id': self.message_id.hex(),
            'payload': self.payload,
        }
        return json.dumps(data).encode('utf-8')
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'Message':
        """Deserialize message from bytes."""
        parsed = json.loads(data.decode('utf-8'))
        return cls(
            type=MessageType(parsed['type']),
            sender_id=bytes.fromhex(parsed['sender_id']),
            message_id=bytes.fromhex(parsed['message_id']),
            payload=parsed.get('payload', {}),
        )
    
    def create_response(self, response_type: MessageType, payload: Dict = None) -> 'Message':
        """Create a response message with the same message_id."""
        return Message(
            type=response_type,
            sender_id=self.sender_id,  # Will be replaced by actual sender
            message_id=self.message_id,
            payload=payload or {},
        )


class DHTProtocol(asyncio.DatagramProtocol):
    """
    UDP Protocol handler for DHT messages.
    
    Handles:
    - Sending and receiving UDP datagrams
    - Message serialization/deserialization
    - Request/response correlation
    - Timeouts for pending requests
    
    Design Note: We use asyncio's DatagramProtocol for clean integration
    with the event loop. Each request gets a unique ID and we track
    pending requests with futures.
    """
    
    # Default timeout for requests
    REQUEST_TIMEOUT = 5.0  # seconds
    
    def __init__(self, node_id: bytes, on_message: Callable[['Message', Tuple[str, int]], Awaitable[Optional['Message']]]):
        """
        Initialize the protocol handler.
        
        Args:
            node_id: Our node's ID
            on_message: Async callback for handling incoming messages
                       Returns optional response message
        """
        self.node_id = node_id
        self.on_message = on_message
        self.transport: Optional[asyncio.DatagramTransport] = None
        
        # Track pending requests: message_id -> (future, timestamp)
        self._pending: Dict[bytes, Tuple[asyncio.Future, float]] = {}
        self._pending_lock = asyncio.Lock()
        
        # Cleanup task for timed-out requests
        self._cleanup_task: Optional[asyncio.Task] = None
    
    def connection_made(self, transport: asyncio.DatagramTransport):
        """Called when the UDP socket is ready."""
        self.transport = transport
        logger.info(f"DHT Protocol ready on {transport.get_extra_info('sockname')}")
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_pending())
    
    def connection_lost(self, exc):
        """Called when the socket is closed."""
        logger.info("DHT Protocol connection lost")
        if self._cleanup_task:
            self._cleanup_task.cancel()
    
    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        """
        Called when a UDP datagram is received.
        
        Handles both incoming requests and responses to our requests.
        """
        try:
            message = Message.from_bytes(data)
            
            # Check if this is a response to a pending request
            if message.message_id in self._pending:
                asyncio.create_task(self._handle_response(message))
            else:
                # It's a new incoming request
                asyncio.create_task(self._handle_request(message, addr))
                
        except Exception as e:
            logger.error(f"Error processing datagram from {addr}: {e}")
    
    def error_received(self, exc):
        """Called when a send or receive operation fails."""
        logger.error(f"DHT Protocol error: {exc}")
    
    async def _handle_response(self, message: Message):
        """Handle a response to one of our requests."""
        async with self._pending_lock:
            if message.message_id in self._pending:
                future, _ = self._pending.pop(message.message_id)
                if not future.done():
                    future.set_result(message)
    
    async def _handle_request(self, message: Message, addr: Tuple[str, int]):
        """Handle an incoming request and send response."""
        try:
            response = await self.on_message(message, addr)
            if response:
                # Update sender_id to be our ID
                response.sender_id = self.node_id
                self.send_message(response, addr)
        except Exception as e:
            logger.error(f"Error handling request from {addr}: {e}")
    
    async def _cleanup_pending(self):
        """Periodically clean up timed-out requests."""
        while True:
            try:
                await asyncio.sleep(1.0)
                now = time.time()
                
                async with self._pending_lock:
                    timed_out = []
                    for msg_id, (future, timestamp) in self._pending.items():
                        if now - timestamp > self.REQUEST_TIMEOUT:
                            timed_out.append(msg_id)
                    
                    for msg_id in timed_out:
                        future, _ = self._pending.pop(msg_id)
                        if not future.done():
                            future.set_exception(asyncio.TimeoutError())
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
    
    def send_message(self, message: Message, addr: Tuple[str, int]):
        """Send a message to an address (fire and forget)."""
        if self.transport:
            data = message.to_bytes()
            self.transport.sendto(data, addr)
    
    async def send_request(self, message: Message, addr: Tuple[str, int], 
                          timeout: float = None) -> Optional[Message]:
        """
        Send a request and wait for response.
        
        Args:
            message: The message to send
            addr: Destination (ip, port)
            timeout: Optional custom timeout
        
        Returns:
            Response message, or None if timed out
        """
        if not self.transport:
            raise RuntimeError("Protocol not connected")
        
        # Create a future for the response
        future = asyncio.get_event_loop().create_future()
        
        async with self._pending_lock:
            self._pending[message.message_id] = (future, time.time())
        
        # Send the message
        self.send_message(message, addr)
        
        # Wait for response
        try:
            return await asyncio.wait_for(
                future, 
                timeout=timeout or self.REQUEST_TIMEOUT
            )
        except asyncio.TimeoutError:
            # Clean up if not already done
            async with self._pending_lock:
                self._pending.pop(message.message_id, None)
            return None


# Helper functions for creating specific message types

def create_ping(sender_id: bytes) -> Message:
    """Create a PING message."""
    return Message(type=MessageType.PING, sender_id=sender_id)


def create_pong(sender_id: bytes, request: Message) -> Message:
    """Create a PONG response."""
    return Message(
        type=MessageType.PONG,
        sender_id=sender_id,
        message_id=request.message_id,
    )


def create_find_node(sender_id: bytes, target_id: bytes) -> Message:
    """Create a FIND_NODE request."""
    return Message(
        type=MessageType.FIND_NODE,
        sender_id=sender_id,
        payload={'target_id': target_id.hex()},
    )


def create_find_node_response(sender_id: bytes, request: Message, 
                              nodes: List[NodeInfo]) -> Message:
    """Create a FIND_NODE response with closest nodes."""
    return Message(
        type=MessageType.FIND_NODE_RESPONSE,
        sender_id=sender_id,
        message_id=request.message_id,
        payload={'nodes': [n.to_dict() for n in nodes]},
    )


def create_store(sender_id: bytes, key: bytes, value: Any) -> Message:
    """Create a STORE request."""
    return Message(
        type=MessageType.STORE,
        sender_id=sender_id,
        payload={
            'key': key.hex(),
            'value': value,
        },
    )


def create_store_response(sender_id: bytes, request: Message, 
                         success: bool) -> Message:
    """Create a STORE response."""
    return Message(
        type=MessageType.STORE_RESPONSE,
        sender_id=sender_id,
        message_id=request.message_id,
        payload={'success': success},
    )


def create_find_value(sender_id: bytes, key: bytes) -> Message:
    """Create a FIND_VALUE request."""
    return Message(
        type=MessageType.FIND_VALUE,
        sender_id=sender_id,
        payload={'key': key.hex()},
    )


def create_find_value_response(sender_id: bytes, request: Message,
                               value: Any = None, 
                               nodes: List[NodeInfo] = None) -> Message:
    """Create a FIND_VALUE response (value or closest nodes)."""
    payload = {}
    if value is not None:
        payload['value'] = value
    if nodes:
        payload['nodes'] = [n.to_dict() for n in nodes]
    
    return Message(
        type=MessageType.FIND_VALUE_RESPONSE,
        sender_id=sender_id,
        message_id=request.message_id,
        payload=payload,
    )


def create_announce_peer(sender_id: bytes, info_hash: bytes, 
                        port: int) -> Message:
    """Create an ANNOUNCE_PEER request (we have this file)."""
    return Message(
        type=MessageType.ANNOUNCE_PEER,
        sender_id=sender_id,
        payload={
            'info_hash': info_hash.hex(),
            'port': port,
        },
    )


def create_get_peers(sender_id: bytes, info_hash: bytes) -> Message:
    """Create a GET_PEERS request (who has this file?)."""
    return Message(
        type=MessageType.GET_PEERS,
        sender_id=sender_id,
        payload={'info_hash': info_hash.hex()},
    )


def create_get_peers_response(sender_id: bytes, request: Message,
                              peers: List[Tuple[str, int]] = None,
                              nodes: List[NodeInfo] = None) -> Message:
    """Create a GET_PEERS response (peers who have file, or closest nodes)."""
    payload = {}
    if peers:
        payload['peers'] = [{'ip': ip, 'port': port} for ip, port in peers]
    if nodes:
        payload['nodes'] = [n.to_dict() for n in nodes]
    
    return Message(
        type=MessageType.GET_PEERS_RESPONSE,
        sender_id=sender_id,
        message_id=request.message_id,
        payload=payload,
    )



