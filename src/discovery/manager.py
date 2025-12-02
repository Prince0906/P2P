"""
Discovery Manager

Coordinates multiple discovery methods for robust peer finding.
"""

import asyncio
import logging
from typing import List, Dict, Callable, Optional, Set
from dataclasses import dataclass

from .mdns import MDNSDiscovery, DiscoveredPeer, PeerCallback
from .broadcast import BroadcastDiscovery

logger = logging.getLogger(__name__)


class DiscoveryManager:
    """
    Manages peer discovery using multiple methods.
    
    Uses both mDNS and UDP broadcast for redundancy.
    Deduplicates peers discovered via different methods.
    """
    
    def __init__(self, node_id: str, dht_port: int, transfer_port: int):
        """
        Initialize discovery manager.
        
        Args:
            node_id: Our node's ID (hex string)
            dht_port: Port for DHT protocol
            transfer_port: Port for file transfers
        """
        self.node_id = node_id
        self.dht_port = dht_port
        self.transfer_port = transfer_port
        
        # Discovery methods
        self._mdns = MDNSDiscovery(node_id, dht_port, transfer_port)
        self._broadcast = BroadcastDiscovery(node_id, dht_port, transfer_port)
        
        # Consolidated peer list
        self._peers: Dict[str, DiscoveredPeer] = {}
        self._callbacks: List[PeerCallback] = []
        
        # Wire up internal callbacks
        self._mdns.on_peer_change(self._on_mdns_peer)
        self._broadcast.on_peer_change(self._on_broadcast_peer)
        
        self._running = False
    
    def on_peer_change(self, callback: PeerCallback):
        """Register a callback for peer discovery events."""
        self._callbacks.append(callback)
    
    def get_peers(self) -> List[DiscoveredPeer]:
        """Get list of all discovered peers."""
        return list(self._peers.values())
    
    def get_peer(self, node_id: str) -> Optional[DiscoveredPeer]:
        """Get a specific peer by node ID."""
        return self._peers.get(node_id)
    
    def get_bootstrap_nodes(self) -> List[tuple]:
        """Get discovered peers as bootstrap nodes (ip, port) tuples."""
        return [(p.ip, p.dht_port) for p in self._peers.values()]
    
    async def start(self):
        """Start all discovery methods."""
        if self._running:
            return
        
        self._running = True
        logger.info("Starting peer discovery...")
        
        # Start mDNS (may not be available)
        await self._mdns.start()
        
        # Start broadcast (always available)
        await self._broadcast.start()
        
        logger.info("Peer discovery started")
    
    async def stop(self):
        """Stop all discovery methods."""
        self._running = False
        
        await self._mdns.stop()
        await self._broadcast.stop()
        
        self._peers.clear()
        logger.info("Peer discovery stopped")
    
    async def discover(self, timeout: float = 3.0) -> List[DiscoveredPeer]:
        """
        Actively discover peers for a period of time.
        
        Useful for initial bootstrap.
        
        Args:
            timeout: How long to wait for discovery
        
        Returns:
            List of discovered peers
        """
        logger.info(f"Discovering peers for {timeout}s...")
        await asyncio.sleep(timeout)
        peers = self.get_peers()
        logger.info(f"Discovered {len(peers)} peers")
        return peers
    
    def _on_mdns_peer(self, peer: DiscoveredPeer, is_added: bool):
        """Handle peer event from mDNS."""
        self._handle_peer_event(peer, is_added, "mDNS")
    
    def _on_broadcast_peer(self, peer: DiscoveredPeer, is_added: bool):
        """Handle peer event from broadcast."""
        self._handle_peer_event(peer, is_added, "broadcast")
    
    def _handle_peer_event(self, peer: DiscoveredPeer, is_added: bool, source: str):
        """Handle a peer discovery event."""
        if is_added:
            # Check if we already know this peer
            is_new = peer.node_id not in self._peers
            self._peers[peer.node_id] = peer
            
            if is_new:
                # Notify callbacks only for new peers
                for callback in self._callbacks:
                    try:
                        callback(peer, True)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
        else:
            # Only remove if no other discovery method knows about it
            # (check if the other method still has this peer)
            mdns_has = any(p.node_id == peer.node_id for p in self._mdns.get_peers())
            broadcast_has = any(p.node_id == peer.node_id for p in self._broadcast.get_peers())
            
            if not mdns_has and not broadcast_has:
                if peer.node_id in self._peers:
                    del self._peers[peer.node_id]
                    
                    for callback in self._callbacks:
                        try:
                            callback(peer, False)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")
    
    def get_stats(self) -> dict:
        """Get discovery statistics."""
        return {
            'total_peers': len(self._peers),
            'mdns_peers': len(self._mdns.get_peers()),
            'broadcast_peers': len(self._broadcast.get_peers()),
            'mdns_available': self._mdns.is_available,
        }



