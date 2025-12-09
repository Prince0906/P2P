'use client';

import { useEffect, useState, useRef } from 'react';
import { Server, HardDrive, Zap, CheckCircle2, XCircle, Loader2, ArrowDownToLine } from 'lucide-react';

interface ChunkInfo {
  index: number;
  hash: string;
  status: 'pending' | 'downloading' | 'complete' | 'failed';
  peer: string | null;
}

interface PeerInfo {
  ip: string;
  port: number;
  chunks_assigned: number;
  chunks_completed: number;
  chunks_failed: number;
  bytes_downloaded: number;
  is_active: boolean;
}

interface DownloadProgress {
  phase: 'initializing' | 'finding_peers' | 'downloading' | 'merging' | 'complete' | 'failed' | 'error';
  total_chunks: number;
  downloaded_chunks: number;
  failed_chunks: number;
  bytes_downloaded: number;
  progress_percent: number;
  speed_bytes_per_sec: number;
  elapsed_seconds: number;
  file_name: string;
  file_size: number;
  chunks: ChunkInfo[];
  peers: PeerInfo[];
  message?: string;
  error?: string;
  file_path?: string;
}

interface DownloadVisualizerProps {
  infoHash: string;
  onComplete?: (filePath: string) => void;
  onError?: (error: string) => void;
}

export default function DownloadVisualizer({ infoHash, onComplete, onError }: DownloadVisualizerProps) {
  const [progress, setProgress] = useState<DownloadProgress | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!infoHash) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
    const eventSource = new EventSource(`${apiUrl}/files/download/${infoHash}/stream`);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setProgress(data);

        // Handle completion
        if (data.phase === 'complete' && data.file_path && onComplete) {
          onComplete(data.file_path);
        }
        if ((data.phase === 'error' || data.phase === 'failed') && onError) {
          onError(data.error || 'Download failed');
        }
      } catch (e) {
        console.error('Failed to parse SSE data:', e);
      }
    };

    eventSource.onerror = () => {
      setIsConnected(false);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [infoHash, onComplete, onError]);

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  };

  const formatSpeed = (bytesPerSec: number): string => {
    return `${formatBytes(bytesPerSec)}/s`;
  };

  const getPhaseLabel = (phase: string): string => {
    switch (phase) {
      case 'initializing': return 'Initializing...';
      case 'finding_peers': return 'Finding peers...';
      case 'downloading': return 'Downloading chunks...';
      case 'merging': return 'Merging file...';
      case 'complete': return 'Complete!';
      case 'failed': return 'Failed';
      case 'error': return 'Error';
      default: return phase;
    }
  };

  const getChunkColor = (status: string): string => {
    switch (status) {
      case 'pending': return 'bg-gray-200';
      case 'downloading': return 'bg-blue-500 animate-pulse';
      case 'complete': return 'bg-green-500';
      case 'failed': return 'bg-red-500';
      default: return 'bg-gray-200';
    }
  };

  if (!progress) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center justify-center gap-3 text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Connecting to download stream...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Phase & Progress Header */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            {progress.phase === 'complete' ? (
              <CheckCircle2 className="w-6 h-6 text-green-500" />
            ) : progress.phase === 'failed' || progress.phase === 'error' ? (
              <XCircle className="w-6 h-6 text-red-500" />
            ) : (
              <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
            )}
            <div>
              <h3 className="font-semibold text-gray-800">{getPhaseLabel(progress.phase)}</h3>
              {progress.file_name && (
                <p className="text-sm text-gray-500">{progress.file_name}</p>
              )}
            </div>
          </div>
          <div className="text-right">
            <p className="text-2xl font-bold text-gray-800">{progress.progress_percent.toFixed(1)}%</p>
            <p className="text-sm text-gray-500">{formatSpeed(progress.speed_bytes_per_sec)}</p>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-300 ${
              progress.phase === 'complete' ? 'bg-green-500' :
              progress.phase === 'failed' ? 'bg-red-500' :
              progress.phase === 'merging' ? 'bg-yellow-500 animate-pulse' :
              'bg-blue-500'
            }`}
            style={{ width: `${progress.progress_percent}%` }}
          />
        </div>

        <div className="flex justify-between mt-2 text-sm text-gray-500">
          <span>{progress.downloaded_chunks} / {progress.total_chunks} chunks</span>
          <span>{formatBytes(progress.bytes_downloaded)} / {formatBytes(progress.file_size)}</span>
        </div>
      </div>

      {/* Peers Panel */}
      {progress.peers && progress.peers.length > 0 && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h4 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
            <Server className="w-5 h-5 text-purple-500" />
            Active Peers ({progress.peers.length})
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {progress.peers.map((peer, idx) => (
              <div
                key={`${peer.ip}:${peer.port}`}
                className={`p-3 rounded-lg border-2 ${
                  peer.is_active ? 'border-green-200 bg-green-50' : 'border-gray-200 bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-sm text-gray-700">{peer.ip}:{peer.port}</span>
                  {peer.is_active && (
                    <span className="flex h-2 w-2 relative">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                    </span>
                  )}
                </div>
                <div className="flex justify-between text-xs text-gray-500">
                  <span>Assigned: {peer.chunks_assigned}</span>
                  <span className="text-green-600">Done: {peer.chunks_completed}</span>
                  {peer.chunks_failed > 0 && (
                    <span className="text-red-600">Failed: {peer.chunks_failed}</span>
                  )}
                </div>
                <div className="mt-1">
                  <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-green-500 transition-all"
                      style={{ width: `${(peer.chunks_completed / peer.chunks_assigned) * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Chunk Grid */}
      {progress.chunks && progress.chunks.length > 0 && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h4 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
            <HardDrive className="w-5 h-5 text-blue-500" />
            Chunk Status ({progress.chunks.length} chunks)
          </h4>
          
          {/* Legend */}
          <div className="flex gap-4 mb-3 text-xs">
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-gray-200"></span> Pending
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-blue-500 animate-pulse"></span> Downloading
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-green-500"></span> Complete
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-red-500"></span> Failed
            </span>
          </div>

          {/* Grid */}
          <div className="flex flex-wrap gap-1">
            {progress.chunks.map((chunk) => (
              <div
                key={chunk.index}
                className={`w-4 h-4 rounded ${getChunkColor(chunk.status)} transition-all duration-200`}
                title={`Chunk ${chunk.index}: ${chunk.status}${chunk.peer ? ` (from ${chunk.peer})` : ''}`}
              />
            ))}
          </div>
        </div>
      )}

      {/* Merging Animation */}
      {progress.phase === 'merging' && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
          <div className="flex items-center justify-center gap-3">
            <ArrowDownToLine className="w-6 h-6 text-yellow-600 animate-bounce" />
            <span className="text-yellow-800 font-medium">Merging chunks into final file...</span>
          </div>
        </div>
      )}

      {/* Error Display */}
      {progress.error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{progress.error}</p>
        </div>
      )}
    </div>
  );
}
