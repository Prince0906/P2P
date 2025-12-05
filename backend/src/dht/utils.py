"""
DHT Utilities

Design Decision: Node IDs and Distance Metric
=============================================

Options Considered:
1. 160-bit IDs (SHA-1 style) - Standard Kademlia
2. 256-bit IDs (SHA-256 style) - More address space
3. 128-bit IDs - Shorter but sufficient

Decision: 160-bit Node IDs
- Matches original Kademlia paper
- 2^160 possible IDs is astronomically large
- Sufficient for any practical network size
- Allows 160 k-buckets (one per bit)

XOR Distance Metric:
- d(x,y) = x XOR y
- Symmetric: d(x,y) = d(y,x)  
- Triangle inequality holds
- Unique: d(x,y) = 0 iff x = y
- Unidirectional: for any point x and distance d, there's exactly one y
"""

import os
import hashlib
from typing import List, Tuple

# Constants
ID_BITS = 160  # Number of bits in node ID
ID_BYTES = ID_BITS // 8  # 20 bytes


def generate_node_id() -> bytes:
    """
    Generate a random 160-bit node ID.
    
    Uses cryptographically secure random bytes.
    """
    return os.urandom(ID_BYTES)


def generate_node_id_from_key(key: str) -> bytes:
    """
    Generate a deterministic node ID from a key string.
    
    Useful for testing or when you want reproducible IDs.
    Uses SHA-1 to get 160-bit output.
    """
    return hashlib.sha1(key.encode()).digest()


def xor_distance(id1: bytes, id2: bytes) -> int:
    """
    Calculate the XOR distance between two node IDs.
    
    The XOR metric is the foundation of Kademlia:
    - Smaller distance = closer in the network
    - Used to determine which k-bucket a node belongs to
    - Used to find the closest nodes to a target
    
    Args:
        id1: First node ID (20 bytes)
        id2: Second node ID (20 bytes)
    
    Returns:
        Integer representing the XOR distance
    """
    assert len(id1) == ID_BYTES and len(id2) == ID_BYTES, \
        f"Node IDs must be {ID_BYTES} bytes"
    
    # XOR byte by byte and convert to integer
    return bytes_to_int(bytes(a ^ b for a, b in zip(id1, id2)))


def bytes_to_int(b: bytes) -> int:
    """Convert bytes to integer (big-endian)."""
    return int.from_bytes(b, byteorder='big')


def int_to_bytes(n: int, length: int = ID_BYTES) -> bytes:
    """Convert integer to bytes (big-endian)."""
    return n.to_bytes(length, byteorder='big')


def get_bucket_index(node_id: bytes, other_id: bytes) -> int:
    """
    Determine which k-bucket the other_id belongs to relative to node_id.
    
    The bucket index is the position of the highest bit where the IDs differ.
    - Bucket 0: IDs that differ in the most significant bit (furthest away)
    - Bucket 159: IDs that differ only in the least significant bit (closest)
    
    This is the "distance" in terms of bit prefix length.
    
    Args:
        node_id: Our node's ID
        other_id: The other node's ID
    
    Returns:
        Bucket index (0-159), or -1 if IDs are identical
    """
    distance = xor_distance(node_id, other_id)
    
    if distance == 0:
        return -1  # Same node
    
    # Find the position of the highest set bit
    # bit_length() gives us the number of bits needed to represent the number
    return ID_BITS - distance.bit_length()


def id_to_hex(node_id: bytes) -> str:
    """Convert node ID to hexadecimal string for display."""
    return node_id.hex()


def hex_to_id(hex_str: str) -> bytes:
    """Convert hexadecimal string back to node ID."""
    return bytes.fromhex(hex_str)


def get_shared_prefix_length(id1: bytes, id2: bytes) -> int:
    """
    Calculate how many leading bits are shared between two IDs.
    
    Useful for understanding network structure.
    """
    distance = xor_distance(id1, id2)
    if distance == 0:
        return ID_BITS
    return ID_BITS - distance.bit_length()


def sort_by_distance(target: bytes, nodes: List[Tuple[bytes, any]]) -> List[Tuple[bytes, any]]:
    """
    Sort a list of (node_id, data) tuples by XOR distance to target.
    
    Args:
        target: Target node ID to measure distance from
        nodes: List of (node_id, any_data) tuples
    
    Returns:
        Sorted list with closest nodes first
    """
    return sorted(nodes, key=lambda x: xor_distance(target, x[0]))


if __name__ == "__main__":
    # Quick demonstration
    id1 = generate_node_id()
    id2 = generate_node_id()
    
    print(f"Node 1: {id_to_hex(id1)}")
    print(f"Node 2: {id_to_hex(id2)}")
    print(f"XOR Distance: {xor_distance(id1, id2)}")
    print(f"Bucket Index: {get_bucket_index(id1, id2)}")
    print(f"Shared Prefix: {get_shared_prefix_length(id1, id2)} bits")



