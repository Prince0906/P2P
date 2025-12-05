# 🚀 Quick Start Guide

## Prerequisites

- **Python 3.12** installed
- **Node.js** (v18 or later) installed
- **npm** (comes with Node.js)

## Step-by-Step Setup

### 1. Install Backend Dependencies

```bash
# Navigate to backend directory
cd /Users/princesahoo/CODE/p2p/backend

# Create virtual environment (if not already created)
python3.12 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Start Backend Server

**Open Terminal 1:**

```bash
cd /Users/princesahoo/CODE/p2p/backend
source venv/bin/activate
python cli.py start
```

**Note:** If `python` command is not found after activation, use `python3` instead:
```bash
python3 cli.py start
```

You should see:
```
P2P Node Started
Node ID: xxxxxxxx...
DHT Port: 8468
Transfer Port: 8469
REST API available at http://localhost:8080
```

**Keep this terminal running!** ✅

### 3. Install Frontend Dependencies

**Open Terminal 2:**

```bash
cd /Users/princesahoo/CODE/p2p/frontend
npm install
```

### 4. Configure Frontend

Create `.env.local` file in the `frontend` directory:

```bash
cd /Users/princesahoo/CODE/p2p/frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8080" > .env.local
echo "API_URL=http://localhost:8080" >> .env.local
```

### 5. Start Frontend Server

**Still in Terminal 2:**

```bash
npm run dev
```

You should see:
```
▲ Next.js 14.x.x
- Local:        http://localhost:3000
- Ready in 2.3s
```

**Keep this terminal running too!** ✅

### 6. Open in Browser

Open your browser and go to:
```
http://localhost:3000
```

## 🎉 You're Ready!

Now you can:
- 📤 **Upload files** - Drag & drop or select files
- 📥 **Download files** - Use share links or info hash
- 📊 **See activity** - Watch step-by-step what's happening
- 🔍 **View peers** - See discovered nodes on the network

## Testing with Multiple Laptops

### On Laptop 1:
1. Start backend: `cd backend && source venv/bin/activate && python cli.py start`
2. Start frontend: `cd frontend && npm run dev`
3. Upload a file
4. Copy the share link

### On Laptop 2:
1. Start backend: `cd backend && source venv/bin/activate && python cli.py start`
2. Start frontend: `cd frontend && npm run dev`
3. Paste the share link from Laptop 1
4. File downloads automatically!

**Note:** Make sure both laptops are on the same WiFi network!

## Troubleshooting

### Backend won't start?
- Check if port 8080 is already in use: `lsof -i :8080`
- Try different ports: `python cli.py start --api-port 8081`

### Frontend can't connect?
- Make sure backend is running on port 8080
- Check `.env.local` file has correct API URL
- Check browser console for errors

### Files not sharing?
- Check both nodes are running
- Check network connectivity
- Look at activity log for error messages

## Stopping the Servers

- **Backend:** Press `Ctrl+C` in Terminal 1
- **Frontend:** Press `Ctrl+C` in Terminal 2

## Quick Commands Reference

```bash
# Backend (from backend/ directory)
cd backend
source venv/bin/activate
python cli.py start                    # Start node
python cli.py share /path/to/file      # Share file (CLI)
python cli.py download <hash>         # Download file (CLI)
python cli.py status                  # Check status

# Frontend
cd frontend
npm run dev                           # Start dev server
npm run build                         # Build for production
npm run start                         # Start production server
```

## 🎓 For Your Professor Demo

1. **Show Upload Flow:**
   - Drag & drop a file
   - Point to activity log showing each step
   - Show share link appearing

2. **Show Download Flow:**
   - Copy share link
   - Open in new browser/device
   - Show download progress in activity log

3. **Show Network Status:**
   - Point to Node Status showing peers
   - Show DHT nodes count
   - Explain peer discovery

The activity log makes it perfect for explaining what's happening at each step! 📊

