"""
Kademlia DHT Node Implementation

This is the main DHT node that coordinates all Kademlia operations.

Design Decision: Iterative vs Recursive Lookups
===============================================

Options:
1. Recursive: Each node forwards the query deeper
   - Less control over the process
   - Node doing lookup doesn't learn about network
   
2. Iterative: Initiator queries each hop directly
   - More control and visibility
   - Learns about more nodes
   - Can parallelize better

Decision: Iterative (α-parallel)
- We control the lookup process
- We learn about nodes for our routing table
- Can do α=3 parallel queries for speed
- Standard Kademlia approach
"""

import asyncio
import logging
import time
from typing import Optional, List, Dict, Any, Tuple, Set
from dataclasses import dataclass

from .utils import (
    ID_BITS, generate_node_id, xor_distance, id_to_hex,
    sort_by_distance, hex_to_id
)
from .routing import RoutingTable, NodeInfo, K, ALPHA
from .protocol import (
    DHTProtocol, Message, MessageType,
    create_ping, create_pong,
    create_find_node, create_find_node_response,
    create_store, create_store_response,
    create_find_value, create_find_value_response,
    create_announce_peer, create_get_peers, create_get_peers_response,
)

logger = logging.getLogger(__name__)


@dataclass
class LookupResult:
    """Result of a DHT lookup operation."""
    target_id: bytes
    closest_nodes: List[NodeInfo]
    value: Optional[Any] = None
    found: bool = False


class KademliaNode:
    """
    A Kademlia DHT node.
    
    This is the main entry point for DHT operations:
    - Join the network via bootstrap nodes
    - Store and retrieve values
    - Announce and find peers for files
    
    The node maintains:
    - Routing table with k-buckets
    - Local key-value storage
    - Peer announcements for file sharing
    """
    
    def __init__(self, node_id: bytes = None, port: int = 8468):
        """
        Initialize a Kademlia node.
        
        Args:
            node_id: Optional specific node ID (generated if not provided)
            port: UDP port for DHT protocol
        """
        self.node_id = node_id or generate_node_id()
        self.port = port
        self.ip: Optional[str] = None
        
        # Core components
        self.routing_table = RoutingTable(self.node_id)
        self.protocol: Optional[DHTProtocol] = None
        self.transport: Optional[asyncio.DatagramTransport] = None
        
        # Local storage
        self._storage: Dict[bytes, Any] = {}  # key -> value
        self._storage_timestamps: Dict[bytes, float] = {}  # key -> store time
        
        # Peer storage (for file sharing)
        # info_hash -> set of (ip, port, timestamp)
        self._peers: Dict[bytes, Set[Tuple[str, int, float]]] = {}
        
        # State
        self._running = False
        self._bootstrap_complete = False
    
    @property
    def node_id_hex(self) -> str:
        """Return node ID as hex string (for display)."""
        return id_to_hex(self.node_id)
    
    @property
    def address(self) -> Tuple[str, int]:
        """Return our (ip, port) tuple."""
        return (self.ip or '0.0.0.0', self.port)
    
    async def start(self, host: str = '0.0.0.0'):
        """
        Start the DHT node.
        
        Binds to UDP port and starts listening for messages.
        """
        if self._running:
            return
        
        self.ip = host
        
        # Create UDP endpoint
        loop = asyncio.get_event_loop()
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: DHTProtocol(self.node_id, self._handle_message),
            local_addr=(host, self.port),
        )
        
        self._running = True
        logger.info(f"Kademlia node started: {self.node_id_hex[:16]}... on {host}:{self.port}")
        
        # Start periodic tasks
        asyncio.create_task(self._periodic_refresh())
    
    async def stop(self):
        """Stop the DHT node."""
        self._running = False
        if self.transport:
            self.transport.close()
            self.transport = None
        logger.info("Kademlia node stopped")
    
    async def bootstrap(self, bootstrap_nodes: List[Tuple[str, int]]):
        """
        Join the DHT network via bootstrap nodes.
        
        Process:
        1. Ping bootstrap nodes to add them to routing table
        2. Do a lookup for our own ID to populate routing table
        3. Refresh all k-buckets
        
        Args:
            bootstrap_nodes: List of (ip, port) tuples
        """
        if not bootstrap_nodes:
            logger.warning("No bootstrap nodes provided")
            return
        
        logger.info(f"Bootstrapping with {len(bootstrap_nodes)} nodes")
        
        # Ping all bootstrap nodes
        ping_tasks = []
        for ip, port in bootstrap_nodes:
            ping_tasks.append(self.ping(ip, port))
        
        results = await asyncio.gather(*ping_tasks, return_exceptions=True)
        successful = sum(1 for r in results if r is True)
        logger.info(f"Bootstrap pings: {successful}/{len(bootstrap_nodes)} responded")
        
        if successful == 0:
            logger.warning("No bootstrap nodes responded")
            return
        
        # Lookup our own ID to find nearby nodes
        await self.find_node(self.node_id)
        
        # Refresh buckets to populate routing table
        await self._refresh_buckets()
        
        self._bootstrap_complete = True
        stats = self.routing_table.get_stats()
        logger.info(f"Bootstrap complete: {stats['total_nodes']} nodes in routing table")
    
    # === Public DHT Operations ===
    
    async def ping(self, ip: str, port: int) -> bool:
        """
        Ping a node to check if it's alive.
        
        Returns True if node responded.
        """
        msg = create_ping(self.node_id)
        response = await self.protocol.send_request(msg, (ip, port))
        
        if response and response.type == MessageType.PONG:
            # Add responding node to routing table
            node = NodeInfo(
                node_id=response.sender_id,
                ip=ip,
                port=port,
            )
            await self.routing_table.add_node(node)
            return True
        
        return False
    
    async def find_node(self, target_id: bytes) -> List[NodeInfo]:
        """
        Find the K closest nodes to a target ID.
        
        Uses iterative α-parallel lookup.
        """
        result = await self._iterative_lookup(target_id, find_value=False)
        return result.closest_nodes
    
    async def find_value(self, key: bytes) -> Optional[Any]:
        """
        Find a value in the DHT.
        
        Returns the value if found, None otherwise.
        """
        # Check local storage first
        if key in self._storage:
            return self._storage[key]
        
        result = await self._iterative_lookup(key, find_value=True)
        return result.value if result.found else None
    
    async def store(self, key: bytes, value: Any) -> bool:
        """
        Store a value in the DHT.
        
        Stores on K closest nodes to the key.
        """
        # Find K closest nodes to the key
        closest_nodes = await self.find_node(key)
        
        if not closest_nodes:
            # Store locally if we don't know any nodes
            self._storage[key] = value
            self._storage_timestamps[key] = time.time()
            return True
        
        # Store on all closest nodes (including ourselves if we're close)
        store_tasks = []
        for node in closest_nodes:
            store_tasks.append(self._store_on_node(node, key, value))
        
        # Also store locally
        self._storage[key] = value
        self._storage_timestamps[key] = time.time()
        
        results = await asyncio.gather(*store_tasks, return_exceptions=True)
        successful = sum(1 for r in results if r is True)
        
        logger.debug(f"Stored key on {successful}/{len(closest_nodes)} nodes")
        return successful > 0
    
    async def announce_peer(self, info_hash: bytes, port: int) -> int:
        """
        Announce that we have a file available.
        
        Args:
            info_hash: SHA-256 hash of the file
            port: Port where we're serving the file
        
        Returns:
            Number of nodes we announced to
        """
        # Find nodes closest to the info_hash
        closest_nodes = await self.find_node(info_hash)
        
        # Also store locally
        if info_hash not in self._peers:
            self._peers[info_hash] = set()
        self._peers[info_hash].add((self.ip, port, time.time()))
        
        if not closest_nodes:
            return 0
        
        # Announce to all closest nodes
        announce_tasks = []
        for node in closest_nodes:
            announce_tasks.append(self._announce_to_node(node, info_hash, port))
        
        results = await asyncio.gather(*announce_tasks, return_exceptions=True)
        successful = sum(1 for r in results if r is True)
        
        logger.info(f"Announced file to {successful}/{len(closest_nodes)} nodes")
        return successful
    
    async def get_peers(self, info_hash: bytes) -> List[Tuple[str, int]]:
        """
        Find peers who have a specific file.
        
        Args:
            info_hash: SHA-256 hash of the file
        
        Returns:
            List of (ip, port) tuples for peers with the file
        """
        all_peers = set()
        
        # Check local storage first
        if info_hash in self._peers:
            for ip, port, timestamp in self._peers[info_hash]:
                all_peers.add((ip, port))
        
        # Query the network
        result = await self._iterative_get_peers(info_hash)
        all_peers.update(result)
        
        return list(all_peers)
    
    # === Internal Operations ===
    
    async def _handle_message(self, message: Message, 
                             addr: Tuple[str, int]) -> Optional[Message]:
        """
        Handle an incoming DHT message.
        
        This is called by the protocol for each received message.
        """
        # Add sender to routing table
        sender_node = NodeInfo(
            node_id=message.sender_id,
            ip=addr[0],
            port=addr[1],
        )
        await self.routing_table.add_node(sender_node)
        
        # Route to appropriate handler
        handlers = {
            MessageType.PING: self._handle_ping,
            MessageType.FIND_NODE: self._handle_find_node,
            MessageType.FIND_VALUE: self._handle_find_value,
            MessageType.STORE: self._handle_store,
            MessageType.ANNOUNCE_PEER: self._handle_announce_peer,
            MessageType.GET_PEERS: self._handle_get_peers,
        }
        
        handler = handlers.get(message.type)
        if handler:
            return await handler(message, addr)
        
        return None
    
    async def _handle_ping(self, message: Message, 
                          addr: Tuple[str, int]) -> Message:
        """Handle PING request."""
        return create_pong(self.node_id, message)
    
    async def _handle_find_node(self, message: Message,
                                addr: Tuple[str, int]) -> Message:
        """Handle FIND_NODE request."""
        target_id = hex_to_id(message.payload['target_id'])
        closest = self.routing_table.find_closest_nodes(target_id)
        return create_find_node_response(self.node_id, message, closest)
    
    async def _handle_find_value(self, message: Message,
                                 addr: Tuple[str, int]) -> Message:
        """Handle FIND_VALUE request."""
        key = hex_to_id(message.payload['key'])
        
        # Check if we have the value
        if key in self._storage:
            return create_find_value_response(
                self.node_id, message, 
                value=self._storage[key]
            )
        
        # Return closest nodes instead
        closest = self.routing_table.find_closest_nodes(key)
        return create_find_value_response(
            self.node_id, message,
            nodes=closest
        )
    
    async def _handle_store(self, message: Message,
                           addr: Tuple[str, int]) -> Message:
        """Handle STORE request."""
        key = hex_to_id(message.payload['key'])
        value = message.payload['value']
        
        self._storage[key] = value
        self._storage_timestamps[key] = time.time()
        
        return create_store_response(self.node_id, message, success=True)
    
    async def _handle_announce_peer(self, message: Message,
                                    addr: Tuple[str, int]) -> Message:
        """Handle ANNOUNCE_PEER request."""
        info_hash = hex_to_id(message.payload['info_hash'])
        port = message.payload['port']
        
        # Store the peer info
        if info_hash not in self._peers:
            self._peers[info_hash] = set()
        
        self._peers[info_hash].add((addr[0], port, time.time()))
        
        return Message(
            type=MessageType.ANNOUNCE_RESPONSE,
            sender_id=self.node_id,
            message_id=message.message_id,
            payload={'success': True},
        )
    
    async def _handle_get_peers(self, message: Message,
                                addr: Tuple[str, int]) -> Message:
        """Handle GET_PEERS request."""
        info_hash = hex_to_id(message.payload['info_hash'])
        
        # Check if we have peers for this file
        if info_hash in self._peers:
            peers = [(ip, port) for ip, port, _ in self._peers[info_hash]]
            return create_get_peers_response(
                self.node_id, message,
                peers=peers
            )
        
        # Return closest nodes
        closest = self.routing_table.find_closest_nodes(info_hash)
        return create_get_peers_response(
            self.node_id, message,
            nodes=closest
        )
    
    async def _iterative_lookup(self, target_id: bytes, 
                               find_value: bool = False) -> LookupResult:
        """
        Perform iterative lookup for a target ID.
        
        This is the core Kademlia lookup algorithm:
        1. Start with K closest known nodes
        2. Send parallel (α=3) queries
        3. As responses come in, query newly discovered closer nodes
        4. Stop when we've queried the K closest we know of
        """
        # Start with closest nodes we know
        closest = self.routing_table.find_closest_nodes(target_id, K)
        
        if not closest:
            return LookupResult(target_id=target_id, closest_nodes=[])
        
        # Track state
        queried: Set[bytes] = set()
        pending: Dict[bytes, NodeInfo] = {n.node_id: n for n in closest}
        found_value = None
        
        while pending:
            # Select α nodes to query that we haven't queried yet
            to_query = []
            for node_id, node in list(pending.items()):
                if node_id not in queried:
                    to_query.append(node)
                    if len(to_query) >= ALPHA:
                        break
            
            if not to_query:
                break
            
            # Send queries in parallel
            tasks = []
            for node in to_query:
                queried.add(node.node_id)
                if find_value:
                    tasks.append(self._send_find_value(node, target_id))
                else:
                    tasks.append(self._send_find_node(node, target_id))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Mark node as failed
                    await self.routing_table.remove_node(to_query[i].node_id)
                    continue
                
                if result is None:
                    continue
                
                # Check if we found the value
                if find_value and result.get('value') is not None:
                    found_value = result['value']
                    break
                
                # Add new nodes to pending
                for node_dict in result.get('nodes', []):
                    node = NodeInfo.from_dict(node_dict)
                    if node.node_id not in queried:
                        pending[node.node_id] = node
                        await self.routing_table.add_node(node)
            
            if found_value is not None:
                break
            
            # Remove queried nodes from pending
            for node in to_query:
                pending.pop(node.node_id, None)
        
        # Get final K closest
        all_seen = list(queried)
        final_closest = []
        for node_id in all_seen:
            node = self.routing_table.get_node(node_id)
            if node:
                final_closest.append(node)
        
        final_closest.sort(key=lambda n: xor_distance(target_id, n.node_id))
        final_closest = final_closest[:K]
        
        return LookupResult(
            target_id=target_id,
            closest_nodes=final_closest,
            value=found_value,
            found=found_value is not None,
        )
    
    async def _send_find_node(self, node: NodeInfo, 
                             target_id: bytes) -> Optional[Dict]:
        """Send FIND_NODE to a specific node."""
        msg = create_find_node(self.node_id, target_id)
        response = await self.protocol.send_request(msg, node.address)
        
        if response and response.type == MessageType.FIND_NODE_RESPONSE:
            await self.routing_table.mark_node_seen(node.node_id)
            return response.payload
        
        return None
    
    async def _send_find_value(self, node: NodeInfo,
                               key: bytes) -> Optional[Dict]:
        """Send FIND_VALUE to a specific node."""
        msg = create_find_value(self.node_id, key)
        response = await self.protocol.send_request(msg, node.address)
        
        if response and response.type == MessageType.FIND_VALUE_RESPONSE:
            await self.routing_table.mark_node_seen(node.node_id)
            return response.payload
        
        return None
    
    async def _store_on_node(self, node: NodeInfo, key: bytes, 
                            value: Any) -> bool:
        """Store a key-value pair on a specific node."""
        msg = create_store(self.node_id, key, value)
        response = await self.protocol.send_request(msg, node.address)
        
        if response and response.type == MessageType.STORE_RESPONSE:
            return response.payload.get('success', False)
        
        return False
    
    async def _announce_to_node(self, node: NodeInfo, info_hash: bytes,
                                port: int) -> bool:
        """Announce a file to a specific node."""
        msg = create_announce_peer(self.node_id, info_hash, port)
        response = await self.protocol.send_request(msg, node.address)
        
        if response and response.type == MessageType.ANNOUNCE_RESPONSE:
            return response.payload.get('success', False)
        
        return False
    
    async def _iterative_get_peers(self, info_hash: bytes) -> Set[Tuple[str, int]]:
        """Find peers for a file through iterative lookup."""
        all_peers = set()
        
        # Similar to iterative lookup but for peers
        closest = self.routing_table.find_closest_nodes(info_hash, K)
        
        if not closest:
            return all_peers
        
        queried: Set[bytes] = set()
        pending: Dict[bytes, NodeInfo] = {n.node_id: n for n in closest}
        
        while pending:
            to_query = []
            for node_id, node in list(pending.items()):
                if node_id not in queried:
                    to_query.append(node)
                    if len(to_query) >= ALPHA:
                        break
            
            if not to_query:
                break
            
            tasks = []
            for node in to_query:
                queried.add(node.node_id)
                tasks.append(self._send_get_peers(node, info_hash))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if isinstance(result, Exception) or result is None:
                    continue
                
                # Collect peers
                for peer in result.get('peers', []):
                    all_peers.add((peer['ip'], peer['port']))
                
                # Add new nodes
                for node_dict in result.get('nodes', []):
                    node = NodeInfo.from_dict(node_dict)
                    if node.node_id not in queried:
                        pending[node.node_id] = node
            
            for node in to_query:
                pending.pop(node.node_id, None)
        
        return all_peers
    
    async def _send_get_peers(self, node: NodeInfo,
                              info_hash: bytes) -> Optional[Dict]:
        """Send GET_PEERS to a specific node."""
        msg = create_get_peers(self.node_id, info_hash)
        response = await self.protocol.send_request(msg, node.address)
        
        if response and response.type == MessageType.GET_PEERS_RESPONSE:
            return response.payload
        
        return None
    
    async def _periodic_refresh(self):
        """Periodically refresh routing table and republish data."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Every minute
                
                if not self._bootstrap_complete:
                    continue
                
                await self._refresh_buckets()
                await self._republish_data()
                await self._cleanup_old_peers()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic refresh: {e}")
    
    async def _refresh_buckets(self):
        """Refresh k-buckets by looking up random IDs."""
        targets = self.routing_table.get_refresh_targets()
        
        for target in targets[:5]:  # Limit to 5 refreshes per cycle
            await self.find_node(target)
    
    async def _republish_data(self):
        """Republish stored data to ensure availability."""
        now = time.time()
        max_age = 3600  # Republish every hour
        
        for key, timestamp in list(self._storage_timestamps.items()):
            if now - timestamp > max_age:
                value = self._storage.get(key)
                if value is not None:
                    await self.store(key, value)
    
    async def _cleanup_old_peers(self):
        """Remove old peer announcements."""
        now = time.time()
        max_age = 1800  # 30 minutes
        
        for info_hash in list(self._peers.keys()):
            self._peers[info_hash] = {
                (ip, port, ts) 
                for ip, port, ts in self._peers[info_hash]
                if now - ts < max_age
            }
            
            if not self._peers[info_hash]:
                del self._peers[info_hash]
    
    def get_stats(self) -> Dict:
        """Get node statistics."""
        routing_stats = self.routing_table.get_stats()
        return {
            'node_id': self.node_id_hex,
            'address': f"{self.ip}:{self.port}",
            'routing_table': routing_stats,
            'stored_values': len(self._storage),
            'tracked_files': len(self._peers),
            'running': self._running,
            'bootstrapped': self._bootstrap_complete,
        }



