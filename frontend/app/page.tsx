'use client';

import { useState, useCallback } from 'react';
import FileUpload from '@/components/FileUpload';
import FileList from '@/components/FileList';
import DownloadSection from '@/components/DownloadSection';
import StatusLog, { LogEntry } from '@/components/StatusLog';
import NodeStatus from '@/components/NodeStatus';
import { ShareResponse } from '@/lib/api';
import { generateUniqueId } from '@/lib/utils';

export default function Home() {
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const addLog = useCallback((log: LogEntry) => {
    setLogs((prev) => {
      // If this log has a step number, check if we already have a log for this step
      if (log.step !== undefined && log.totalSteps !== undefined) {
        // Find existing log with same step
        const existingIndex = prev.findIndex(
          (l) => l.step === log.step && l.totalSteps === log.totalSteps
        );
        
        if (existingIndex !== -1) {
          // Update existing log entry
          const updated = [...prev];
          updated[existingIndex] = {
            ...updated[existingIndex],
            type: log.type,
            message: log.message,
            timestamp: log.timestamp,
          };
          return updated;
        }
      }
      
      // Add new log entry
      return [...prev, log];
    });
  }, []);

  const handleFileShared = useCallback((response: ShareResponse) => {
    // File sharing success is already logged in FileUpload component
    // This callback is just for triggering UI updates
  }, []);

  const handleDownload = useCallback(async (infoHash: string) => {
    addLog({
      id: generateUniqueId(),
      timestamp: new Date(),
      type: 'info',
      message: `Download initiated for file: ${infoHash.substring(0, 16)}...`,
    });
    
    // Redirect to download page
    window.location.href = `/download/${infoHash}`;
  }, [addLog]);

  const handleFileListLog = useCallback((message: string) => {
    addLog({
      id: generateUniqueId(),
      timestamp: new Date(),
      type: 'info',
      message,
    });
  }, []);

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <h1 className="text-3xl font-bold text-gray-900">P2P File Sharing System</h1>
          <p className="mt-2 text-gray-600">
            Decentralized file sharing using Kademlia DHT - Share files across your network
          </p>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Node Status */}
        <div className="mb-6">
          <NodeStatus />
        </div>

        {/* Two Column Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* Left Column */}
          <div className="space-y-6">
            <FileUpload onLog={addLog} onFileShared={handleFileShared} />
            <DownloadSection onLog={addLog} />
          </div>

          {/* Right Column */}
          <div>
            <StatusLog logs={logs} title="Activity Log - What's Happening" />
          </div>
        </div>

        {/* Shared Files */}
        <div className="mt-6">
          <FileList onDownload={handleDownload} onLog={handleFileListLog} />
        </div>

        {/* Info Section */}
        <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-blue-900 mb-3">How It Works</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm text-blue-800">
            <div>
              <h4 className="font-semibold mb-2">1. Share Files</h4>
              <p>Upload a file to share it on the P2P network. The file is chunked and hashed automatically.</p>
            </div>
            <div>
              <h4 className="font-semibold mb-2">2. Peer Discovery</h4>
              <p>The system automatically discovers other peers on your network using mDNS and UDP broadcast.</p>
            </div>
            <div>
              <h4 className="font-semibold mb-2">3. Download Files</h4>
              <p>Use the info hash or scan the QR code to download files from other peers in the network.</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
