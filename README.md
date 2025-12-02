# P2P File Sharing System

A decentralized file sharing system using Kademlia DHT, designed for university WiFi networks.

## Features

- **Decentralized**: No central server, pure peer-to-peer
- **DHT-based**: Kademlia distributed hash table for efficient file discovery
- **LAN Optimized**: mDNS discovery for zero-config setup on local networks
- **Chunked Transfers**: Large files split into 256KB chunks for parallel downloads
- **Content Addressed**: Files identified by SHA-256 hash for integrity verification

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start a node
python cli.py start --port 8000

# Share a file
python cli.py share /path/to/file.pdf

# Download a file (using its hash)
python cli.py download <file_hash> --output ./downloads/
```

## Architecture

```
┌─────────────────────────────────────────┐
│              P2P Node                    │
├─────────────────────────────────────────┤
│  CLI / REST API                         │
├─────────────────────────────────────────┤
│  Node Controller                        │
├──────────┬──────────┬──────────────────┤
│ DHT      │ File     │ Transfer         │
│ Engine   │ Manager  │ Manager          │
├──────────┴──────────┴──────────────────┤
│  Network Layer (UDP/TCP)               │
├─────────────────────────────────────────┤
│  Discovery (mDNS/Broadcast)            │
└─────────────────────────────────────────┘
```

## How It Works

1. **Discovery**: Nodes find each other via mDNS on the local network
2. **DHT Join**: New nodes join the Kademlia DHT network
3. **Share**: Files are chunked, hashed, and announced to the DHT
4. **Find**: File requests query the DHT to find peers with chunks
5. **Transfer**: Chunks downloaded in parallel from multiple peers

## Documentation

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed design decisions.

## License

MIT License



