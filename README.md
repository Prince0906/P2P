# P2P File Sharing System

A decentralized file sharing system using Kademlia DHT, designed for university WiFi networks.

## 📁 Project Structure

```
p2p/
├── backend/          # Python backend (P2P node)
│   ├── src/         # Source code
│   ├── cli.py       # Command-line interface
│   ├── start.sh     # Helper script to start backend
│   └── requirements.txt
└── frontend/         # Next.js frontend (web interface)
    ├── app/         # Next.js app directory
    ├── components/  # React components
    └── package.json
```

## 🚀 Quick Start

### Backend Setup

```bash
# Navigate to backend directory
cd backend

# Option 1: Use the helper script (recommended)
./start.sh start

# Option 2: Manual activation
source venv/bin/activate
python cli.py start
# Or if python is not found:
python3 cli.py start
```

### Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies (first time only)
npm install

# Create environment file
echo "NEXT_PUBLIC_API_URL=http://localhost:8080" > .env.local

# Start development server
npm run dev
```

Then open http://localhost:3000 in your browser.

## 📖 Detailed Documentation

- **Backend**: See [backend/README.md](backend/README.md) and [backend/QUICK_START.md](backend/QUICK_START.md)
- **Frontend**: See [frontend/README.md](frontend/README.md)

## 🔧 Troubleshooting

### Backend: "python: command not found"

If you get this error after activating the venv, use the helper script instead:
```bash
cd backend
./start.sh start
```

Or use `python3` directly:
```bash
cd backend
source venv/bin/activate
python3 cli.py start
```

### Backend: "ModuleNotFoundError"

Reinstall dependencies:
```bash
cd backend
venv/bin/python -m pip install -r requirements.txt
```

### Frontend: Can't connect to backend

1. Make sure backend is running: `cd backend && ./start.sh start`
2. Check `.env.local` has correct URL: `NEXT_PUBLIC_API_URL=http://localhost:8080`
3. Check backend is accessible: `curl http://localhost:8080/status`

## 🎓 Features

- **Decentralized**: No central server, pure peer-to-peer
- **DHT-based**: Kademlia distributed hash table for efficient file discovery
- **LAN Optimized**: mDNS discovery for zero-config setup on local networks
- **Chunked Transfers**: Large files split into 256KB chunks for parallel downloads
- **Content Addressed**: Files identified by SHA-256 hash for integrity verification
- **Web Interface**: Beautiful Next.js frontend with drag-and-drop uploads
- **Activity Log**: Step-by-step progress tracking (perfect for demos!)

## 📝 License

MIT License


