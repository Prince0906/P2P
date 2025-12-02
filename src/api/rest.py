"""
REST API for P2P Node

Design Decision: API Framework
==============================

Options Considered:
1. FastAPI - Modern, fast, auto-docs, async support
2. Flask - Simple, widely used, but sync-focused
3. aiohttp - Async, but less features
4. Starlette - Lightweight, FastAPI is built on it

Decision: FastAPI
- Native async support (important for our async node)
- Automatic OpenAPI documentation
- Pydantic integration for validation
- Modern Python features

API Design:
- RESTful endpoints
- JSON responses
- Follows HTTP semantics
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Global reference to the P2P node (set when app is created)
_node = None


# === Pydantic Models ===

class ShareRequest(BaseModel):
    """Request to share a file."""
    file_path: str
    description: str = ""


class DownloadRequest(BaseModel):
    """Request to download a file."""
    info_hash: str
    output_path: Optional[str] = None


class NodeStatus(BaseModel):
    """Node status response."""
    node_id: str
    running: bool
    dht_nodes: int
    shared_files: int
    discovered_peers: int


class FileInfo(BaseModel):
    """Information about a shared file."""
    name: str
    size: int
    info_hash: str
    chunk_count: int
    mime_type: str
    description: str


class PeerInfo(BaseModel):
    """Information about a peer."""
    node_id: str
    ip: str
    dht_port: int
    transfer_port: int


# === API Creation ===

def create_app(node=None) -> FastAPI:
    """
    Create the FastAPI application.
    
    Args:
        node: P2PNode instance to control
    
    Returns:
        FastAPI application
    """
    global _node
    _node = node
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Handle startup and shutdown."""
        logger.info("API server starting...")
        yield
        logger.info("API server stopping...")
    
    app = FastAPI(
        title="P2P File Sharing API",
        description="REST API for the DHT-based P2P file sharing system",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # === Endpoints ===
    
    @app.get("/", tags=["General"])
    async def root():
        """API root - basic info."""
        return {
            "name": "P2P File Sharing System",
            "version": "1.0.0",
            "status": "running" if _node and _node.is_running else "not running"
        }
    
    @app.get("/status", response_model=NodeStatus, tags=["Node"])
    async def get_status():
        """Get node status."""
        if not _node:
            raise HTTPException(status_code=503, detail="Node not initialized")
        
        stats = _node.get_full_stats()
        manifests = await _node.list_shared_files()
        
        return NodeStatus(
            node_id=stats['node_id'][:16] + "...",
            running=stats['running'],
            dht_nodes=stats['dht']['routing_table']['total_nodes'],
            shared_files=len(manifests),
            discovered_peers=stats['discovery']['total_peers'],
        )
    
    @app.get("/stats", tags=["Node"])
    async def get_stats():
        """Get detailed node statistics."""
        if not _node:
            raise HTTPException(status_code=503, detail="Node not initialized")
        
        return _node.get_full_stats()
    
    # === File Operations ===
    
    @app.post("/files/share", tags=["Files"])
    async def share_file(request: ShareRequest):
        """Share a file with the network."""
        if not _node:
            raise HTTPException(status_code=503, detail="Node not initialized")
        
        file_path = Path(request.file_path)
        
        # Handle relative paths - resolve to absolute
        if not file_path.is_absolute():
            file_path = file_path.resolve()
        
        logger.info(f"Share request for: {file_path}")
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
        
        if not file_path.is_file():
            raise HTTPException(status_code=400, detail=f"Not a file: {file_path}")
        
        try:
            manifest = await _node.share(file_path, request.description)
            return {
                "success": True,
                "info_hash": manifest.info_hash,
                "name": manifest.name,
                "size": manifest.size,
                "chunks": manifest.chunk_count,
            }
        except Exception as e:
            logger.error(f"Error sharing file: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/files/download", tags=["Files"])
    async def download_file(request: DownloadRequest):
        """Download a file from the network."""
        if not _node:
            raise HTTPException(status_code=503, detail="Node not initialized")
        
        # Validate info_hash format (should be 64 hex characters for SHA-256)
        info_hash = request.info_hash.strip()
        if len(info_hash) != 64 or not all(c in '0123456789abcdefABCDEF' for c in info_hash):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid info_hash format. Expected 64 hex characters, got: {info_hash[:20]}..."
            )
        
        output_path = Path(request.output_path) if request.output_path else None
        
        logger.info(f"Download request for: {info_hash[:16]}...")
        
        try:
            # Download synchronously (not in background) so we can return the result
            result = await _node.download(info_hash, output_path)
            
            if result:
                logger.info(f"Download complete: {result}")
                return {
                    "success": True,
                    "message": "Download complete",
                    "info_hash": info_hash,
                    "file_path": str(result),
                }
            else:
                logger.error(f"Download failed: {info_hash}")
                raise HTTPException(status_code=404, detail="Download failed - file not found or no peers available")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Download error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/files", response_model=List[FileInfo], tags=["Files"])
    async def list_files():
        """List all shared files."""
        if not _node:
            raise HTTPException(status_code=503, detail="Node not initialized")
        
        manifests = await _node.list_shared_files()
        return [
            FileInfo(
                name=m.name,
                size=m.size,
                info_hash=m.info_hash,
                chunk_count=m.chunk_count,
                mime_type=m.mime_type,
                description=m.description,
            )
            for m in manifests
        ]
    
    @app.get("/files/{info_hash}", tags=["Files"])
    async def get_file_info(info_hash: str):
        """Get information about a specific file."""
        if not _node:
            raise HTTPException(status_code=503, detail="Node not initialized")
        
        manifest = await _node.get_file_info(info_hash)
        if not manifest:
            raise HTTPException(status_code=404, detail="File not found")
        
        return {
            "name": manifest.name,
            "size": manifest.size,
            "info_hash": manifest.info_hash,
            "chunks": manifest.chunk_count,
            "chunk_size": manifest.chunk_size,
            "mime_type": manifest.mime_type,
            "description": manifest.description,
            "created_at": manifest.created_at,
        }
    
    @app.delete("/files/{info_hash}", tags=["Files"])
    async def remove_file(info_hash: str):
        """Stop sharing a file."""
        if not _node:
            raise HTTPException(status_code=503, detail="Node not initialized")
        
        success = await _node.remove_shared_file(info_hash)
        return {"success": success}
    
    # === Peer Operations ===
    
    @app.get("/peers", response_model=List[PeerInfo], tags=["Peers"])
    async def list_peers():
        """List discovered peers."""
        if not _node:
            raise HTTPException(status_code=503, detail="Node not initialized")
        
        peers = _node.get_peers()
        return [
            PeerInfo(
                node_id=p.node_id[:16] + "...",
                ip=p.ip,
                dht_port=p.dht_port,
                transfer_port=p.transfer_port,
            )
            for p in peers
        ]
    
    @app.get("/dht/nodes", tags=["DHT"])
    async def list_dht_nodes():
        """List nodes in the DHT routing table."""
        if not _node:
            raise HTTPException(status_code=503, detail="Node not initialized")
        
        nodes = _node.dht.routing_table.get_all_nodes()
        return [
            {
                "node_id": n.node_id.hex()[:16] + "...",
                "ip": n.ip,
                "port": n.port,
                "last_seen": n.last_seen,
            }
            for n in nodes[:50]  # Limit to 50
        ]
    
    return app


async def run_api_server(node, host: str = "0.0.0.0", port: int = 8080):
    """
    Run the API server.
    
    Args:
        node: P2PNode instance
        host: Host to bind to
        port: Port to listen on
    """
    import uvicorn
    
    app = create_app(node)
    
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


