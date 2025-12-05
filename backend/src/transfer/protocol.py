"""
File Transfer Protocol

Design Decision: Transfer Protocol
===================================

Options Considered:
1. HTTP - Standard, well-supported
   - Heavy, requires web server
   
2. Raw TCP with custom framing
   - Lightweight, full control
   - Need to handle framing ourselves
   
3. gRPC streaming
   - Good for structured data
   - Heavy dependency
   
4. WebSocket
   - Good for bidirectional
   - Overkill for chunk transfers

Decision: Custom TCP Protocol with Length-Prefixed Messages
- Simple 4-byte length prefix + JSON header + binary data
- Lightweight, no dependencies
- Full control over behavior
- Easy to debug

Message Format:
```
+----------------+----------------+----------------+
| Length (4B)    | Header (JSON)  | Data (binary)  |
+----------------+----------------+----------------+

Header JSON:
{
    "type": "REQUEST_CHUNK" | "CHUNK_DATA" | "REQUEST_MANIFEST" | ...
    "chunk_hash": "...",
    "data_length": 12345,
    ...
}
```
"""

import asyncio
import json
import struct
import logging
from enum import Enum
from typing import Optional, Tuple, Callable, Awaitable, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class TransferMessageType(Enum):
    """Transfer protocol message types."""
    # Chunk operations
    REQUEST_CHUNK = "REQUEST_CHUNK"
    CHUNK_DATA = "CHUNK_DATA"
    CHUNK_NOT_FOUND = "CHUNK_NOT_FOUND"
    
    # Manifest operations
    REQUEST_MANIFEST = "REQUEST_MANIFEST"
    MANIFEST_DATA = "MANIFEST_DATA"
    MANIFEST_NOT_FOUND = "MANIFEST_NOT_FOUND"
    
    # Control
    ERROR = "ERROR"
    PING = "PING"
    PONG = "PONG"


@dataclass
class TransferMessage:
    """A transfer protocol message."""
    type: TransferMessageType
    headers: Dict[str, Any]
    data: bytes = b''
    
    def to_bytes(self) -> bytes:
        """Serialize message to bytes."""
        # Create header JSON
        header_dict = {
            'type': self.type.value,
            'data_length': len(self.data),
            **self.headers
        }
        header_bytes = json.dumps(header_dict).encode('utf-8')
        
        # Calculate total length (header + data)
        total_length = len(header_bytes) + len(self.data)
        
        # Pack: length (4 bytes) + header_length (4 bytes) + header + data
        return (
            struct.pack('>I', total_length) +
            struct.pack('>I', len(header_bytes)) +
            header_bytes +
            self.data
        )
    
    @classmethod
    async def from_reader(cls, reader: asyncio.StreamReader) -> Optional['TransferMessage']:
        """Read a message from a stream."""
        try:
            # Read total length
            length_bytes = await reader.readexactly(4)
            total_length = struct.unpack('>I', length_bytes)[0]
            
            # Sanity check
            if total_length > 100 * 1024 * 1024:  # 100MB max
                raise ValueError(f"Message too large: {total_length}")
            
            # Read header length
            header_length_bytes = await reader.readexactly(4)
            header_length = struct.unpack('>I', header_length_bytes)[0]
            
            # Read header
            header_bytes = await reader.readexactly(header_length)
            header_dict = json.loads(header_bytes.decode('utf-8'))
            
            # Read data
            data_length = total_length - header_length
            data = await reader.readexactly(data_length) if data_length > 0 else b''
            
            # Extract type and remaining headers
            msg_type = TransferMessageType(header_dict.pop('type'))
            header_dict.pop('data_length', None)
            
            return cls(type=msg_type, headers=header_dict, data=data)
            
        except asyncio.IncompleteReadError:
            return None
        except Exception as e:
            logger.error(f"Error reading message: {e}")
            return None


class TransferProtocol:
    """
    Low-level transfer protocol handler.
    
    Handles sending/receiving messages over TCP.
    
    Thread-safe: Uses a lock to ensure only one request/response
    pair is active at a time per connection.
    """
    
    def __init__(self, reader: asyncio.StreamReader, 
                 writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self._closed = False
        # Lock to prevent concurrent reads/writes on the same connection
        self._lock = asyncio.Lock()
    
    @property
    def remote_address(self) -> Tuple[str, int]:
        """Get remote peer address."""
        return self.writer.get_extra_info('peername')
    
    async def send(self, message: TransferMessage):
        """Send a message."""
        if self._closed:
            raise ConnectionError("Connection closed")
        
        data = message.to_bytes()
        self.writer.write(data)
        await self.writer.drain()
    
    async def receive(self) -> Optional[TransferMessage]:
        """Receive a message."""
        if self._closed:
            return None
        return await TransferMessage.from_reader(self.reader)
    
    async def close(self):
        """Close the connection."""
        if not self._closed:
            self._closed = True
            self.writer.close()
            await self.writer.wait_closed()
    
    # === High-level operations ===
    
    async def request_chunk(self, chunk_hash: str) -> Optional[bytes]:
        """
        Request a chunk from the peer.
        
        Returns:
            Chunk data, or None if not found/error
        """
        # Use lock to ensure request/response pair is atomic
        async with self._lock:
            request = TransferMessage(
                type=TransferMessageType.REQUEST_CHUNK,
                headers={'chunk_hash': chunk_hash}
            )
            data = request.to_bytes()
            self.writer.write(data)
            await self.writer.drain()
            
            response = await TransferMessage.from_reader(self.reader)
            if response is None:
                return None
            
            if response.type == TransferMessageType.CHUNK_DATA:
                return response.data
            
            return None
    
    async def request_manifest(self, info_hash: str) -> Optional[str]:
        """
        Request a file manifest from the peer.
        
        Returns:
            Manifest JSON string, or None if not found
        """
        # Use lock to ensure request/response pair is atomic
        async with self._lock:
            request = TransferMessage(
                type=TransferMessageType.REQUEST_MANIFEST,
                headers={'info_hash': info_hash}
            )
            data = request.to_bytes()
            self.writer.write(data)
            await self.writer.drain()
            
            response = await TransferMessage.from_reader(self.reader)
            if response is None:
                return None
            
            if response.type == TransferMessageType.MANIFEST_DATA:
                return response.data.decode('utf-8')
            
            return None
    
    async def send_chunk(self, chunk_hash: str, data: bytes):
        """Send a chunk to the peer."""
        async with self._lock:
            message = TransferMessage(
                type=TransferMessageType.CHUNK_DATA,
                headers={'chunk_hash': chunk_hash},
                data=data
            )
            data_bytes = message.to_bytes()
            self.writer.write(data_bytes)
            await self.writer.drain()
    
    async def send_chunk_not_found(self, chunk_hash: str):
        """Send chunk not found response."""
        async with self._lock:
            message = TransferMessage(
                type=TransferMessageType.CHUNK_NOT_FOUND,
                headers={'chunk_hash': chunk_hash}
            )
            data = message.to_bytes()
            self.writer.write(data)
            await self.writer.drain()
    
    async def send_manifest(self, info_hash: str, manifest_json: str):
        """Send a manifest to the peer."""
        async with self._lock:
            message = TransferMessage(
                type=TransferMessageType.MANIFEST_DATA,
                headers={'info_hash': info_hash},
                data=manifest_json.encode('utf-8')
            )
            data = message.to_bytes()
            self.writer.write(data)
            await self.writer.drain()
    
    async def send_manifest_not_found(self, info_hash: str):
        """Send manifest not found response."""
        async with self._lock:
            message = TransferMessage(
                type=TransferMessageType.MANIFEST_NOT_FOUND,
                headers={'info_hash': info_hash}
            )
            data = message.to_bytes()
            self.writer.write(data)
            await self.writer.drain()


# Type for request handlers
RequestHandler = Callable[[TransferMessage, TransferProtocol], Awaitable[None]]


class TransferServer:
    """
    TCP server for handling chunk transfer requests.
    
    Serves chunks and manifests to other peers.
    """
    
    def __init__(self, host: str = '0.0.0.0', port: int = 8469):
        self.host = host
        self.port = port
        self.server: Optional[asyncio.AbstractServer] = None
        self._handlers: Dict[TransferMessageType, RequestHandler] = {}
        self._running = False
    
    def on_request(self, msg_type: TransferMessageType):
        """Decorator to register a request handler."""
        def decorator(handler: RequestHandler):
            self._handlers[msg_type] = handler
            return handler
        return decorator
    
    def set_handler(self, msg_type: TransferMessageType, handler: RequestHandler):
        """Set a request handler."""
        self._handlers[msg_type] = handler
    
    async def start(self):
        """Start the transfer server."""
        self.server = await asyncio.start_server(
            self._handle_connection,
            self.host,
            self.port
        )
        self._running = True
        
        addr = self.server.sockets[0].getsockname()
        logger.info(f"Transfer server listening on {addr}")
    
    async def stop(self):
        """Stop the transfer server."""
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Transfer server stopped")
    
    async def _handle_connection(self, reader: asyncio.StreamReader,
                                 writer: asyncio.StreamWriter):
        """Handle an incoming connection."""
        protocol = TransferProtocol(reader, writer)
        peer = protocol.remote_address
        logger.debug(f"New transfer connection from {peer}")
        
        try:
            while self._running:
                message = await protocol.receive()
                if message is None:
                    break
                
                handler = self._handlers.get(message.type)
                if handler:
                    await handler(message, protocol)
                else:
                    logger.warning(f"No handler for {message.type}")
                    
        except Exception as e:
            logger.error(f"Error handling connection from {peer}: {e}")
        finally:
            await protocol.close()
            logger.debug(f"Connection closed: {peer}")


async def connect_to_peer(ip: str, port: int, 
                         timeout: float = 10.0) -> Optional[TransferProtocol]:
    """
    Connect to a peer's transfer server.
    
    Returns:
        TransferProtocol, or None if connection failed
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=timeout
        )
        return TransferProtocol(reader, writer)
    except Exception as e:
        logger.error(f"Failed to connect to {ip}:{port}: {e}")
        return None



