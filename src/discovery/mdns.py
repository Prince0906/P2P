"""
mDNS Discovery

Design Decision: Service Discovery Protocol
============================================

Options Considered:
1. mDNS/DNS-SD (Zeroconf/Bonjour)
   - Zero configuration needed
   - Works across subnets (sometimes)
   - Standard protocol (RFC 6762, 6763)
   - Used by Apple devices, printers, etc.
   
2. SSDP (Simple Service Discovery Protocol)
   - Used by UPnP
   - Works well on LANs
   - More complex
   
3. WS-Discovery
   - Enterprise focused
   - Too complex for our needs

Decision: mDNS with zeroconf library
- Zero-config: just run and discover
- Proven reliable on university networks
- Easy to implement with zeroconf library
- Fallback to broadcast if mDNS blocked

Service Type: _p2pshare._udp.local.
- Custom service type for our P2P system
- _udp suffix (our DHT uses UDP)
- .local. domain for mDNS
"""

import asyncio
import logging
import socket
from typing import Callable, Optional, List, Dict, Tuple, Set
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)

# Try to import zeroconf
try:
    from zeroconf import ServiceInfo, Zeroconf, ServiceBrowser, ServiceListener
    from zeroconf.asyncio import AsyncZeroconf, AsyncServiceInfo, AsyncServiceBrowser
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False
    logger.warning("zeroconf not available, mDNS discovery disabled")


# Service type for our P2P system
SERVICE_TYPE = "_p2pshare._udp.local."
SERVICE_NAME_PREFIX = "P2PNode-"


@dataclass
class DiscoveredPeer:
    """Information about a discovered peer."""
    node_id: str
    ip: str
    dht_port: int
    transfer_port: int
    discovered_at: float
    
    def __hash__(self):
        return hash((self.node_id, self.ip))
    
    def __eq__(self, other):
        if isinstance(other, DiscoveredPeer):
            return self.node_id == other.node_id and self.ip == other.ip
        return False


# Callback type for peer discovery events
PeerCallback = Callable[[DiscoveredPeer, bool], None]  # (peer, is_added)


class MDNSDiscovery:
    """
    mDNS-based peer discovery using Zeroconf.
    
    Registers our node as a service and discovers other nodes.
    """
    
    def __init__(self, node_id: str, dht_port: int, transfer_port: int):
        """
        Initialize mDNS discovery.
        
        Args:
            node_id: Our node's ID (hex string)
            dht_port: Port for DHT protocol (UDP)
            transfer_port: Port for file transfers (TCP)
        """
        self.node_id = node_id
        self.dht_port = dht_port
        self.transfer_port = transfer_port
        
        self._zeroconf: Optional['AsyncZeroconf'] = None
        self._service_info: Optional['ServiceInfo'] = None
        self._browser: Optional['AsyncServiceBrowser'] = None
        
        # Discovered peers
        self._peers: Dict[str, DiscoveredPeer] = {}  # node_id -> peer
        self._callbacks: List[PeerCallback] = []
        
        self._running = False
    
    @property
    def is_available(self) -> bool:
        """Check if mDNS is available."""
        return ZEROCONF_AVAILABLE
    
    def on_peer_change(self, callback: PeerCallback):
        """Register a callback for peer discovery events."""
        self._callbacks.append(callback)
    
    def get_peers(self) -> List[DiscoveredPeer]:
        """Get list of discovered peers."""
        return list(self._peers.values())
    
    async def start(self):
        """Start mDNS discovery and registration."""
        if not ZEROCONF_AVAILABLE:
            logger.warning("Zeroconf not available, skipping mDNS")
            return
        
        if self._running:
            return
        
        try:
            # Get our IP address
            hostname = socket.gethostname()
            local_ip = self._get_local_ip()
            
            logger.info(f"Starting mDNS discovery (IP: {local_ip})")
            
            # Create zeroconf instance
            self._zeroconf = AsyncZeroconf()
            
            # Create service info for registration
            service_name = f"{SERVICE_NAME_PREFIX}{self.node_id[:16]}.{SERVICE_TYPE}"
            
            self._service_info = ServiceInfo(
                SERVICE_TYPE,
                service_name,
                addresses=[socket.inet_aton(local_ip)],
                port=self.dht_port,
                properties={
                    'node_id': self.node_id,
                    'transfer_port': str(self.transfer_port),
                    'version': '1.0',
                },
                server=f"{hostname}.local.",
            )
            
            # Register our service
            await self._zeroconf.async_register_service(self._service_info)
            logger.info(f"Registered mDNS service: {service_name}")
            
            # Create service browser
            self._browser = AsyncServiceBrowser(
                self._zeroconf.zeroconf,
                SERVICE_TYPE,
                handlers=[self._on_service_state_change]
            )
            
            self._running = True
            logger.info("mDNS discovery started")
            
        except Exception as e:
            logger.error(f"Failed to start mDNS: {e}")
            await self.stop()
    
    async def stop(self):
        """Stop mDNS discovery."""
        self._running = False
        
        # Browser cleanup - handle different zeroconf versions
        if self._browser:
            try:
                # Try cancel() for older versions
                if hasattr(self._browser, 'cancel'):
                    self._browser.cancel()
            except Exception as e:
                logger.debug(f"Browser cleanup: {e}")
            self._browser = None
        
        if self._service_info and self._zeroconf:
            try:
                await self._zeroconf.async_unregister_service(self._service_info)
            except Exception as e:
                logger.debug(f"Service unregister: {e}")
        
        if self._zeroconf:
            try:
                await self._zeroconf.async_close()
            except Exception as e:
                logger.debug(f"Zeroconf close: {e}")
            self._zeroconf = None
        
        self._peers.clear()
        logger.info("mDNS discovery stopped")
    
    def _get_local_ip(self) -> str:
        """Get the local IP address (best guess)."""
        try:
            # Create a socket and connect to a public address
            # This doesn't actually send data, just determines the route
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def _on_service_state_change(self, zeroconf, service_type, name, state_change):
        """Handle service discovery events (synchronous callback)."""
        if not self._running:
            return
        
        # Schedule async handling
        asyncio.create_task(
            self._handle_service_change(zeroconf, service_type, name, state_change)
        )
    
    async def _handle_service_change(self, zeroconf, service_type, name, state_change):
        """Handle service discovery events."""
        from zeroconf import ServiceStateChange
        
        if state_change == ServiceStateChange.Added:
            # Get service info
            info = AsyncServiceInfo(service_type, name)
            await info.async_request(zeroconf, 3000)
            
            if info.addresses:
                # Extract peer info
                node_id = info.properties.get(b'node_id', b'').decode()
                transfer_port = int(info.properties.get(b'transfer_port', b'0'))
                ip = socket.inet_ntoa(info.addresses[0])
                
                # Skip ourselves
                if node_id == self.node_id:
                    return
                
                peer = DiscoveredPeer(
                    node_id=node_id,
                    ip=ip,
                    dht_port=info.port,
                    transfer_port=transfer_port,
                    discovered_at=time.time(),
                )
                
                self._peers[node_id] = peer
                logger.info(f"mDNS: Discovered peer {node_id[:16]}... at {ip}")
                
                # Notify callbacks
                for callback in self._callbacks:
                    try:
                        callback(peer, True)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
        
        elif state_change == ServiceStateChange.Removed:
            # Find and remove the peer
            # Name format: "P2PNode-{id}.{service_type}"
            for node_id, peer in list(self._peers.items()):
                if name.startswith(f"{SERVICE_NAME_PREFIX}{node_id[:16]}"):
                    del self._peers[node_id]
                    logger.info(f"mDNS: Peer removed {node_id[:16]}...")
                    
                    for callback in self._callbacks:
                        try:
                            callback(peer, False)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")
                    break


# Fallback for when zeroconf is not available
class MDNSDiscoveryStub:
    """Stub implementation when zeroconf is not available."""
    
    def __init__(self, *args, **kwargs):
        self._peers = {}
        self._callbacks = []
    
    @property
    def is_available(self) -> bool:
        return False
    
    def on_peer_change(self, callback):
        pass
    
    def get_peers(self) -> List[DiscoveredPeer]:
        return []
    
    async def start(self):
        logger.warning("mDNS not available (zeroconf not installed)")
    
    async def stop(self):
        pass


# Export the appropriate class
if not ZEROCONF_AVAILABLE:
    MDNSDiscovery = MDNSDiscoveryStub


