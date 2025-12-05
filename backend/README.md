# P2P File Sharing System

A decentralized file sharing system using Kademlia DHT, designed for university WiFi networks.

## Features

- **Decentralized**: No central server, pure peer-to-peer
- **DHT-based**: Kademlia distributed hash table for efficient file discovery
- **LAN Optimized**: mDNS discovery for zero-config setup on local networks
- **Chunked Transfers**: Large files split into 256KB chunks for parallel downloads
- **Content Addressed**: Files identified by SHA-256 hash for integrity verification

## Quick Start

### Backend (CLI)

**Recommended: Use the helper script**
```bash
# Start a node
./start.sh start

# Share a file
./start.sh share /path/to/file.pdf

# Download a file (using its hash)
./start.sh download <file_hash> --output ./downloads/
```

**Alternative: Manual activation**
```bash
# Navigate to backend directory
cd backend

# Activate virtual environment
source venv/bin/activate

# If 'python' command not found, use 'python3'
python3 cli.py start

# Share a file
python3 cli.py share /path/to/file.pdf

# Download a file (using its hash)
python3 cli.py download <file_hash> --output ./downloads/
```

**First-time setup:**
```bash
# Create virtual environment
python3.12 -m venv venv

# Install dependencies
venv/bin/python -m pip install -r requirements.txt
```

### Frontend (Web Interface)

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Create .env.local file
echo "NEXT_PUBLIC_API_URL=http://localhost:8080" > .env.local
echo "API_URL=http://localhost:8080" >> .env.local

# Make sure backend is running (in another terminal)
# python cli.py start

# Start frontend
npm run dev

# Open http://localhost:3000
```

The frontend provides:
- 📤 **Drag & drop file upload**
- 📥 **Easy file downloads** (no hash copy-paste needed!)
- 📊 **Real-time activity log** showing every step (perfect for demos!)
- 📱 **QR code sharing** for easy file distribution
- 🔍 **Peer and DHT node visualization**

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



