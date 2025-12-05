"""
P2P Node - Main Controller

This is the main entry point that orchestrates all components:
- DHT (Kademlia) for peer/file discovery
- File storage and chunking
- Transfer server for uploads
- Discovery for finding peers on LAN
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Callable
from dataclasses import dataclass

from .dht import KademliaNode, generate_node_id, id_to_hex
from .file import ChunkStorage, FileManifest, create_manifest
from .transfer import ChunkUploader, FileDownloader, TransferServer
from .discovery import DiscoveryManager, DiscoveredPeer

logger = logging.getLogger(__name__)


def info_hash_to_dht_key(info_hash: str) -> bytes:
    """
    Convert a SHA-256 info_hash (32 bytes) to a DHT key (20 bytes).
    
    Kademlia uses 160-bit (20 byte) keys, but SHA-256 produces 256-bit (32 byte) hashes.
    We use SHA-1 of the info_hash to get a 20-byte key.
    """
    info_hash_bytes = bytes.fromhex(info_hash)
    return hashlib.sha1(info_hash_bytes).digest()


@dataclass
class NodeConfig:
    """Configuration for a P2P node."""
    # Network
    host: str = '0.0.0.0'
    dht_port: int = 8468
    transfer_port: int = 8469
    
    # Storage
    data_dir: Path = Path('./p2p_data')
    
    # Node identity
    node_id: Optional[bytes] = None  # Generated if not provided
    
    # Bootstrap
    bootstrap_nodes: List[Tuple[str, int]] = None
    auto_discover: bool = True  # Use mDNS/broadcast discovery


class P2PNode:
    """
    A complete P2P file sharing node.
    
    Combines all components into a unified interface:
    - share(file_path): Share a file with the network
    - download(info_hash): Download a file from the network  
    - search(query): Search for files (future)
    - list_files(): List locally shared files
    """
    
    def __init__(self, config: NodeConfig = None):
        """
        Initialize a P2P node.
        
        Args:
            config: Node configuration (uses defaults if not provided)
        """
        self.config = config or NodeConfig()
        
        # Generate or use provided node ID
        self.node_id = self.config.node_id or generate_node_id()
        self.node_id_hex = id_to_hex(self.node_id)
        
        # Create data directory
        self.data_dir = Path(self.config.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.storage = ChunkStorage(self.data_dir)
        
        self.dht = KademliaNode(
            node_id=self.node_id,
            port=self.config.dht_port
        )
        
        self.uploader = ChunkUploader(
            storage=self.storage,
            host=self.config.host,
            port=self.config.transfer_port
        )
        
        self.downloader = FileDownloader(
            storage=self.storage,
            max_concurrent=5
        )
        
        self.discovery = DiscoveryManager(
            node_id=self.node_id_hex,
            dht_port=self.config.dht_port,
            transfer_port=self.config.transfer_port
        )
        
        # State
        self._running = False
        
        # Wire up discovery to DHT
        self.discovery.on_peer_change(self._on_peer_discovered)
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    async def start(self):
        """
        Start the P2P node.
        
        This starts all services:
        1. DHT for peer/file discovery
        2. Transfer server for uploads
        3. LAN discovery (mDNS/broadcast)
        4. Bootstrap into the network
        """
        if self._running:
            return
        
        logger.info(f"Starting P2P node {self.node_id_hex[:16]}...")
        
        # Start DHT
        await self.dht.start(self.config.host)
        
        # Start transfer server
        await self.uploader.start()
        
        # Start LAN discovery
        if self.config.auto_discover:
            await self.discovery.start()
        
        self._running = True
        
        # Bootstrap into the network
        await self._bootstrap()
        
        logger.info(f"P2P node started successfully")
        logger.info(f"  Node ID: {self.node_id_hex[:16]}...")
        logger.info(f"  DHT Port: {self.config.dht_port}")
        logger.info(f"  Transfer Port: {self.config.transfer_port}")
        logger.info(f"  Data Dir: {self.data_dir}")
    
    async def stop(self):
        """Stop the P2P node."""
        if not self._running:
            return
        
        logger.info("Stopping P2P node...")
        
        self._running = False
        
        await self.discovery.stop()
        await self.uploader.stop()
        await self.dht.stop()
        
        logger.info("P2P node stopped")
    
    async def _bootstrap(self):
        """Bootstrap into the P2P network."""
        bootstrap_nodes = []
        
        # Add configured bootstrap nodes
        if self.config.bootstrap_nodes:
            bootstrap_nodes.extend(self.config.bootstrap_nodes)
        
        # Wait for discovery
        if self.config.auto_discover:
            logger.info("Discovering peers on LAN...")
            await self.discovery.discover(timeout=3.0)
            discovered = self.discovery.get_bootstrap_nodes()
            bootstrap_nodes.extend(discovered)
        
        if bootstrap_nodes:
            logger.info(f"Bootstrapping with {len(bootstrap_nodes)} nodes...")
            await self.dht.bootstrap(bootstrap_nodes)
        else:
            logger.info("No bootstrap nodes found, running as first node")
    
    def _on_peer_discovered(self, peer: DiscoveredPeer, is_added: bool):
        """Handle peer discovery events."""
        if is_added and self._running:
            # Add to DHT routing table
            asyncio.create_task(
                self.dht.ping(peer.ip, peer.dht_port)
            )
    
    # === File Operations ===
    
    async def share(self, file_path: Path, description: str = "") -> FileManifest:
        """
        Share a file with the network.
        
        This will:
        1. Chunk the file and store locally
        2. Create a manifest
        3. Announce to the DHT
        
        Args:
            file_path: Path to the file to share
            description: Optional description
        
        Returns:
            FileManifest with info_hash for sharing
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        logger.info(f"Sharing file: {file_path.name}")
        
        # Create manifest and store chunks
        manifest = await self.storage.store_file(file_path)
        manifest.description = description
        manifest.created_by = self.node_id_hex
        
        # Store updated manifest
        await self.storage.store_manifest(manifest)
        
        # Announce to DHT (convert 32-byte SHA-256 to 20-byte DHT key)
        dht_key = info_hash_to_dht_key(manifest.info_hash)
        await self.dht.announce_peer(
            dht_key, 
            self.config.transfer_port
        )
        
        # Also store manifest in DHT for discovery
        await self.dht.store(dht_key, manifest.to_json())
        
        logger.info(f"Shared {manifest.name} with info_hash: {manifest.info_hash[:16]}...")
        
        return manifest
    
    async def download(self, info_hash: str, output_path: Path = None,
                      progress_callback: Callable = None) -> Optional[Path]:
        """
        Download a file from the network.
        
        Args:
            info_hash: SHA-256 hash of the file
            output_path: Where to save the file (default: data_dir/files/)
            progress_callback: Optional callback for progress updates
        
        Returns:
            Path to downloaded file, or None if failed
        """
        logger.info(f"Downloading file: {info_hash[:16]}...")
        
        # Convert info_hash to DHT key (20 bytes)
        dht_key = info_hash_to_dht_key(info_hash)
        
        # First try to get manifest from DHT
        manifest_json = await self.dht.find_value(dht_key)
        
        manifest = None
        if manifest_json:
            try:
                manifest = FileManifest.from_json(manifest_json)
                logger.info(f"Got manifest from DHT: {manifest.name}")
            except Exception:
                pass
        
        # Find peers who have this file
        peers = await self.dht.get_peers(dht_key)
        
        if not peers:
            logger.error("No peers found for this file")
            return None
        
        logger.info(f"Found {len(peers)} peers with the file")
        
        # If we don't have manifest, try to get from peers
        if manifest is None:
            for ip, port in peers:
                manifest = await self.downloader.chunk_downloader.download_manifest(
                    ip, port, info_hash
                )
                if manifest:
                    break
        
        if manifest is None:
            logger.error("Could not get file manifest")
            return None
        
        # Peers from get_peers already have the transfer port
        # (announce_peer stores the transfer port, not DHT port)
        transfer_peers = list(peers)
        
        # Download the file
        result = await self.downloader.download_file(
            manifest=manifest,
            peers=transfer_peers,
            progress_callback=progress_callback,
            output_path=output_path
        )
        
        return result
    
    async def list_shared_files(self) -> List[FileManifest]:
        """List all files we're sharing."""
        return await self.storage.list_manifests()
    
    async def get_file_info(self, info_hash: str) -> Optional[FileManifest]:
        """Get information about a specific file."""
        return await self.storage.get_manifest(info_hash)
    
    async def remove_shared_file(self, info_hash: str) -> bool:
        """Stop sharing a file."""
        # Remove manifest
        return await self.storage.delete_manifest(info_hash)
    
    # === Network Info ===
    
    def get_peers(self) -> List[DiscoveredPeer]:
        """Get list of discovered peers."""
        return self.discovery.get_peers()
    
    def get_dht_stats(self) -> dict:
        """Get DHT statistics."""
        return self.dht.get_stats()
    
    async def get_storage_stats(self) -> dict:
        """Get storage statistics."""
        stats = await self.storage.get_stats()
        return {
            'chunks': stats.total_chunks,
            'bytes': stats.total_bytes,
            'manifests': stats.manifest_count,
        }
    
    def get_full_stats(self) -> dict:
        """Get complete node statistics."""
        return {
            'node_id': self.node_id_hex,
            'running': self._running,
            'dht': self.dht.get_stats(),
            'discovery': self.discovery.get_stats(),
            'uploader': self.uploader.get_stats(),
            'downloader': self.downloader.get_stats(),
        }


async def run_node(config: NodeConfig = None):
    """
    Run a P2P node (convenience function).
    
    Starts the node and runs until interrupted.
    """
    node = P2PNode(config)
    
    try:
        await node.start()
        
        # Keep running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        await node.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_node())


