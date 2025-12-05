"""
Kademlia Routing Table Implementation

Design Decision: K-Bucket Parameters
====================================

Options Considered for k (bucket size):
1. k=8  - Smaller, faster lookups, less redundancy
2. k=20 - Standard Kademlia (used in BitTorrent)
3. k=32 - More redundancy, slower operations

Decision: k=20
- Standard value from Kademlia paper
- Good balance between redundancy and overhead
- With k=20, probability of all nodes in bucket failing is negligible
- Each lookup touches O(log n) buckets

Options Considered for α (parallel queries):
1. α=1 - Sequential, slow but simple
2. α=3 - Standard Kademlia
3. α=5 - More aggressive parallelism

Decision: α=3
- Standard value, good for LAN with low latency
- Three parallel lookups provide good speed
- Not too aggressive on bandwidth

Bucket Refresh Strategy:
- LRU (Least Recently Used) eviction
- But prefer OLD nodes (they're proven reliable)
- Only replace if old node fails to respond
"""

import time
import asyncio
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple, Set
from collections import OrderedDict

from .utils import (
    ID_BITS, ID_BYTES, xor_distance, get_bucket_index,
    id_to_hex, sort_by_distance
)


# Kademlia constants
K = 20  # Maximum nodes per bucket
ALPHA = 3  # Parallelism parameter for lookups


@dataclass
class NodeInfo:
    """
    Information about a known node in the network.
    
    Stores contact information and metadata for routing.
    """
    node_id: bytes
    ip: str
    port: int
    last_seen: float = field(default_factory=time.time)
    failed_requests: int = 0
    
    def __hash__(self):
        return hash(self.node_id)
    
    def __eq__(self, other):
        if isinstance(other, NodeInfo):
            return self.node_id == other.node_id
        return False
    
    @property
    def address(self) -> Tuple[str, int]:
        """Return (ip, port) tuple for networking."""
        return (self.ip, self.port)
    
    def update_last_seen(self):
        """Mark this node as recently seen."""
        self.last_seen = time.time()
        self.failed_requests = 0
    
    def mark_failed(self):
        """Record a failed communication attempt."""
        self.failed_requests += 1
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for network transmission."""
        return {
            'node_id': self.node_id.hex(),
            'ip': self.ip,
            'port': self.port,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'NodeInfo':
        """Deserialize from dictionary."""
        return cls(
            node_id=bytes.fromhex(data['node_id']),
            ip=data['ip'],
            port=data['port'],
        )


class KBucket:
    """
    A k-bucket holds up to K nodes at a certain distance range.
    
    Key behaviors:
    1. If bucket not full, add new node
    2. If bucket full and new node seen, ping oldest
    3. If oldest responds, move to end (most recent), discard new
    4. If oldest fails, replace with new node
    
    This "prefer old nodes" policy makes the network resistant to churn
    and attacks that try to inject many new nodes.
    """
    
    def __init__(self, k: int = K):
        self.k = k
        # OrderedDict maintains insertion order (oldest first)
        self._nodes: OrderedDict[bytes, NodeInfo] = OrderedDict()
        self._replacement_cache: OrderedDict[bytes, NodeInfo] = OrderedDict()
        self._lock = asyncio.Lock()
    
    @property
    def nodes(self) -> List[NodeInfo]:
        """Return list of nodes (oldest to newest)."""
        return list(self._nodes.values())
    
    @property
    def is_full(self) -> bool:
        """Check if bucket has K nodes."""
        return len(self._nodes) >= self.k
    
    def __len__(self) -> int:
        return len(self._nodes)
    
    def __contains__(self, node_id: bytes) -> bool:
        return node_id in self._nodes
    
    async def add_node(self, node: NodeInfo) -> Optional[NodeInfo]:
        """
        Add a node to the bucket.
        
        Returns:
            - None if node was added or updated
            - NodeInfo of oldest node if bucket is full (needs ping check)
        """
        async with self._lock:
            # If node already exists, move to end (most recent)
            if node.node_id in self._nodes:
                self._nodes.move_to_end(node.node_id)
                self._nodes[node.node_id].update_last_seen()
                return None
            
            # If bucket not full, just add
            if not self.is_full:
                self._nodes[node.node_id] = node
                return None
            
            # Bucket is full - add to replacement cache and return oldest
            self._replacement_cache[node.node_id] = node
            # Keep replacement cache bounded
            while len(self._replacement_cache) > self.k:
                self._replacement_cache.popitem(last=False)
            
            # Return the oldest node for ping verification
            oldest_id = next(iter(self._nodes))
            return self._nodes[oldest_id]
    
    async def remove_node(self, node_id: bytes) -> bool:
        """
        Remove a node (usually after failed ping).
        
        If there are nodes in replacement cache, promote one.
        """
        async with self._lock:
            if node_id not in self._nodes:
                return False
            
            del self._nodes[node_id]
            
            # Try to promote from replacement cache
            if self._replacement_cache:
                replacement_id, replacement = self._replacement_cache.popitem(last=False)
                self._nodes[replacement_id] = replacement
            
            return True
    
    async def mark_node_seen(self, node_id: bytes):
        """Update a node's last_seen time and move to end."""
        async with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].update_last_seen()
                self._nodes.move_to_end(node_id)
    
    def get_node(self, node_id: bytes) -> Optional[NodeInfo]:
        """Get a specific node by ID."""
        return self._nodes.get(node_id)
    
    def get_stale_nodes(self, max_age_seconds: float = 900) -> List[NodeInfo]:
        """Get nodes that haven't been seen recently (default 15 min)."""
        cutoff = time.time() - max_age_seconds
        return [n for n in self._nodes.values() if n.last_seen < cutoff]


class RoutingTable:
    """
    Kademlia routing table with 160 k-buckets.
    
    Structure:
    - Bucket i contains nodes where the XOR distance to us has 
      its highest bit at position (159 - i)
    - Bucket 0: furthest nodes (differ in most significant bit)
    - Bucket 159: closest nodes (differ only in least significant bit)
    
    This logarithmic structure means:
    - We know MORE nodes close to us
    - We know FEWER nodes far away
    - But we always know SOME nodes in every distance range
    """
    
    def __init__(self, node_id: bytes, k: int = K):
        self.node_id = node_id
        self.k = k
        self.buckets: List[KBucket] = [KBucket(k) for _ in range(ID_BITS)]
        self._lock = asyncio.Lock()
    
    def _get_bucket_for_node(self, other_id: bytes) -> Optional[KBucket]:
        """Get the appropriate bucket for a node."""
        index = get_bucket_index(self.node_id, other_id)
        if index < 0:
            return None  # Same as our ID
        return self.buckets[index]
    
    async def add_node(self, node: NodeInfo) -> Optional[NodeInfo]:
        """
        Add a node to the appropriate bucket.
        
        Returns the oldest node if bucket is full (for ping verification).
        """
        if node.node_id == self.node_id:
            return None  # Don't add ourselves
        
        bucket = self._get_bucket_for_node(node.node_id)
        if bucket is None:
            return None
        
        return await bucket.add_node(node)
    
    async def remove_node(self, node_id: bytes) -> bool:
        """Remove a node from its bucket."""
        bucket = self._get_bucket_for_node(node_id)
        if bucket is None:
            return False
        return await bucket.remove_node(node_id)
    
    async def mark_node_seen(self, node_id: bytes):
        """Mark a node as recently seen."""
        bucket = self._get_bucket_for_node(node_id)
        if bucket:
            await bucket.mark_node_seen(node_id)
    
    def get_node(self, node_id: bytes) -> Optional[NodeInfo]:
        """Get a specific node by ID."""
        bucket = self._get_bucket_for_node(node_id)
        if bucket:
            return bucket.get_node(node_id)
        return None
    
    def find_closest_nodes(self, target_id: bytes, count: int = K) -> List[NodeInfo]:
        """
        Find the K closest nodes to a target ID.
        
        This is the core operation for Kademlia lookups.
        We search outward from the target's bucket to find closest nodes.
        """
        # Gather all nodes from all buckets
        all_nodes = []
        for bucket in self.buckets:
            all_nodes.extend(bucket.nodes)
        
        # Sort by XOR distance to target
        all_nodes.sort(key=lambda n: xor_distance(target_id, n.node_id))
        
        return all_nodes[:count]
    
    def get_all_nodes(self) -> List[NodeInfo]:
        """Get all known nodes."""
        all_nodes = []
        for bucket in self.buckets:
            all_nodes.extend(bucket.nodes)
        return all_nodes
    
    def get_stats(self) -> Dict:
        """Get routing table statistics."""
        total_nodes = 0
        non_empty_buckets = 0
        bucket_sizes = []
        
        for i, bucket in enumerate(self.buckets):
            size = len(bucket)
            if size > 0:
                non_empty_buckets += 1
                total_nodes += size
            bucket_sizes.append(size)
        
        return {
            'total_nodes': total_nodes,
            'non_empty_buckets': non_empty_buckets,
            'total_buckets': ID_BITS,
            'bucket_sizes': bucket_sizes,
        }
    
    def get_refresh_targets(self) -> List[bytes]:
        """
        Generate random IDs for buckets that need refreshing.
        
        Used to discover nodes in sparse regions of our ID space.
        """
        import os
        targets = []
        
        for i, bucket in enumerate(self.buckets):
            # If bucket is empty or hasn't been accessed recently
            if len(bucket) == 0:
                # Generate a random ID that would fall in this bucket
                # Set bit at position (159 - i) and randomize the rest
                random_id = bytearray(os.urandom(ID_BYTES))
                
                # XOR with our ID to get an ID at the right distance
                target = bytes(a ^ b for a, b in zip(self.node_id, random_id))
                targets.append(target)
        
        return targets


if __name__ == "__main__":
    # Quick demonstration
    import asyncio
    from .utils import generate_node_id
    
    async def main():
        my_id = generate_node_id()
        table = RoutingTable(my_id)
        
        # Add some random nodes
        for i in range(50):
            node = NodeInfo(
                node_id=generate_node_id(),
                ip=f"192.168.1.{i+1}",
                port=8000 + i
            )
            await table.add_node(node)
        
        stats = table.get_stats()
        print(f"Added nodes. Stats: {stats['total_nodes']} nodes in {stats['non_empty_buckets']} buckets")
        
        # Find closest to a random target
        target = generate_node_id()
        closest = table.find_closest_nodes(target, count=5)
        print(f"\nClosest 5 nodes to random target:")
        for node in closest:
            print(f"  {id_to_hex(node.node_id)[:16]}... @ {node.ip}:{node.port}")
    
    asyncio.run(main())



