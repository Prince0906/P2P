"""
Chunk Storage

Design Decision: Storage Strategy
==================================

Options Considered:
1. Single directory with hash-named files
   - Simple, but can have many files
   
2. Two-level directory (first 2 chars of hash)
   - Standard approach, prevents too many files per dir
   - Used by Git, many caching systems
   
3. Content-addressable storage (CAS)
   - More complex, better deduplication
   
4. SQLite blob storage
   - Single file, but harder to manage large data

Decision: Two-level directory structure
- chunks/ab/abcdef123... (first 2 chars as subdirectory)
- Prevents filesystem issues with too many files
- Easy to implement and debug
- Can inspect storage manually

Storage Layout:
```
data/
├── chunks/           # Raw chunk data
│   ├── ab/
│   │   └── abcdef123...
│   └── cd/
│       └── cdef456...
├── manifests/        # File manifests
│   └── <info_hash>.json
├── files/            # Downloaded/reassembled files
└── temp/             # Partial downloads
```
"""

import os
import json
import asyncio
import hashlib
from pathlib import Path
from typing import Optional, Dict, List, Set
from dataclasses import dataclass
import aiofiles
import aiofiles.os

from .manifest import FileManifest


@dataclass
class StorageStats:
    """Statistics about stored data."""
    total_chunks: int
    total_bytes: int
    manifest_count: int


class ChunkStorage:
    """
    Local storage for file chunks and manifests.
    
    Provides:
    - Chunk storage/retrieval by hash
    - Manifest storage/retrieval
    - File reassembly from chunks
    - Storage statistics
    """
    
    def __init__(self, data_dir: Path):
        """
        Initialize chunk storage.
        
        Args:
            data_dir: Root directory for all stored data
        """
        self.data_dir = Path(data_dir)
        self.chunks_dir = self.data_dir / "chunks"
        self.manifests_dir = self.data_dir / "manifests"
        self.files_dir = self.data_dir / "files"
        self.temp_dir = self.data_dir / "temp"
        
        # Ensure directories exist
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create storage directories if they don't exist."""
        for dir_path in [self.chunks_dir, self.manifests_dir, 
                        self.files_dir, self.temp_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def _chunk_path(self, chunk_hash: str) -> Path:
        """Get filesystem path for a chunk."""
        # Use first 2 characters as subdirectory
        prefix = chunk_hash[:2]
        return self.chunks_dir / prefix / chunk_hash
    
    def _manifest_path(self, info_hash: str) -> Path:
        """Get filesystem path for a manifest."""
        return self.manifests_dir / f"{info_hash}.json"
    
    # === Chunk Operations ===
    
    async def store_chunk(self, chunk_hash: str, data: bytes) -> bool:
        """
        Store a chunk.
        
        Verifies hash before storing.
        
        Returns:
            True if stored successfully, False if hash mismatch
        """
        # Verify hash
        actual_hash = hashlib.sha256(data).hexdigest()
        if actual_hash != chunk_hash:
            return False
        
        # Ensure subdirectory exists
        chunk_path = self._chunk_path(chunk_hash)
        await aiofiles.os.makedirs(chunk_path.parent, exist_ok=True)
        
        # Write atomically (write to temp, then rename)
        temp_path = self.temp_dir / f"{chunk_hash}.tmp"
        
        async with aiofiles.open(temp_path, 'wb') as f:
            await f.write(data)
        
        # Rename to final location
        await aiofiles.os.rename(temp_path, chunk_path)
        
        return True
    
    async def get_chunk(self, chunk_hash: str) -> Optional[bytes]:
        """
        Retrieve a chunk by hash.
        
        Returns:
            Chunk data, or None if not found
        """
        chunk_path = self._chunk_path(chunk_hash)
        
        if not chunk_path.exists():
            return None
        
        async with aiofiles.open(chunk_path, 'rb') as f:
            data = await f.read()
        
        # Verify hash
        actual_hash = hashlib.sha256(data).hexdigest()
        if actual_hash != chunk_hash:
            # Corrupted chunk, remove it
            await aiofiles.os.remove(chunk_path)
            return None
        
        return data
    
    async def has_chunk(self, chunk_hash: str) -> bool:
        """Check if a chunk exists in storage."""
        return self._chunk_path(chunk_hash).exists()
    
    async def delete_chunk(self, chunk_hash: str) -> bool:
        """Delete a chunk from storage."""
        chunk_path = self._chunk_path(chunk_hash)
        
        if chunk_path.exists():
            await aiofiles.os.remove(chunk_path)
            return True
        
        return False
    
    def has_chunk_sync(self, chunk_hash: str) -> bool:
        """Synchronous check if chunk exists."""
        return self._chunk_path(chunk_hash).exists()
    
    def get_chunk_sync(self, chunk_hash: str) -> Optional[bytes]:
        """Synchronous chunk retrieval."""
        chunk_path = self._chunk_path(chunk_hash)
        
        if not chunk_path.exists():
            return None
        
        with open(chunk_path, 'rb') as f:
            data = f.read()
        
        actual_hash = hashlib.sha256(data).hexdigest()
        if actual_hash != chunk_hash:
            chunk_path.unlink()
            return None
        
        return data
    
    # === Manifest Operations ===
    
    async def store_manifest(self, manifest: FileManifest) -> str:
        """
        Store a file manifest.
        
        Returns:
            The info_hash (can be used to retrieve later)
        """
        manifest_path = self._manifest_path(manifest.info_hash)
        
        async with aiofiles.open(manifest_path, 'w') as f:
            await f.write(manifest.to_json(indent=2))
        
        return manifest.info_hash
    
    async def get_manifest(self, info_hash: str) -> Optional[FileManifest]:
        """
        Retrieve a manifest by info_hash.
        
        Returns:
            FileManifest, or None if not found
        """
        manifest_path = self._manifest_path(info_hash)
        
        if not manifest_path.exists():
            return None
        
        async with aiofiles.open(manifest_path, 'r') as f:
            data = await f.read()
        
        return FileManifest.from_json(data)
    
    async def has_manifest(self, info_hash: str) -> bool:
        """Check if a manifest exists."""
        return self._manifest_path(info_hash).exists()
    
    async def delete_manifest(self, info_hash: str) -> bool:
        """Delete a manifest."""
        manifest_path = self._manifest_path(info_hash)
        
        if manifest_path.exists():
            await aiofiles.os.remove(manifest_path)
            return True
        
        return False
    
    async def list_manifests(self) -> List[FileManifest]:
        """List all stored manifests."""
        manifests = []
        
        for manifest_file in self.manifests_dir.glob("*.json"):
            try:
                async with aiofiles.open(manifest_file, 'r') as f:
                    data = await f.read()
                manifests.append(FileManifest.from_json(data))
            except Exception:
                pass  # Skip corrupted manifests
        
        return manifests
    
    # === File Operations ===
    
    async def store_file(self, file_path: Path, manifest: FileManifest = None) -> FileManifest:
        """
        Store a complete file (chunk it and store all chunks).
        
        Args:
            file_path: Path to the file to store
            manifest: Optional pre-computed manifest
        
        Returns:
            The file's manifest
        """
        from .manifest import create_manifest
        from .chunker import FileChunker
        
        file_path = Path(file_path)
        
        # Create manifest if not provided
        if manifest is None:
            manifest = await create_manifest(file_path)
        
        # Store manifest
        await self.store_manifest(manifest)
        
        # Store chunks
        chunker = FileChunker(chunk_size=manifest.chunk_size)
        
        async for index, data, hash_bytes in chunker.chunk_file(file_path):
            chunk_hash = hash_bytes.hex()
            await self.store_chunk(chunk_hash, data)
        
        return manifest
    
    async def reassemble_file(self, manifest: FileManifest, 
                             output_path: Path = None) -> Optional[Path]:
        """
        Reassemble a file from its chunks.
        
        Args:
            manifest: The file's manifest
            output_path: Where to write the file (defaults to files_dir)
        
        Returns:
            Path to the reassembled file, or None if chunks missing
        """
        if output_path is None:
            output_path = self.files_dir / manifest.name
        
        output_path = Path(output_path)
        
        # Check all chunks exist
        for chunk_info in manifest.chunks:
            if not await self.has_chunk(chunk_info.hash):
                return None
        
        # Write to temp file first
        temp_path = self.temp_dir / f"{manifest.info_hash}.tmp"
        
        async with aiofiles.open(temp_path, 'wb') as f:
            for chunk_info in manifest.chunks:
                chunk_data = await self.get_chunk(chunk_info.hash)
                if chunk_data is None:
                    # Chunk disappeared
                    await aiofiles.os.remove(temp_path)
                    return None
                await f.write(chunk_data)
        
        # Verify file hash
        file_hasher = hashlib.sha256()
        async with aiofiles.open(temp_path, 'rb') as f:
            while True:
                data = await f.read(256 * 1024)
                if not data:
                    break
                file_hasher.update(data)
        
        if file_hasher.hexdigest() != manifest.info_hash:
            await aiofiles.os.remove(temp_path)
            return None
        
        # Move to final location
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await aiofiles.os.rename(temp_path, output_path)
        
        return output_path
    
    async def get_missing_chunks(self, manifest: FileManifest) -> List[str]:
        """
        Get list of chunk hashes we don't have for a file.
        
        Useful for knowing what to download.
        """
        missing = []
        
        for chunk_info in manifest.chunks:
            if not await self.has_chunk(chunk_info.hash):
                missing.append(chunk_info.hash)
        
        return missing
    
    async def get_available_chunks(self, manifest: FileManifest) -> List[str]:
        """Get list of chunk hashes we have for a file."""
        available = []
        
        for chunk_info in manifest.chunks:
            if await self.has_chunk(chunk_info.hash):
                available.append(chunk_info.hash)
        
        return available
    
    def get_download_progress(self, manifest: FileManifest) -> float:
        """
        Get download progress for a file (0.0 to 1.0).
        
        Synchronous for easy status checks.
        """
        if not manifest.chunks:
            return 1.0
        
        available = sum(1 for c in manifest.chunks if self.has_chunk_sync(c.hash))
        return available / len(manifest.chunks)
    
    # === Statistics ===
    
    async def get_stats(self) -> StorageStats:
        """Get storage statistics."""
        total_chunks = 0
        total_bytes = 0
        
        # Count chunks
        for prefix_dir in self.chunks_dir.iterdir():
            if prefix_dir.is_dir():
                for chunk_file in prefix_dir.iterdir():
                    total_chunks += 1
                    total_bytes += chunk_file.stat().st_size
        
        # Count manifests
        manifest_count = len(list(self.manifests_dir.glob("*.json")))
        
        return StorageStats(
            total_chunks=total_chunks,
            total_bytes=total_bytes,
            manifest_count=manifest_count,
        )
    
    async def cleanup_orphan_chunks(self, keep_hashes: Set[str] = None):
        """
        Remove chunks that aren't referenced by any manifest.
        
        Args:
            keep_hashes: Additional hashes to keep (optional)
        """
        # Collect all referenced chunk hashes
        referenced = set(keep_hashes or [])
        
        manifests = await self.list_manifests()
        for manifest in manifests:
            for chunk in manifest.chunks:
                referenced.add(chunk.hash)
        
        # Find and remove orphans
        removed = 0
        for prefix_dir in self.chunks_dir.iterdir():
            if prefix_dir.is_dir():
                for chunk_file in prefix_dir.iterdir():
                    chunk_hash = chunk_file.name
                    if chunk_hash not in referenced:
                        chunk_file.unlink()
                        removed += 1
        
        return removed


if __name__ == "__main__":
    import sys
    import asyncio
    
    async def main():
        if len(sys.argv) < 2:
            print("Usage: python storage.py <file_path>")
            return
        
        file_path = Path(sys.argv[1])
        data_dir = Path("./test_storage")
        
        storage = ChunkStorage(data_dir)
        
        print(f"Storing file: {file_path}")
        manifest = await storage.store_file(file_path)
        
        print(f"Stored with info_hash: {manifest.info_hash}")
        print(f"Chunks: {manifest.chunk_count}")
        
        stats = await storage.get_stats()
        print(f"\nStorage stats:")
        print(f"  Chunks: {stats.total_chunks}")
        print(f"  Bytes: {stats.total_bytes:,}")
        print(f"  Manifests: {stats.manifest_count}")
        
        # Test reassembly
        print(f"\nReassembling file...")
        output = await storage.reassemble_file(manifest)
        print(f"Reassembled to: {output}")
    
    asyncio.run(main())



