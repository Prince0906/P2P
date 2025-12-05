"""
UDP Broadcast Discovery

Design Decision: Broadcast vs Multicast
========================================

Options:
1. UDP Broadcast (255.255.255.255 or subnet broadcast)
   - Simple, works on most LANs
   - Doesn't cross routers
   - Some networks block it
   
2. UDP Multicast
   - Can cross routers (if configured)
   - More complex setup
   - Better for larger networks

Decision: UDP Broadcast to subnet
- Simplest approach
- Works on typical university subnet
- Good fallback when mDNS is blocked
- Use subnet broadcast address for efficiency

Protocol:
- DISCOVER: Node looking for peers
- ANNOUNCE: Node announcing itself
- Simple JSON messages
"""

import asyncio
import json
import socket
import logging
import time
from typing import Callable, Optional, List, Dict, Tuple, Set
from dataclasses import dataclass

from .mdns import DiscoveredPeer, PeerCallback

logger = logging.getLogger(__name__)

# Broadcast port (different from DHT port to avoid confusion)
BROADCAST_PORT = 8470

# Discovery message types
MSG_DISCOVER = "DISCOVER"
MSG_ANNOUNCE = "ANNOUNCE"


class BroadcastDiscovery:
    """
    UDP broadcast-based peer discovery.
    
    Fallback discovery method when mDNS is not available or blocked.
    """
    
    def __init__(self, node_id: str, dht_port: int, transfer_port: int,
                 broadcast_port: int = BROADCAST_PORT):
        """
        Initialize broadcast discovery.
        
        Args:
            node_id: Our node's ID (hex string)
            dht_port: Port for DHT protocol
            transfer_port: Port for file transfers
            broadcast_port: Port for discovery broadcasts
        """
        self.node_id = node_id
        self.dht_port = dht_port
        self.transfer_port = transfer_port
        self.broadcast_port = broadcast_port
        
        self._socket: Optional[socket.socket] = None
        self._peers: Dict[str, DiscoveredPeer] = {}
        self._callbacks: List[PeerCallback] = []
        
        self._running = False
        self._receive_task: Optional[asyncio.Task] = None
        self._announce_task: Optional[asyncio.Task] = None
        
        # Peer timeout (remove if not seen in this time)
        self._peer_timeout = 120  # seconds
    
    def on_peer_change(self, callback: PeerCallback):
        """Register a callback for peer discovery events."""
        self._callbacks.append(callback)
    
    def get_peers(self) -> List[DiscoveredPeer]:
        """Get list of discovered peers."""
        return list(self._peers.values())
    
    async def start(self):
        """Start broadcast discovery."""
        if self._running:
            return
        
        try:
            # Create UDP socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Try to set SO_REUSEPORT if available (for macOS/Linux)
            try:
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                pass
            
            # Bind to receive broadcasts
            self._socket.bind(('', self.broadcast_port))
            self._socket.setblocking(False)
            
            self._running = True
            
            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            # Start periodic announce
            self._announce_task = asyncio.create_task(self._announce_loop())
            
            # Send initial discovery
            await self._send_discover()
            
            logger.info(f"Broadcast discovery started on port {self.broadcast_port}")
            
        except Exception as e:
            logger.error(f"Failed to start broadcast discovery: {e}")
            await self.stop()
    
    async def stop(self):
        """Stop broadcast discovery."""
        self._running = False
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        
        if self._announce_task:
            self._announce_task.cancel()
            try:
                await self._announce_task
            except asyncio.CancelledError:
                pass
            self._announce_task = None
        
        if self._socket:
            self._socket.close()
            self._socket = None
        
        self._peers.clear()
        logger.info("Broadcast discovery stopped")
    
    async def _receive_loop(self):
        """Receive and process broadcast messages."""
        loop = asyncio.get_event_loop()
        
        while self._running:
            try:
                # Use asyncio to receive
                data, addr = await loop.sock_recvfrom(self._socket, 4096)
                await self._handle_message(data, addr)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.error(f"Error receiving broadcast: {e}")
                    await asyncio.sleep(1)
    
    async def _announce_loop(self):
        """Periodically announce our presence."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Announce every 30 seconds
                await self._send_announce()
                await self._cleanup_stale_peers()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in announce loop: {e}")
    
    async def _handle_message(self, data: bytes, addr: Tuple[str, int]):
        """Handle a received broadcast message."""
        try:
            message = json.loads(data.decode('utf-8'))
            msg_type = message.get('type')
            
            if msg_type == MSG_DISCOVER:
                # Someone is looking for peers - announce ourselves
                await self._send_announce()
                
            elif msg_type == MSG_ANNOUNCE:
                # Someone is announcing themselves
                await self._handle_announce(message, addr[0])
                
        except json.JSONDecodeError:
            pass  # Ignore malformed messages
        except Exception as e:
            logger.error(f"Error handling broadcast message: {e}")
    
    async def _handle_announce(self, message: dict, sender_ip: str):
        """Handle an announce message."""
        node_id = message.get('node_id')
        dht_port = message.get('dht_port')
        transfer_port = message.get('transfer_port')
        
        if not node_id or not dht_port:
            return
        
        # Skip ourselves
        if node_id == self.node_id:
            return
        
        # Create or update peer
        is_new = node_id not in self._peers
        
        peer = DiscoveredPeer(
            node_id=node_id,
            ip=sender_ip,
            dht_port=dht_port,
            transfer_port=transfer_port or (dht_port + 1),
            discovered_at=time.time(),
        )
        
        self._peers[node_id] = peer
        
        if is_new:
            logger.info(f"Broadcast: Discovered peer {node_id[:16]}... at {sender_ip}")
            
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(peer, True)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
    
    async def _send_discover(self):
        """Send a discovery request."""
        message = {
            'type': MSG_DISCOVER,
            'node_id': self.node_id,
            'dht_port': self.dht_port,
            'transfer_port': self.transfer_port,
        }
        await self._broadcast(message)
    
    async def _send_announce(self):
        """Send an announcement."""
        message = {
            'type': MSG_ANNOUNCE,
            'node_id': self.node_id,
            'dht_port': self.dht_port,
            'transfer_port': self.transfer_port,
        }
        await self._broadcast(message)
    
    async def _broadcast(self, message: dict):
        """Send a broadcast message."""
        if not self._socket:
            return
        
        try:
            data = json.dumps(message).encode('utf-8')
            
            # Get broadcast addresses
            broadcast_addrs = self._get_broadcast_addresses()
            
            loop = asyncio.get_event_loop()
            for addr in broadcast_addrs:
                try:
                    await loop.sock_sendto(
                        self._socket, data, (addr, self.broadcast_port)
                    )
                except Exception:
                    pass  # Some addresses may not work
                    
        except Exception as e:
            logger.error(f"Error sending broadcast: {e}")
    
    def _get_broadcast_addresses(self) -> List[str]:
        """Get broadcast addresses for all interfaces."""
        addresses = ['255.255.255.255']  # Global broadcast
        
        try:
            import netifaces
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        if 'broadcast' in addr_info:
                            addresses.append(addr_info['broadcast'])
        except ImportError:
            # netifaces not available, use simple approach
            # Try to get subnet broadcast from local IP
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                
                # Assume /24 subnet
                parts = local_ip.split('.')
                parts[3] = '255'
                addresses.append('.'.join(parts))
            except Exception:
                pass
        
        return list(set(addresses))
    
    async def _cleanup_stale_peers(self):
        """Remove peers that haven't been seen recently."""
        now = time.time()
        stale = []
        
        for node_id, peer in self._peers.items():
            if now - peer.discovered_at > self._peer_timeout:
                stale.append(node_id)
        
        for node_id in stale:
            peer = self._peers.pop(node_id)
            logger.info(f"Broadcast: Peer timed out {node_id[:16]}...")
            
            for callback in self._callbacks:
                try:
                    callback(peer, False)
                except Exception as e:
                    logger.error(f"Callback error: {e}")



