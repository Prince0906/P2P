# Backend Codebase Structure

## 📁 Directory Layout

```
backend/
├── src/                    # Source code modules
│   ├── __init__.py
│   ├── node.py            # Main P2P node controller
│   ├── dht/               # DHT (Kademlia) implementation
│   │   ├── kademlia.py    # Kademlia node
│   │   ├── routing.py     # K-bucket routing table
│   │   ├── protocol.py    # DHT message protocol
│   │   └── utils.py       # XOR distance, ID generation
│   ├── file/              # File operations
│   │   ├── chunker.py     # File chunking logic
│   │   ├── manifest.py    # File manifest handling
│   │   └── storage.py     # Local chunk storage
│   ├── transfer/          # File transfer
│   │   ├── downloader.py  # Download orchestration
│   │   ├── uploader.py     # Upload handling
│   │   └── protocol.py    # Transfer protocol (TCP)
│   ├── discovery/         # Peer discovery
│   │   ├── mdns.py        # mDNS discovery
│   │   ├── broadcast.py   # UDP broadcast discovery
│   │   └── manager.py     # Discovery coordinator
│   ├── api/               # REST API
│   │   └── rest.py        # FastAPI endpoints
│   └── storage/            # Metadata storage
│       └── database.py    # SQLite database
├── cli.py                 # Command-line interface
├── config.py              # Configuration management
├── start.sh               # Helper script (recommended way to start)
├── requirements.txt       # Python dependencies
├── venv/                  # Virtual environment (Python 3.12)
└── p2p_data/              # Runtime data (chunks, manifests, files)
```

## 🔧 Import Structure

All imports use relative imports within the `src/` package:

- `cli.py` imports: `from src.node import P2PNode`
- `src/node.py` imports: `from .dht import KademliaNode`
- Modules use relative imports: `from .manifest import FileManifest`

The `cli.py` adds `src/` to `sys.path` so imports work correctly:
```python
sys.path.insert(0, str(Path(__file__).parent))
```

## 🐍 Python Environment

### Virtual Environment Setup

The backend uses Python 3.12 in a virtual environment:

```bash
# Virtual environment location
backend/venv/

# Python executable
backend/venv/bin/python  # Points to Python 3.12.12
```

### Common Issue: "python: command not found"

**Problem:** After activating venv with `source venv/bin/activate`, the `python` command is not found.

**Root Cause:** The venv activation script may not properly set PATH in zsh, or there's a mismatch between the venv Python and system Python.

**Solutions:**

1. **Use the helper script (recommended):**
   ```bash
   ./start.sh start
   ```
   This script uses the venv Python directly without relying on activation.

2. **Use python3 directly:**
   ```bash
   source venv/bin/activate
   python3 cli.py start  # Instead of 'python'
   ```

3. **Use full path to venv Python:**
   ```bash
   venv/bin/python cli.py start
   ```

## 🚀 Running the Backend

### Method 1: Helper Script (Recommended)

```bash
cd backend
./start.sh start
```

The `start.sh` script:
- Checks if venv exists (creates if needed)
- Installs dependencies if missing
- Uses venv Python directly (no activation needed)
- Passes all arguments to `cli.py`

### Method 2: Manual Activation

```bash
cd backend
source venv/bin/activate
python3 cli.py start  # Use python3, not python
```

### Method 3: Direct Python Path

```bash
cd backend
venv/bin/python cli.py start
```

## 📝 Key Files Explained

### `cli.py`
- Entry point for command-line interface
- Uses Click framework for CLI commands
- Imports from `src/` modules
- Adds `backend/` directory to `sys.path` for imports

### `src/node.py`
- Main P2P node controller
- Orchestrates DHT, file operations, transfer, and discovery
- Contains `P2PNode` class and `NodeConfig` dataclass
- Has `info_hash_to_dht_key()` function to convert SHA-256 to DHT keys

### `src/api/rest.py`
- FastAPI REST API server
- Provides HTTP endpoints for file operations
- Includes CORS middleware for frontend access
- Runs on port 8080 by default

### `start.sh`
- Helper script to start backend reliably
- Handles venv activation issues
- Can be used for any CLI command: `./start.sh <command>`

## 🔍 Troubleshooting

### "ModuleNotFoundError: No module named 'click'"

**Fix:** Reinstall dependencies:
```bash
cd backend
venv/bin/python -m pip install -r requirements.txt
```

### "Address already in use" (port 8080)

**Fix:** Kill existing process or use different port:
```bash
# Kill process on port 8080
lsof -ti :8080 | xargs kill -9

# Or use different port
./start.sh start --api-port 8081
```

### Import errors after moving files

**Fix:** Make sure you're running from `backend/` directory:
```bash
cd backend
./start.sh start
```

## 📚 Related Documentation

- [QUICK_START.md](QUICK_START.md) - Step-by-step setup guide
- [README.md](README.md) - Overview and features
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - Design decisions


