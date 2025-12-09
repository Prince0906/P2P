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
import random
from typing import Optional, List, Tuple, Dict, Set, Callable
from dataclasses import dataclass, field
from pathlib import Path

from .protocol import connect_to_peer, TransferProtocol
from ..file.storage import ChunkStorage
from ..file.manifest import FileManifest

logger = logging.getLogger(__name__)


@dataclass
class ChunkState:
    """Track individual chunk download state for visualization."""
    chunk_hash: str
    chunk_index: int
    status: str = 'pending'  # 'pending', 'downloading', 'complete', 'failed'
    peer_ip: Optional[str] = None
    peer_port: Optional[int] = None
    size: int = 0
    downloaded_at: Optional[float] = None


@dataclass
class PeerState:
    """Track peer contribution for visualization."""
    ip: str
    port: int
    chunks_assigned: int = 0
    chunks_completed: int = 0
    chunks_failed: int = 0
    bytes_downloaded: int = 0
    is_active: bool = True


@dataclass
class DownloadProgress:
    """Track download progress with detailed chunk/peer info for visualization."""
    total_chunks: int
    downloaded_chunks: int = 0
    failed_chunks: int = 0
    bytes_downloaded: int = 0
    start_time: float = field(default_factory=time.time)
    
    # Detailed tracking for visualization
    chunk_states: Dict[str, ChunkState] = field(default_factory=dict)  # hash -> ChunkState
    peer_states: Dict[str, PeerState] = field(default_factory=dict)    # "ip:port" -> PeerState
    phase: str = 'initializing'  # 'initializing', 'finding_peers', 'downloading', 'merging', 'complete', 'failed'
    file_name: str = ''
    file_size: int = 0
    
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
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'total_chunks': self.total_chunks,
            'downloaded_chunks': self.downloaded_chunks,
            'failed_chunks': self.failed_chunks,
            'bytes_downloaded': self.bytes_downloaded,
            'progress_percent': self.progress_percent,
            'speed_bytes_per_sec': self.speed_bytes_per_sec,
            'elapsed_seconds': self.elapsed_seconds,
            'phase': self.phase,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'chunks': [
                {
                    'index': cs.chunk_index,
                    'hash': cs.chunk_hash[:16],
                    'status': cs.status,
                    'peer': f"{cs.peer_ip}:{cs.peer_port}" if cs.peer_ip else None,
                }
                for cs in sorted(self.chunk_states.values(), key=lambda x: x.chunk_index)
            ],
            'peers': [
                {
                    'ip': ps.ip,
                    'port': ps.port,
                    'chunks_assigned': ps.chunks_assigned,
                    'chunks_completed': ps.chunks_completed,
                    'chunks_failed': ps.chunks_failed,
                    'bytes_downloaded': ps.bytes_downloaded,
                    'is_active': ps.is_active,
                }
                for ps in self.peer_states.values()
            ],
        }


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
        Download a complete file using multiple peers with load balancing.
        
        Load Balancing Strategy:
        1. Shuffle peers - different downloaders get different peer order
        2. Round-robin chunk assignment - distribute chunks across all peers
        3. Parallel downloads from all peers simultaneously
        4. Retry failed chunks with other peers
        
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
        
        # === LOAD BALANCING: Shuffle peers ===
        # Each downloader gets a random order, preventing thundering herd
        peers = list(peers)
        random.shuffle(peers)
        logger.debug(f"Peer order after shuffle: {[(p[0], p[1]) for p in peers[:3]]}...")
        
        # === LOAD BALANCING: Round-robin chunk assignment ===
        # Distribute chunks evenly across all available peers
        chunk_assignments = self._assign_chunks_round_robin(missing_chunks, peers)
        
        # Log chunk distribution
        for peer, chunks in chunk_assignments.items():
            logger.debug(f"Assigned {len(chunks)} chunks to {peer[0]}:{peer[1]}")
        
        # Build chunk index map for tracking
        chunk_index_map = {}
        for chunk_info in manifest.chunks:
            chunk_index_map[chunk_info.hash] = (chunk_info.index, chunk_info.size)
        
        # Initialize progress with detailed tracking
        progress = DownloadProgress(
            total_chunks=len(missing_chunks),
            downloaded_chunks=0,
            file_name=manifest.name,
            file_size=manifest.size,
            phase='finding_peers',
        )
        
        # Initialize chunk states
        for chunk_hash in missing_chunks:
            idx, size = chunk_index_map.get(chunk_hash, (0, 0))
            progress.chunk_states[chunk_hash] = ChunkState(
                chunk_hash=chunk_hash,
                chunk_index=idx,
                status='pending',
                size=size,
            )
        
        # Initialize peer states
        for peer, chunks in chunk_assignments.items():
            ip, port = peer
            peer_key = f"{ip}:{port}"
            progress.peer_states[peer_key] = PeerState(
                ip=ip,
                port=port,
                chunks_assigned=len(chunks),
            )
        
        # Notify about peers found
        progress.phase = 'downloading'
        if progress_callback:
            progress_callback(progress)
        
        # Track failed chunks for retry
        failed_chunks: List[str] = []
        failed_lock = asyncio.Lock()
        progress_lock = asyncio.Lock()  # Protect progress updates from race conditions
        
        async def download_from_peer(peer: Tuple[str, int], chunks: List[str]) -> None:
            """Download assigned chunks from a specific peer."""
            ip, port = peer
            peer_key = f"{ip}:{port}"
            
            for chunk_hash in chunks:
                # Mark chunk as downloading
                async with progress_lock:
                    if chunk_hash in progress.chunk_states:
                        progress.chunk_states[chunk_hash].status = 'downloading'
                        progress.chunk_states[chunk_hash].peer_ip = ip
                        progress.chunk_states[chunk_hash].peer_port = port
                    if progress_callback:
                        progress_callback(progress)
                
                data = await self.chunk_downloader.download_chunk(ip, port, chunk_hash)
                
                if data:
                    # Store chunk
                    success = await self.storage.store_chunk(chunk_hash, data)
                    if success:
                        async with progress_lock:
                            progress.downloaded_chunks += 1
                            progress.bytes_downloaded += len(data)
                            
                            # Update chunk state
                            if chunk_hash in progress.chunk_states:
                                progress.chunk_states[chunk_hash].status = 'complete'
                                progress.chunk_states[chunk_hash].downloaded_at = time.time()
                            
                            # Update peer state
                            if peer_key in progress.peer_states:
                                progress.peer_states[peer_key].chunks_completed += 1
                                progress.peer_states[peer_key].bytes_downloaded += len(data)
                            
                            if progress_callback:
                                progress_callback(progress)
                else:
                    # Mark chunk as failed and queue for retry
                    async with progress_lock:
                        if chunk_hash in progress.chunk_states:
                            progress.chunk_states[chunk_hash].status = 'failed'
                        if peer_key in progress.peer_states:
                            progress.peer_states[peer_key].chunks_failed += 1
                    async with failed_lock:
                        failed_chunks.append(chunk_hash)
        
        # Download from all peers in parallel
        tasks = [
            download_from_peer(peer, chunks)
            for peer, chunks in chunk_assignments.items()
            if chunks  # Skip peers with no assigned chunks
        ]
        
        await asyncio.gather(*tasks)
        
        # === Retry failed chunks with other peers ===
        if failed_chunks:
            logger.info(f"Retrying {len(failed_chunks)} failed chunks with alternate peers")
            
            async def retry_chunk(chunk_hash: str) -> bool:
                """Retry a chunk with all peers until success."""
                for ip, port in peers:
                    peer_key = f"{ip}:{port}"
                    
                    # Mark as retrying
                    async with progress_lock:
                        if chunk_hash in progress.chunk_states:
                            progress.chunk_states[chunk_hash].status = 'downloading'
                            progress.chunk_states[chunk_hash].peer_ip = ip
                            progress.chunk_states[chunk_hash].peer_port = port
                        if progress_callback:
                            progress_callback(progress)
                    
                    data = await self.chunk_downloader.download_chunk(ip, port, chunk_hash)
                    if data:
                        success = await self.storage.store_chunk(chunk_hash, data)
                        if success:
                            async with progress_lock:
                                progress.downloaded_chunks += 1
                                progress.bytes_downloaded += len(data)
                                if chunk_hash in progress.chunk_states:
                                    progress.chunk_states[chunk_hash].status = 'complete'
                                    progress.chunk_states[chunk_hash].downloaded_at = time.time()
                                if peer_key in progress.peer_states:
                                    progress.peer_states[peer_key].chunks_completed += 1
                                    progress.peer_states[peer_key].bytes_downloaded += len(data)
                                if progress_callback:
                                    progress_callback(progress)
                            return True
                
                # All peers failed for this chunk
                async with progress_lock:
                    if chunk_hash in progress.chunk_states:
                        progress.chunk_states[chunk_hash].status = 'failed'
                return False
            
            retry_tasks = [retry_chunk(ch) for ch in failed_chunks]
            retry_results = await asyncio.gather(*retry_tasks)
            
            # Update failed count
            progress.failed_chunks = sum(1 for r in retry_results if not r)
        
        # Close connections
        await self.chunk_downloader.close_all()
        
        # Check if download complete
        still_missing = await self.storage.get_missing_chunks(manifest)
        if still_missing:
            logger.error(f"Download incomplete: {len(still_missing)} chunks still missing")
            progress.phase = 'failed'
            if progress_callback:
                progress_callback(progress)
            return None
        
        # Reassemble file
        logger.info(f"Download complete, reassembling {manifest.name}")
        progress.phase = 'merging'
        if progress_callback:
            progress_callback(progress)
        
        result_path = await self.storage.reassemble_file(manifest, output_path)
        
        if result_path:
            self.files_downloaded += 1
            self.total_bytes += manifest.size
            logger.info(f"File saved to {result_path}")
            progress.phase = 'complete'
            if progress_callback:
                progress_callback(progress)
        else:
            progress.phase = 'failed'
            if progress_callback:
                progress_callback(progress)
        
        return result_path
    
    def _assign_chunks_round_robin(self, chunks: List[str], 
                                   peers: List[Tuple[str, int]]) -> Dict[Tuple[str, int], List[str]]:
        """
        Distribute chunks across peers using round-robin assignment.
        
        Example with 10 chunks and 2 peers:
            Peer A: chunks [0, 2, 4, 6, 8]
            Peer B: chunks [1, 3, 5, 7, 9]
        
        This ensures even load distribution across all available peers.
        """
        assignments: Dict[Tuple[str, int], List[str]] = {peer: [] for peer in peers}
        
        for i, chunk_hash in enumerate(chunks):
            peer = peers[i % len(peers)]
            assignments[peer].append(chunk_hash)
        
        return assignments
    
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



