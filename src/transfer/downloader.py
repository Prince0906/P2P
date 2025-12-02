"""
Chunk Downloader

Design Decision: Download Strategy
===================================

Options Considered:
1. Sequential download from single peer
   - Simple but slow
   - Single point of failure
   
2. Parallel download from single peer
   - Better speed
   - Still single point of failure
   
3. Parallel download from multiple peers (swarming)
   - Best speed
   - Redundancy
   - More complex
   
4. Rarest-first chunk selection
   - Helps file availability
   - More complex, better for large swarms

Decision: Parallel multi-peer download
- Request different chunks from different peers
- Retry failed chunks with other peers
- Simple round-robin peer selection initially
- Can add rarest-first later

Download Flow:
1. Get manifest (from DHT or peers)
2. Find peers who have the file
3. Request chunks in parallel from multiple peers
4. Verify each chunk hash
5. Reassemble when complete
"""

import asyncio
import logging
import time
import hashlib
from typing import Optional, List, Tuple, Dict, Set, Callable
from dataclasses import dataclass, field
from pathlib import Path

from .protocol import connect_to_peer, TransferProtocol
from ..file.storage import ChunkStorage
from ..file.manifest import FileManifest

logger = logging.getLogger(__name__)


@dataclass
class DownloadProgress:
    """Track download progress."""
    total_chunks: int
    downloaded_chunks: int = 0
    failed_chunks: int = 0
    bytes_downloaded: int = 0
    start_time: float = field(default_factory=time.time)
    
    @property
    def progress(self) -> float:
        """Progress as 0.0 to 1.0."""
        if self.total_chunks == 0:
            return 1.0
        return self.downloaded_chunks / self.total_chunks
    
    @property
    def progress_percent(self) -> float:
        """Progress as percentage."""
        return self.progress * 100
    
    @property
    def elapsed_seconds(self) -> float:
        """Time elapsed since start."""
        return time.time() - self.start_time
    
    @property
    def speed_bytes_per_sec(self) -> float:
        """Download speed in bytes/second."""
        elapsed = self.elapsed_seconds
        if elapsed == 0:
            return 0
        return self.bytes_downloaded / elapsed


# Progress callback type
ProgressCallback = Callable[[DownloadProgress], None]


class ChunkDownloader:
    """
    Downloads individual chunks from peers.
    
    Handles connection management and retry logic.
    """
    
    def __init__(self, max_connections: int = 5, 
                 chunk_timeout: float = 30.0):
        self.max_connections = max_connections
        self.chunk_timeout = chunk_timeout
        
        # Connection pool: (ip, port) -> TransferProtocol
        self._connections: Dict[Tuple[str, int], TransferProtocol] = {}
        self._connection_lock = asyncio.Lock()
    
    async def get_connection(self, ip: str, port: int) -> Optional[TransferProtocol]:
        """Get or create a connection to a peer."""
        key = (ip, port)
        
        async with self._connection_lock:
            # Check existing connection
            if key in self._connections:
                conn = self._connections[key]
                if not conn._closed:
                    return conn
                else:
                    del self._connections[key]
            
            # Create new connection
            conn = await connect_to_peer(ip, port)
            if conn:
                self._connections[key] = conn
            
            return conn
    
    async def close_connection(self, ip: str, port: int):
        """Close a connection to a peer."""
        key = (ip, port)
        
        async with self._connection_lock:
            if key in self._connections:
                await self._connections[key].close()
                del self._connections[key]
    
    async def close_all(self):
        """Close all connections."""
        async with self._connection_lock:
            for conn in self._connections.values():
                await conn.close()
            self._connections.clear()
    
    async def download_chunk(self, ip: str, port: int, 
                            chunk_hash: str) -> Optional[bytes]:
        """
        Download a single chunk from a peer.
        
        Returns:
            Chunk data (verified), or None if failed
        """
        try:
            conn = await self.get_connection(ip, port)
            if conn is None:
                return None
            
            # Request chunk with timeout
            data = await asyncio.wait_for(
                conn.request_chunk(chunk_hash),
                timeout=self.chunk_timeout
            )
            
            if data is None:
                return None
            
            # Verify hash
            actual_hash = hashlib.sha256(data).hexdigest()
            if actual_hash != chunk_hash:
                logger.warning(f"Chunk hash mismatch from {ip}:{port}")
                await self.close_connection(ip, port)
                return None
            
            return data
            
        except asyncio.TimeoutError:
            logger.warning(f"Chunk download timeout from {ip}:{port}")
            await self.close_connection(ip, port)
            return None
        except Exception as e:
            logger.error(f"Error downloading chunk from {ip}:{port}: {e}")
            await self.close_connection(ip, port)
            return None
    
    async def download_manifest(self, ip: str, port: int,
                               info_hash: str) -> Optional[FileManifest]:
        """Download a manifest from a peer."""
        try:
            conn = await self.get_connection(ip, port)
            if conn is None:
                return None
            
            manifest_json = await asyncio.wait_for(
                conn.request_manifest(info_hash),
                timeout=10.0
            )
            
            if manifest_json is None:
                return None
            
            manifest = FileManifest.from_json(manifest_json)
            
            # Verify info_hash
            if manifest.info_hash != info_hash:
                logger.warning(f"Manifest hash mismatch from {ip}:{port}")
                return None
            
            return manifest
            
        except Exception as e:
            logger.error(f"Error downloading manifest from {ip}:{port}: {e}")
            return None


class FileDownloader:
    """
    Downloads complete files using multiple peers.
    
    Coordinates chunk downloads across multiple peers for speed.
    """
    
    def __init__(self, storage: ChunkStorage, max_concurrent: int = 5):
        """
        Initialize file downloader.
        
        Args:
            storage: Where to store downloaded chunks
            max_concurrent: Maximum concurrent chunk downloads
        """
        self.storage = storage
        self.max_concurrent = max_concurrent
        self.chunk_downloader = ChunkDownloader(max_connections=max_concurrent * 2)
        
        # Statistics
        self.files_downloaded = 0
        self.total_bytes = 0
    
    async def download_file(self, manifest: FileManifest,
                           peers: List[Tuple[str, int]],
                           progress_callback: ProgressCallback = None,
                           output_path: Path = None) -> Optional[Path]:
        """
        Download a complete file.
        
        Args:
            manifest: File manifest with chunk info
            peers: List of (ip, port) tuples for peers with the file
            progress_callback: Optional callback for progress updates
            output_path: Where to save the file (default: storage/files/)
        
        Returns:
            Path to downloaded file, or None if failed
        """
        if not peers:
            logger.error("No peers available for download")
            return None
        
        # Store manifest
        await self.storage.store_manifest(manifest)
        
        # Get missing chunks
        missing_chunks = await self.storage.get_missing_chunks(manifest)
        
        if not missing_chunks:
            # Already have all chunks
            logger.info(f"All chunks already available for {manifest.name}")
            return await self.storage.reassemble_file(manifest, output_path)
        
        logger.info(f"Downloading {manifest.name}: {len(missing_chunks)}/{manifest.chunk_count} chunks needed")
        
        # Initialize progress
        progress = DownloadProgress(
            total_chunks=len(missing_chunks),
            downloaded_chunks=0,
        )
        
        # Create download tasks
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def download_chunk_with_retry(chunk_hash: str) -> bool:
            """Download a chunk with retry across peers."""
            async with semaphore:
                # Try each peer
                for ip, port in peers:
                    data = await self.chunk_downloader.download_chunk(
                        ip, port, chunk_hash
                    )
                    
                    if data:
                        # Store the chunk
                        success = await self.storage.store_chunk(chunk_hash, data)
                        if success:
                            progress.downloaded_chunks += 1
                            progress.bytes_downloaded += len(data)
                            
                            if progress_callback:
                                progress_callback(progress)
                            
                            return True
                
                # All peers failed
                progress.failed_chunks += 1
                return False
        
        # Download all chunks
        tasks = [
            download_chunk_with_retry(chunk_hash)
            for chunk_hash in missing_chunks
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Close connections
        await self.chunk_downloader.close_all()
        
        # Check results
        success_count = sum(1 for r in results if r)
        
        if success_count < len(missing_chunks):
            logger.error(f"Download incomplete: {success_count}/{len(missing_chunks)} chunks")
            return None
        
        # Reassemble file
        logger.info(f"Download complete, reassembling {manifest.name}")
        result_path = await self.storage.reassemble_file(manifest, output_path)
        
        if result_path:
            self.files_downloaded += 1
            self.total_bytes += manifest.size
            logger.info(f"File saved to {result_path}")
        
        return result_path
    
    async def download_from_dht(self, dht_node, info_hash: str,
                               progress_callback: ProgressCallback = None,
                               output_path: Path = None) -> Optional[Path]:
        """
        Download a file using DHT to find peers.
        
        This is the high-level download method that:
        1. Finds peers for the info_hash via DHT
        2. Downloads manifest from a peer
        3. Downloads all chunks
        4. Reassembles the file
        """
        from ..dht.kademlia import KademliaNode
        
        logger.info(f"Looking up peers for {info_hash[:16]}...")
        
        # Find peers via DHT
        peers = await dht_node.get_peers(bytes.fromhex(info_hash))
        
        if not peers:
            logger.error("No peers found for this file")
            return None
        
        logger.info(f"Found {len(peers)} peers")
        
        # Try to get manifest from peers
        manifest = None
        for ip, port in peers:
            manifest = await self.chunk_downloader.download_manifest(
                ip, port, info_hash
            )
            if manifest:
                break
        
        if manifest is None:
            logger.error("Could not download manifest from any peer")
            return None
        
        logger.info(f"Got manifest: {manifest.name} ({manifest.size:,} bytes)")
        
        # Download the file
        return await self.download_file(
            manifest, peers, progress_callback, output_path
        )
    
    def get_stats(self) -> dict:
        """Get downloader statistics."""
        return {
            'files_downloaded': self.files_downloaded,
            'total_bytes': self.total_bytes,
        }


if __name__ == "__main__":
    # Simple test
    import sys
    
    async def test():
        print("Downloader module loaded successfully")
        
        # Create a dummy progress callback
        def show_progress(p: DownloadProgress):
            print(f"Progress: {p.progress_percent:.1f}% "
                  f"({p.downloaded_chunks}/{p.total_chunks} chunks, "
                  f"{p.bytes_downloaded:,} bytes)")
    
    asyncio.run(test())



