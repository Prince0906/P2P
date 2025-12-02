"""
SQLite Database for Metadata Storage

Design Decision: Why SQLite?
============================

Options Considered:
1. SQLite - Embedded, no server, ACID compliant
2. LevelDB - Key-value, fast, no SQL
3. JSON files - Simple, but no querying
4. PostgreSQL/MySQL - Overkill, requires server

Decision: SQLite with aiosqlite
- Zero configuration
- ACID compliant
- SQL queries for complex lookups
- Single file, easy to backup
- Async support via aiosqlite

Tables:
- node_info: Node identity and configuration
- known_peers: Persistent peer list
- shared_files: Files we're sharing
- download_progress: Partial downloads
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

import aiosqlite

logger = logging.getLogger(__name__)

# Schema version for migrations
SCHEMA_VERSION = 1


class Database:
    """
    SQLite database for persistent storage.
    
    Stores:
    - Node configuration
    - Known peers (for faster bootstrap)
    - Shared file metadata
    - Download state
    """
    
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def connect(self):
        """Open database connection."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        
        # Enable foreign keys
        await self._connection.execute("PRAGMA foreign_keys = ON")
        
        # Initialize schema
        await self._init_schema()
        
        logger.info(f"Database connected: {self.db_path}")
    
    async def close(self):
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
    
    async def _init_schema(self):
        """Initialize database schema."""
        await self._connection.executescript("""
            -- Node information
            CREATE TABLE IF NOT EXISTS node_info (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Known peers for bootstrap
            CREATE TABLE IF NOT EXISTS known_peers (
                node_id TEXT PRIMARY KEY,
                ip TEXT NOT NULL,
                dht_port INTEGER NOT NULL,
                transfer_port INTEGER NOT NULL,
                last_seen TIMESTAMP,
                successful_connections INTEGER DEFAULT 0,
                failed_connections INTEGER DEFAULT 0
            );
            
            -- Shared files metadata
            CREATE TABLE IF NOT EXISTS shared_files (
                info_hash TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                size INTEGER NOT NULL,
                chunk_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT,
                local_path TEXT
            );
            
            -- Download progress tracking
            CREATE TABLE IF NOT EXISTS downloads (
                info_hash TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                size INTEGER NOT NULL,
                total_chunks INTEGER NOT NULL,
                downloaded_chunks INTEGER DEFAULT 0,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT DEFAULT 'in_progress'
            );
            
            -- Downloaded chunks tracking
            CREATE TABLE IF NOT EXISTS downloaded_chunks (
                info_hash TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_hash TEXT NOT NULL,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (info_hash, chunk_index),
                FOREIGN KEY (info_hash) REFERENCES downloads(info_hash) ON DELETE CASCADE
            );
            
            -- Create indexes
            CREATE INDEX IF NOT EXISTS idx_peers_last_seen ON known_peers(last_seen);
            CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
        """)
        
        await self._connection.commit()
    
    # === Node Info ===
    
    async def get_node_info(self, key: str) -> Optional[str]:
        """Get a node info value."""
        async with self._connection.execute(
            "SELECT value FROM node_info WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row['value'] if row else None
    
    async def set_node_info(self, key: str, value: str):
        """Set a node info value."""
        await self._connection.execute(
            """INSERT INTO node_info (key, value, updated_at) 
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP""",
            (key, value, value)
        )
        await self._connection.commit()
    
    # === Peers ===
    
    async def add_peer(self, node_id: str, ip: str, dht_port: int, 
                      transfer_port: int):
        """Add or update a known peer."""
        await self._connection.execute(
            """INSERT INTO known_peers (node_id, ip, dht_port, transfer_port, last_seen)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(node_id) DO UPDATE SET 
                   ip = ?, dht_port = ?, transfer_port = ?, last_seen = CURRENT_TIMESTAMP""",
            (node_id, ip, dht_port, transfer_port, ip, dht_port, transfer_port)
        )
        await self._connection.commit()
    
    async def get_peers(self, limit: int = 50) -> List[Dict]:
        """Get known peers, ordered by most recently seen."""
        async with self._connection.execute(
            """SELECT node_id, ip, dht_port, transfer_port, last_seen,
                      successful_connections, failed_connections
               FROM known_peers
               ORDER BY last_seen DESC
               LIMIT ?""",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def mark_peer_success(self, node_id: str):
        """Mark a successful connection to a peer."""
        await self._connection.execute(
            """UPDATE known_peers 
               SET successful_connections = successful_connections + 1,
                   last_seen = CURRENT_TIMESTAMP
               WHERE node_id = ?""",
            (node_id,)
        )
        await self._connection.commit()
    
    async def mark_peer_failure(self, node_id: str):
        """Mark a failed connection to a peer."""
        await self._connection.execute(
            """UPDATE known_peers 
               SET failed_connections = failed_connections + 1
               WHERE node_id = ?""",
            (node_id,)
        )
        await self._connection.commit()
    
    async def remove_stale_peers(self, max_failures: int = 5):
        """Remove peers with too many failures."""
        await self._connection.execute(
            "DELETE FROM known_peers WHERE failed_connections > ?",
            (max_failures,)
        )
        await self._connection.commit()
    
    # === Shared Files ===
    
    async def add_shared_file(self, info_hash: str, name: str, size: int,
                             chunk_count: int, description: str = "",
                             local_path: str = None):
        """Add a shared file record."""
        await self._connection.execute(
            """INSERT INTO shared_files (info_hash, name, size, chunk_count, description, local_path)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(info_hash) DO UPDATE SET 
                   name = ?, size = ?, chunk_count = ?, description = ?, local_path = ?""",
            (info_hash, name, size, chunk_count, description, local_path,
             name, size, chunk_count, description, local_path)
        )
        await self._connection.commit()
    
    async def get_shared_files(self) -> List[Dict]:
        """Get all shared files."""
        async with self._connection.execute(
            "SELECT * FROM shared_files ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def remove_shared_file(self, info_hash: str):
        """Remove a shared file record."""
        await self._connection.execute(
            "DELETE FROM shared_files WHERE info_hash = ?",
            (info_hash,)
        )
        await self._connection.commit()
    
    # === Downloads ===
    
    async def start_download(self, info_hash: str, name: str, size: int,
                            total_chunks: int):
        """Start tracking a download."""
        await self._connection.execute(
            """INSERT INTO downloads (info_hash, name, size, total_chunks)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(info_hash) DO UPDATE SET status = 'in_progress'""",
            (info_hash, name, size, total_chunks)
        )
        await self._connection.commit()
    
    async def mark_chunk_downloaded(self, info_hash: str, chunk_index: int,
                                   chunk_hash: str):
        """Mark a chunk as downloaded."""
        await self._connection.execute(
            """INSERT INTO downloaded_chunks (info_hash, chunk_index, chunk_hash)
               VALUES (?, ?, ?)
               ON CONFLICT DO NOTHING""",
            (info_hash, chunk_index, chunk_hash)
        )
        
        # Update chunk count
        await self._connection.execute(
            """UPDATE downloads SET downloaded_chunks = 
               (SELECT COUNT(*) FROM downloaded_chunks WHERE info_hash = ?)
               WHERE info_hash = ?""",
            (info_hash, info_hash)
        )
        await self._connection.commit()
    
    async def complete_download(self, info_hash: str):
        """Mark a download as complete."""
        await self._connection.execute(
            """UPDATE downloads 
               SET status = 'completed', completed_at = CURRENT_TIMESTAMP
               WHERE info_hash = ?""",
            (info_hash,)
        )
        await self._connection.commit()
    
    async def get_download_progress(self, info_hash: str) -> Optional[Dict]:
        """Get download progress."""
        async with self._connection.execute(
            "SELECT * FROM downloads WHERE info_hash = ?",
            (info_hash,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def get_downloaded_chunks(self, info_hash: str) -> List[int]:
        """Get list of downloaded chunk indices."""
        async with self._connection.execute(
            "SELECT chunk_index FROM downloaded_chunks WHERE info_hash = ?",
            (info_hash,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [row['chunk_index'] for row in rows]
    
    async def get_incomplete_downloads(self) -> List[Dict]:
        """Get all incomplete downloads."""
        async with self._connection.execute(
            "SELECT * FROM downloads WHERE status = 'in_progress'"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def init_database(data_dir: Path) -> Database:
    """Initialize and return a database instance."""
    db_path = data_dir / "p2p.db"
    db = Database(db_path)
    await db.connect()
    return db



