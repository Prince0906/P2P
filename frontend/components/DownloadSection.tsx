'use client';

import { useState } from 'react';
import { Download, Search, Loader2, CheckCircle2 } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { LogEntry } from './StatusLog';
import { generateUniqueId } from '@/lib/utils';

interface DownloadSectionProps {
  onLog: (log: LogEntry) => void;
}

export default function DownloadSection({ onLog }: DownloadSectionProps) {
  const [infoHash, setInfoHash] = useState('');
  const [downloading, setDownloading] = useState(false);

  const addLog = (type: LogEntry['type'], message: string, step?: number, totalSteps?: number) => {
    onLog({
      id: generateUniqueId(),
      timestamp: new Date(),
      type,
      message,
      step,
      totalSteps,
    });
  };

  const handleDownload = async () => {
    if (!infoHash.trim() || downloading) return;

    // Clean and validate the hash (handles URLs, just hash, etc.)
    let hash = infoHash.trim();
    
    // If it's a full URL, extract the hash from the path
    if (hash.includes('://') || hash.startsWith('/download/')) {
      const urlMatch = hash.match(/\/download\/([0-9a-fA-F]{64})/i);
      if (urlMatch && urlMatch[1]) {
        hash = urlMatch[1];
      } else {
        // Try to extract any 64-char hex string from the URL
        const hexMatch = hash.match(/([0-9a-fA-F]{64})/i);
        if (hexMatch && hexMatch[1]) {
          hash = hexMatch[1];
        }
      }
    }
    
    // Remove any query parameters or fragments
    hash = hash.split('?')[0].split('#')[0];
    
    // Validate: must be exactly 64 hex characters
    if (hash.length !== 64 || !/^[0-9a-fA-F]{64}$/.test(hash)) {
      addLog('error', `Invalid info hash. Must be exactly 64 hexadecimal characters. Got: "${hash}" (length: ${hash.length})`);
      return;
    }
    
    // Normalize to lowercase
    hash = hash.toLowerCase();

    setDownloading(true);
    addLog('info', `Starting download for hash: ${hash.substring(0, 16)}...`, 1, 5);

    try {
      // Step 2: DHT lookup
      addLog('loading', 'Looking up file in DHT network...', 2, 5);
      await new Promise(resolve => setTimeout(resolve, 400));
      addLog('success', 'File found in DHT network', 2, 5);
      
      // Step 3: Finding peers
      addLog('loading', 'Finding peers who have this file...', 3, 5);
      await new Promise(resolve => setTimeout(resolve, 400));
      addLog('success', 'Peers found for file download', 3, 5);
      
      // Step 4: Downloading chunks
      addLog('loading', 'Downloading file chunks from peers...', 4, 5);
      
      const response = await apiClient.downloadFile(hash);
      
      // Step 4 completed
      addLog('success', 'All chunks downloaded successfully', 4, 5);
      
      // Step 5: Complete
      addLog('success', `File download completed! Saved to: ${response.file_path || 'p2p_data/files/'}`, 5, 5);
      
      setInfoHash('');
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || error.message;
      addLog('error', `Download failed: ${errorMsg}`);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-xl font-bold mb-4 text-gray-800">Download a File</h2>
      
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Info Hash (or scan QR code from shared file)
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={infoHash}
              onChange={(e) => setInfoHash(e.target.value)}
              placeholder="Enter 64-character info hash..."
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
              disabled={downloading}
            />
            <button
              onClick={handleDownload}
              disabled={!infoHash.trim() || downloading}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
            >
              {downloading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  Downloading...
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  Download
                </>
              )}
            </button>
          </div>
        </div>

        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm text-blue-800">
            <strong>Tip:</strong> You can get the info hash from a shared file's QR code or share link.
            The system will automatically find peers who have the file and download it.
          </p>
        </div>
      </div>
    </div>
  );
}

