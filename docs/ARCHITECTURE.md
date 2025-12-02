# P2P File Sharing System - Architecture Design Document

## Context
Building a DHT-based file sharing system for university WiFi network (LAN environment).

---

## Decision 1: Programming Language

### Options Considered

| Language | Pros | Cons |
|----------|------|------|
| **Python** | Fast development, readable, great libraries (asyncio) | Slower runtime, GIL limitations |
| **Go** | Excellent concurrency (goroutines), fast, single binary | Less flexible, verbose error handling |
| **Rust** | Maximum performance, memory safe | Steep learning curve, slower development |
| **Node.js** | Good async model, npm ecosystem | Single-threaded, not ideal for CPU tasks |

### Decision: **Python with asyncio**

**Rationale:**
1. **University context**: Code should be readable for learning/contribution
2. **Rapid prototyping**: Can iterate quickly on P2P protocols
3. **asyncio**: Modern Python handles concurrent connections well
4. **Libraries**: Rich ecosystem (cryptography, networking, etc.)
5. **Good enough performance**: For LAN file sharing, Python's speed is sufficient

---

## Decision 2: DHT Algorithm

### Options Considered

| Algorithm | Lookup Complexity | Key Features | Used By |
|-----------|------------------|--------------|---------|
| **Kademlia** | O(log n) | XOR distance, parallel queries, redundancy | BitTorrent, IPFS, Ethereum |
| **Chord** | O(log n) | Ring topology, finger tables | Academic/research systems |
| **Pastry** | O(log n) | Prefix-based routing, locality aware | Microsoft Research |
| **CAN** | O(d·n^(1/d)) | Multi-dimensional space | Research systems |

### Decision: **Kademlia**

**Rationale:**
1. **Battle-tested**: Powers BitTorrent DHT (millions of nodes)
2. **Self-healing**: XOR metric naturally balances the network
3. **Parallel lookups**: Faster discovery with α concurrent queries
4. **k-buckets**: Natural redundancy (k nodes per bucket)
5. **Flexible**: Works well for both small (LAN) and large networks
6. **Documentation**: Well-documented, many reference implementations

---

## Decision 3: Transport Protocol

### Options Considered

| Protocol | Use Case | Pros | Cons |
|----------|----------|------|------|
| **UDP** | DHT messages | Low overhead, fast | Unreliable, need custom reliability |
| **TCP** | File transfer | Reliable, ordered | Connection overhead |
| **gRPC** | All communication | Structured, streaming | Heavy dependency |
| **Custom over UDP** | Both | Full control | More work |

### Decision: **Hybrid Approach**

- **UDP** for DHT protocol messages (PING, FIND_NODE, etc.)
- **TCP** for file chunk transfers (reliability needed)

**Rationale:**
1. DHT messages are small, frequent → UDP is efficient
2. File transfers need reliability → TCP handles this
3. Follows proven patterns (BitTorrent uses same approach)
4. LAN environment = low packet loss, UDP works great

---

## Decision 4: Node Discovery (Bootstrap)

### Options Considered

| Method | Pros | Cons |
|--------|------|------|
| **mDNS (Multicast DNS)** | Zero-config, automatic | Some networks block multicast |
| **Bootstrap servers** | Reliable entry point | Single point of failure |
| **UDP Broadcast** | Simple, works on LAN | Only works on same subnet |
| **Hybrid** | Best of both worlds | More complexity |

### Decision: **Hybrid (mDNS + Local Bootstrap)**

**Rationale:**
1. **mDNS first**: Zero-config discovery on university LAN
2. **Fallback to broadcast**: If mDNS fails, UDP broadcast on LAN
3. **Optional bootstrap file**: For cross-subnet scenarios
4. University network = same broadcast domain usually

---

## Decision 5: File Chunking Strategy

### Options Considered

| Strategy | Pros | Cons |
|----------|------|------|
| **Fixed-size (e.g., 1MB)** | Simple, predictable | Poor deduplication |
| **Content-Defined Chunking (CDC)** | Great deduplication | Complex, CPU intensive |
| **File-type aware** | Optimized per type | Complex to maintain |

### Decision: **Fixed-size chunks (256KB)**

**Rationale:**
1. **Simplicity**: Easy to implement and debug
2. **LAN context**: High bandwidth, chunk size less critical
3. **256KB sweet spot**: Not too small (overhead) or large (latency)
4. **Future**: Can add CDC later if deduplication needed

---

## Decision 6: Content Addressing

### Options Considered

| Method | Pros | Cons |
|--------|------|------|
| **SHA-256** | Secure, widely used | Slightly slower |
| **SHA-1** | Fast, shorter hash | Collision attacks exist |
| **BLAKE3** | Very fast, secure | Newer, less adoption |
| **MD5** | Very fast | Cryptographically broken |

### Decision: **SHA-256**

**Rationale:**
1. **Security**: No known practical attacks
2. **Standard**: Universal support in Python
3. **Content integrity**: Verifies chunks haven't been tampered
4. **DHT key**: Hash becomes the lookup key

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         P2P Node                                 │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   REST API  │  │   CLI       │  │   (Future: Web UI)      │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
│         │                │                      │                │
│  ┌──────▼────────────────▼──────────────────────▼─────────────┐ │
│  │                    Node Controller                          │ │
│  │         (Orchestrates all operations)                       │ │
│  └──────┬─────────────────┬────────────────────┬──────────────┘ │
│         │                 │                    │                 │
│  ┌──────▼──────┐  ┌───────▼───────┐  ┌────────▼────────┐       │
│  │  DHT Engine │  │ File Manager  │  │ Transfer Manager│       │
│  │  (Kademlia) │  │ (Chunk/Hash)  │  │  (Upload/Down)  │       │
│  └──────┬──────┘  └───────┬───────┘  └────────┬────────┘       │
│         │                 │                    │                 │
│  ┌──────▼─────────────────▼────────────────────▼──────────────┐ │
│  │                   Network Layer                             │ │
│  │         UDP (DHT)           │        TCP (Files)            │ │
│  └─────────────────────────────┴──────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                   Discovery Service                         │ │
│  │              mDNS / UDP Broadcast / Bootstrap               │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                   Local Storage                             │ │
│  │        Chunks (files/) │ Metadata (SQLite) │ Config         │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

### 1. DHT Engine (Kademlia)
- Maintain routing table (k-buckets)
- Handle PING, STORE, FIND_NODE, FIND_VALUE RPCs
- Node ID generation (random 160-bit)
- XOR distance calculations

### 2. File Manager
- Split files into 256KB chunks
- Calculate SHA-256 hash for each chunk
- Generate file manifest (list of chunk hashes)
- Reassemble files from chunks

### 3. Transfer Manager
- Parallel chunk downloads from multiple peers
- Upload chunks to requesting peers
- Bandwidth management (optional)
- Resume interrupted transfers

### 4. Discovery Service
- mDNS service registration/discovery
- UDP broadcast for fallback
- Maintain list of known peers

### 5. Node Controller
- Coordinate all components
- Expose API for operations
- Handle lifecycle (start/stop)

### 6. Local Storage
- Store chunks on filesystem
- SQLite for metadata (files, peers, stats)
- Configuration management

---

## Protocol Messages

### DHT Protocol (UDP)
```
PING           → PONG
STORE          → STORE_RESPONSE
FIND_NODE      → NODES (closest k nodes)
FIND_VALUE     → VALUE or NODES
ANNOUNCE_PEER  → ANNOUNCE_RESPONSE
```

### File Transfer Protocol (TCP)
```
REQUEST_CHUNK(hash)     → CHUNK_DATA or NOT_FOUND
REQUEST_MANIFEST(hash)  → MANIFEST_DATA or NOT_FOUND
```

---

## Directory Structure
```
p2p/
├── src/
│   ├── __init__.py
│   ├── node.py              # Main node controller
│   ├── dht/
│   │   ├── __init__.py
│   │   ├── kademlia.py      # Kademlia DHT implementation
│   │   ├── routing.py       # K-bucket routing table
│   │   ├── protocol.py      # DHT message protocol
│   │   └── utils.py         # XOR distance, ID generation
│   ├── file/
│   │   ├── __init__.py
│   │   ├── chunker.py       # File chunking logic
│   │   ├── manifest.py      # File manifest handling
│   │   └── storage.py       # Local chunk storage
│   ├── transfer/
│   │   ├── __init__.py
│   │   ├── downloader.py    # Download orchestration
│   │   ├── uploader.py      # Upload handling
│   │   └── protocol.py      # Transfer protocol
│   ├── discovery/
│   │   ├── __init__.py
│   │   ├── mdns.py          # mDNS discovery
│   │   └── broadcast.py     # UDP broadcast discovery
│   ├── api/
│   │   ├── __init__.py
│   │   └── rest.py          # REST API endpoints
│   └── storage/
│       ├── __init__.py
│       └── database.py      # SQLite metadata storage
├── cli.py                   # Command-line interface
├── config.py                # Configuration management
├── requirements.txt
├── docs/
│   └── ARCHITECTURE.md      # This file
└── README.md
```

---

## Implementation Phases

### Phase 1: Core DHT
- [ ] Node ID generation
- [ ] K-bucket routing table
- [ ] XOR distance metric
- [ ] Basic UDP protocol (PING/PONG)
- [ ] FIND_NODE implementation

### Phase 2: File Operations
- [ ] File chunking (256KB)
- [ ] SHA-256 hashing
- [ ] Manifest generation
- [ ] Local chunk storage

### Phase 3: DHT Storage & Lookup
- [ ] STORE operation
- [ ] FIND_VALUE operation
- [ ] Announce peer (who has what)

### Phase 4: File Transfer
- [ ] TCP chunk transfer
- [ ] Download from multiple peers
- [ ] Progress tracking

### Phase 5: Discovery
- [ ] mDNS registration
- [ ] mDNS browsing
- [ ] UDP broadcast fallback

### Phase 6: API & CLI
- [ ] REST API
- [ ] Command-line interface
- [ ] Basic web UI (optional)

---

## Security Considerations (Future)
- Node ID verification (prevent Sybil attacks)
- Chunk verification via hashes
- Optional encryption for sensitive files
- Rate limiting to prevent abuse

---

## Performance Targets
- Support 100+ concurrent nodes
- Handle files up to 10GB
- Chunk discovery < 1 second on LAN
- Transfer speed: maximize LAN bandwidth




