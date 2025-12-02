"""
Discovery Module - Peer Discovery on LAN

Provides multiple methods to discover other P2P nodes:
- mDNS (Bonjour/Zeroconf) - Zero-config discovery
- UDP Broadcast - Simple fallback
"""

from .mdns import MDNSDiscovery, DiscoveredPeer
from .broadcast import BroadcastDiscovery
from .manager import DiscoveryManager

__all__ = [
    'MDNSDiscovery',
    'BroadcastDiscovery',
    'DiscoveryManager',
    'DiscoveredPeer',
]

