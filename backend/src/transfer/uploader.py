"""
Chunk Uploader

Handles serving chunks to other peers.
"""

import asyncio
import logging
from typing import Optional
from pathlib import Path

from .protocol import (
    TransferServer, TransferProtocol, TransferMessage,
    TransferMessageType
)
from ..file.storage import ChunkStorage
from ..file.manifest import FileManifest

logger = logging.getLogger(__name__)


class ChunkUploader:
    """
    Serves file chunks and manifests to requesting peers.
    
    Integrates with the transfer server to handle requests.
    """
    
    def __init__(self, storage: ChunkStorage, host: str = '0.0.0.0', 
                 port: int = 8469):
        self.storage = storage
        self.server = TransferServer(host=host, port=port)
        self.port = port
        
        # Statistics
        self.chunks_served = 0
        self.bytes_uploaded = 0
        
        # Register handlers
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Register request handlers with the server."""
        self.server.set_handler(
            TransferMessageType.REQUEST_CHUNK,
            self._handle_chunk_request
        )
        self.server.set_handler(
            TransferMessageType.REQUEST_MANIFEST,
            self._handle_manifest_request
        )
        self.server.set_handler(
            TransferMessageType.PING,
            self._handle_ping
        )
    
    async def start(self):
        """Start the uploader server."""
        await self.server.start()
        logger.info(f"Chunk uploader started on port {self.port}")
    
    async def stop(self):
        """Stop the uploader server."""
        await self.server.stop()
        logger.info(f"Chunk uploader stopped. Served {self.chunks_served} chunks, "
                   f"{self.bytes_uploaded:,} bytes")
    
    async def _handle_chunk_request(self, message: TransferMessage,
                                    protocol: TransferProtocol):
        """Handle a chunk request."""
        chunk_hash = message.headers.get('chunk_hash')
        if not chunk_hash:
            await protocol.send_chunk_not_found('')
            return
        
        # Get chunk from storage
        chunk_data = await self.storage.get_chunk(chunk_hash)
        
        if chunk_data:
            await protocol.send_chunk(chunk_hash, chunk_data)
            self.chunks_served += 1
            self.bytes_uploaded += len(chunk_data)
            logger.debug(f"Served chunk {chunk_hash[:16]}... ({len(chunk_data)} bytes)")
        else:
            await protocol.send_chunk_not_found(chunk_hash)
            logger.debug(f"Chunk not found: {chunk_hash[:16]}...")
    
    async def _handle_manifest_request(self, message: TransferMessage,
                                       protocol: TransferProtocol):
        """Handle a manifest request."""
        info_hash = message.headers.get('info_hash')
        if not info_hash:
            await protocol.send_manifest_not_found('')
            return
        
        # Get manifest from storage
        manifest = await self.storage.get_manifest(info_hash)
        
        if manifest:
            await protocol.send_manifest(info_hash, manifest.to_json())
            logger.debug(f"Served manifest {info_hash[:16]}...")
        else:
            await protocol.send_manifest_not_found(info_hash)
            logger.debug(f"Manifest not found: {info_hash[:16]}...")
    
    async def _handle_ping(self, message: TransferMessage,
                          protocol: TransferProtocol):
        """Handle a ping (health check)."""
        pong = TransferMessage(
            type=TransferMessageType.PONG,
            headers={}
        )
        await protocol.send(pong)
    
    def get_stats(self) -> dict:
        """Get uploader statistics."""
        return {
            'chunks_served': self.chunks_served,
            'bytes_uploaded': self.bytes_uploaded,
            'port': self.port,
        }



