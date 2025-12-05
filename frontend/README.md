# P2P File Sharing - Frontend

Next.js frontend for the DHT-based P2P file sharing system.

## Features

- 📤 **Upload Files** - Drag and drop or select files to share on the P2P network
- 📥 **Download Files** - Download files using info hash or QR code
- 📊 **Real-time Status** - See step-by-step what's happening (perfect for demos!)
- 🔍 **Peer Discovery** - View discovered peers and DHT nodes
- 📱 **QR Code Sharing** - Share files via QR codes (no copy-paste needed)

## Setup

1. Install dependencies:
```bash
npm install
```

2. Create `.env.local` file:
```env
NEXT_PUBLIC_API_URL=http://localhost:8080
API_URL=http://localhost:8080
```

3. Make sure the backend is running:
```bash
# In the parent directory
python cli.py start
```

4. Run the frontend:
```bash
npm run dev
```

5. Open [http://localhost:3000](http://localhost:3000)

## How It Works

### Upload Flow
1. User selects/drops a file
2. File is uploaded to Next.js API route
3. API route saves file and calls backend `/files/share`
4. Backend chunks file, computes hash, stores chunks
5. Backend announces file to DHT network
6. File is now available for download

### Download Flow
1. User enters info hash or scans QR code
2. Frontend calls backend `/files/download`
3. Backend looks up file in DHT
4. Backend finds peers who have the file
5. Backend downloads chunks from multiple peers (swarming)
6. Backend reassembles file and saves it

### Status Log
The activity log shows every step of the process:
- File selection
- Upload progress
- Chunking and hashing
- DHT announcements
- Peer discovery
- Download progress
- File completion

This makes it perfect for explaining the system to professors or during demos!

## Project Structure

```
frontend/
├── app/
│   ├── api/upload/route.ts    # File upload API route
│   ├── download/[hash]/page.tsx # Download page for QR links
│   └── page.tsx                # Main page
├── components/
│   ├── FileUpload.tsx          # File upload component
│   ├── FileList.tsx            # List of shared files
│   ├── DownloadSection.tsx     # Download interface
│   ├── StatusLog.tsx           # Activity log component
│   └── NodeStatus.tsx          # Node status display
└── lib/
    └── api.ts                  # API client
```

## Technologies

- **Next.js 14** - React framework with App Router
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **Axios** - HTTP client
- **QRCode.react** - QR code generation
- **Lucide React** - Icons
