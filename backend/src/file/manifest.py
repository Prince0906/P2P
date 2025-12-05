"""
File Manifest

Design Decision: Manifest Structure
====================================

The manifest is metadata about a shared file. It contains:
- File identification (name, size, total hash)
- Chunk information (hashes, sizes)
- Additional metadata (creation time, etc.)

Options Considered for Manifest Format:
1. JSON - Human readable, easy to parse
2. Protocol Buffers - Compact, typed
3. Bencode - BitTorrent style, well-known
4. Custom binary - Most compact

Decision: JSON
- Easy to debug and inspect
- Standard library support
- Can be compressed if size matters
- Matches our protocol message format

Manifest Distribution:
- Manifest hash = info_hash (DHT key)
- Store manifest in DHT
- Peers download manifest first, then chunks
"""

import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from pathlib import Path


@dataclass
class ChunkInfo:
    """Information about a single file chunk."""
    index: int
    hash: str  # SHA-256 hash as hex
    size: int  # Chunk size in bytes
    offset: int  # Byte offset in original file
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ChunkInfo':
        return cls(**data)


@dataclass
class FileManifest:
    """
    Complete metadata for a shared file.
    
    The manifest is what gets shared/downloaded first.
    It tells peers:
    - What chunks to expect
    - How to verify each chunk
    - How to reassemble the file
    """
    # File identification
    name: str
    size: int
    info_hash: str  # SHA-256 of the file content (hex)
    
    # Chunks
    chunk_size: int
    chunks: List[ChunkInfo]
    
    # Metadata
    created_at: float = field(default_factory=time.time)
    created_by: str = ""  # Node ID that created this
    
    # Optional
    mime_type: str = ""
    description: str = ""
    
    @property
    def chunk_count(self) -> int:
        return len(self.chunks)
    
    @property
    def manifest_hash(self) -> str:
        """
        Hash of the manifest itself.
        
        This can be used as an alternative identifier,
        especially useful when the file hasn't been fully downloaded yet.
        """
        # Hash the JSON representation
        data = self.to_json().encode('utf-8')
        return hashlib.sha256(data).hexdigest()
    
    def get_chunk(self, index: int) -> Optional[ChunkInfo]:
        """Get chunk info by index."""
        if 0 <= index < len(self.chunks):
            return self.chunks[index]
        return None
    
    def get_chunk_by_hash(self, chunk_hash: str) -> Optional[ChunkInfo]:
        """Get chunk info by hash."""
        for chunk in self.chunks:
            if chunk.hash == chunk_hash:
                return chunk
        return None
    
    def verify_chunk(self, index: int, data: bytes) -> bool:
        """Verify a chunk's data against its expected hash."""
        chunk = self.get_chunk(index)
        if chunk is None:
            return False
        
        actual_hash = hashlib.sha256(data).hexdigest()
        return actual_hash == chunk.hash
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            'name': self.name,
            'size': self.size,
            'info_hash': self.info_hash,
            'chunk_size': self.chunk_size,
            'chunks': [c.to_dict() for c in self.chunks],
            'created_at': self.created_at,
            'created_by': self.created_by,
            'mime_type': self.mime_type,
            'description': self.description,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'FileManifest':
        """Deserialize from dictionary."""
        chunks = [ChunkInfo.from_dict(c) for c in data['chunks']]
        return cls(
            name=data['name'],
            size=data['size'],
            info_hash=data['info_hash'],
            chunk_size=data['chunk_size'],
            chunks=chunks,
            created_at=data.get('created_at', time.time()),
            created_by=data.get('created_by', ''),
            mime_type=data.get('mime_type', ''),
            description=data.get('description', ''),
        )
    
    def to_json(self, indent: int = None) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'FileManifest':
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    def save(self, path: Path):
        """Save manifest to a file."""
        with open(path, 'w') as f:
            f.write(self.to_json(indent=2))
    
    @classmethod
    def load(cls, path: Path) -> 'FileManifest':
        """Load manifest from a file."""
        with open(path, 'r') as f:
            return cls.from_json(f.read())


async def create_manifest(file_path: Path, node_id: str = "",
                         chunk_size: int = 256 * 1024) -> FileManifest:
    """
    Create a manifest for a file.
    
    This reads the file, chunks it, and creates the manifest.
    
    Args:
        file_path: Path to the file
        node_id: ID of the node creating this manifest
        chunk_size: Size of each chunk
    
    Returns:
        FileManifest object
    """
    import aiofiles
    from .chunker import FileChunker
    
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    chunker = FileChunker(chunk_size=chunk_size)
    
    # Get file info
    file_size = file_path.stat().st_size
    file_name = file_path.name
    
    # Compute file hash and chunk info
    chunks = []
    file_hasher = hashlib.sha256()
    
    async with aiofiles.open(file_path, 'rb') as f:
        chunk_index = 0
        offset = 0
        
        while True:
            data = await f.read(chunk_size)
            if not data:
                break
            
            file_hasher.update(data)
            chunk_hash = hashlib.sha256(data).hexdigest()
            
            chunks.append(ChunkInfo(
                index=chunk_index,
                hash=chunk_hash,
                size=len(data),
                offset=offset,
            ))
            
            offset += len(data)
            chunk_index += 1
    
    info_hash = file_hasher.hexdigest()
    
    # Detect MIME type (basic)
    mime_type = _guess_mime_type(file_path)
    
    return FileManifest(
        name=file_name,
        size=file_size,
        info_hash=info_hash,
        chunk_size=chunk_size,
        chunks=chunks,
        created_by=node_id,
        mime_type=mime_type,
    )


def create_manifest_sync(file_path: Path, node_id: str = "",
                        chunk_size: int = 256 * 1024) -> FileManifest:
    """Synchronous version of create_manifest."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    file_size = file_path.stat().st_size
    file_name = file_path.name
    
    chunks = []
    file_hasher = hashlib.sha256()
    
    with open(file_path, 'rb') as f:
        chunk_index = 0
        offset = 0
        
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            
            file_hasher.update(data)
            chunk_hash = hashlib.sha256(data).hexdigest()
            
            chunks.append(ChunkInfo(
                index=chunk_index,
                hash=chunk_hash,
                size=len(data),
                offset=offset,
            ))
            
            offset += len(data)
            chunk_index += 1
    
    info_hash = file_hasher.hexdigest()
    mime_type = _guess_mime_type(file_path)
    
    return FileManifest(
        name=file_name,
        size=file_size,
        info_hash=info_hash,
        chunk_size=chunk_size,
        chunks=chunks,
        created_by=node_id,
        mime_type=mime_type,
    )


def _guess_mime_type(file_path: Path) -> str:
    """Guess MIME type from file extension."""
    import mimetypes
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "application/octet-stream"


if __name__ == "__main__":
    import sys
    import asyncio
    
    async def main():
        if len(sys.argv) < 2:
            print("Usage: python manifest.py <file_path>")
            return
        
        file_path = Path(sys.argv[1])
        manifest = await create_manifest(file_path, node_id="test-node")
        
        print(f"Manifest for: {manifest.name}")
        print(f"Size: {manifest.size:,} bytes")
        print(f"Info Hash: {manifest.info_hash}")
        print(f"Chunks: {manifest.chunk_count}")
        print(f"MIME Type: {manifest.mime_type}")
        print()
        print("First 5 chunks:")
        for chunk in manifest.chunks[:5]:
            print(f"  [{chunk.index}] offset={chunk.offset}, size={chunk.size}, hash={chunk.hash[:16]}...")
    
    asyncio.run(main())



