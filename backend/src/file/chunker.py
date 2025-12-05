"""
File Chunker

Design Decision: Chunk Size
===========================

Options Considered:
| Size    | Pros                          | Cons                           |
|---------|-------------------------------|--------------------------------|
| 64KB    | Fine-grained, good for small  | High overhead, many chunks     |
| 256KB   | Good balance, standard        | -                              |
| 1MB     | Lower overhead                | Coarse, slower start           |
| 4MB     | Very low overhead             | Bad for partial downloads      |

Decision: 256KB (262,144 bytes)
- Standard size used by many P2P systems
- Good balance between overhead and granularity
- On LAN: chunk transfer takes ~2ms at 1Gbps
- Small enough for parallel downloads from multiple peers
- Large enough to minimize per-chunk overhead

Chunking Strategy: Fixed-Size
- Simplest to implement
- Predictable behavior
- Easy to calculate chunk indices
- Good enough for file sharing (not dedup-focused)
"""

import os
import hashlib
import asyncio
from pathlib import Path
from typing import Iterator, Tuple, Optional, AsyncIterator
import aiofiles

# Chunk size: 256KB
CHUNK_SIZE = 256 * 1024  # 262,144 bytes


class FileChunker:
    """
    Splits files into fixed-size chunks for P2P transfer.
    
    Features:
    - Fixed 256KB chunks
    - SHA-256 hash for each chunk
    - Async file reading
    - Progress tracking support
    """
    
    def __init__(self, chunk_size: int = CHUNK_SIZE):
        self.chunk_size = chunk_size
    
    def get_chunk_count(self, file_size: int) -> int:
        """Calculate number of chunks for a file of given size."""
        return (file_size + self.chunk_size - 1) // self.chunk_size
    
    def get_chunk_bounds(self, chunk_index: int, file_size: int) -> Tuple[int, int]:
        """
        Get byte range for a specific chunk.
        
        Returns:
            (start_offset, length) tuple
        """
        start = chunk_index * self.chunk_size
        length = min(self.chunk_size, file_size - start)
        return start, length
    
    async def chunk_file(self, file_path: Path) -> AsyncIterator[Tuple[int, bytes, bytes]]:
        """
        Split a file into chunks.
        
        Yields:
            (chunk_index, chunk_data, chunk_hash) tuples
        """
        file_size = file_path.stat().st_size
        chunk_count = self.get_chunk_count(file_size)
        
        async with aiofiles.open(file_path, 'rb') as f:
            for chunk_index in range(chunk_count):
                chunk_data = await f.read(self.chunk_size)
                chunk_hash = hashlib.sha256(chunk_data).digest()
                
                yield chunk_index, chunk_data, chunk_hash
    
    async def get_chunk(self, file_path: Path, chunk_index: int) -> Optional[Tuple[bytes, bytes]]:
        """
        Read a specific chunk from a file.
        
        Returns:
            (chunk_data, chunk_hash) tuple, or None if invalid index
        """
        file_size = file_path.stat().st_size
        chunk_count = self.get_chunk_count(file_size)
        
        if chunk_index < 0 or chunk_index >= chunk_count:
            return None
        
        start, length = self.get_chunk_bounds(chunk_index, file_size)
        
        async with aiofiles.open(file_path, 'rb') as f:
            await f.seek(start)
            chunk_data = await f.read(length)
        
        chunk_hash = hashlib.sha256(chunk_data).digest()
        return chunk_data, chunk_hash
    
    def chunk_file_sync(self, file_path: Path) -> Iterator[Tuple[int, bytes, bytes]]:
        """
        Split a file into chunks (synchronous version).
        
        Yields:
            (chunk_index, chunk_data, chunk_hash) tuples
        """
        file_size = file_path.stat().st_size
        chunk_count = self.get_chunk_count(file_size)
        
        with open(file_path, 'rb') as f:
            for chunk_index in range(chunk_count):
                chunk_data = f.read(self.chunk_size)
                chunk_hash = hashlib.sha256(chunk_data).digest()
                
                yield chunk_index, chunk_data, chunk_hash
    
    async def compute_file_hash(self, file_path: Path) -> bytes:
        """
        Compute SHA-256 hash of entire file.
        
        This is the 'info_hash' used to identify the file in the DHT.
        """
        hasher = hashlib.sha256()
        
        async with aiofiles.open(file_path, 'rb') as f:
            while True:
                chunk = await f.read(self.chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        
        return hasher.digest()
    
    def compute_file_hash_sync(self, file_path: Path) -> bytes:
        """Compute SHA-256 hash of entire file (synchronous)."""
        hasher = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        
        return hasher.digest()


def hash_to_hex(hash_bytes: bytes) -> str:
    """Convert hash bytes to hex string."""
    return hash_bytes.hex()


def hex_to_hash(hex_str: str) -> bytes:
    """Convert hex string to hash bytes."""
    return bytes.fromhex(hex_str)


if __name__ == "__main__":
    import sys
    import asyncio
    
    async def main():
        if len(sys.argv) < 2:
            print("Usage: python chunker.py <file_path>")
            return
        
        file_path = Path(sys.argv[1])
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return
        
        chunker = FileChunker()
        
        # Compute file hash
        file_hash = await chunker.compute_file_hash(file_path)
        print(f"File: {file_path.name}")
        print(f"Size: {file_path.stat().st_size:,} bytes")
        print(f"File Hash: {hash_to_hex(file_hash)}")
        print(f"Chunks: {chunker.get_chunk_count(file_path.stat().st_size)}")
        print()
        
        # Show first few chunks
        print("First 3 chunks:")
        count = 0
        async for index, data, hash_val in chunker.chunk_file(file_path):
            print(f"  Chunk {index}: {len(data):,} bytes, hash={hash_to_hex(hash_val)[:16]}...")
            count += 1
            if count >= 3:
                break
    
    asyncio.run(main())



