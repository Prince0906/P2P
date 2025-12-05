import axios from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface NodeStatus {
  node_id: string;
  running: boolean;
  dht_nodes: number;
  shared_files: number;
  discovered_peers: number;
}

export interface FileInfo {
  name: string;
  size: number;
  info_hash: string;
  chunk_count: number;
  mime_type: string;
  description: string;
}

export interface PeerInfo {
  node_id: string;
  ip: string;
  dht_port: number;
  transfer_port: number;
}

export interface ShareResponse {
  success: boolean;
  info_hash: string;
  name: string;
  size: number;
  chunks: number;
}

export interface DownloadResponse {
  success: boolean;
  message: string;
  info_hash: string;
  file_path?: string;
}

export const apiClient = {
  // Node status
  async getStatus(): Promise<NodeStatus> {
    const response = await api.get('/status');
    return response.data;
  },

  async getStats() {
    const response = await api.get('/stats');
    return response.data;
  },

  // File operations
  async shareFile(filePath: string, description: string = ''): Promise<ShareResponse> {
    const response = await api.post('/files/share', {
      file_path: filePath,
      description,
    });
    return response.data;
  },

  async downloadFile(infoHash: string, outputPath?: string): Promise<DownloadResponse> {
    const response = await api.post('/files/download', {
      info_hash: infoHash,
      output_path: outputPath,
    });
    return response.data;
  },

  async listFiles(): Promise<FileInfo[]> {
    const response = await api.get('/files');
    return response.data;
  },

  async getFileInfo(infoHash: string) {
    const response = await api.get(`/files/${infoHash}`);
    return response.data;
  },

  // Peer operations
  async listPeers(): Promise<PeerInfo[]> {
    const response = await api.get('/peers');
    return response.data;
  },

  async listDHTNodes() {
    const response = await api.get('/dht/nodes');
    return response.data;
  },
};

