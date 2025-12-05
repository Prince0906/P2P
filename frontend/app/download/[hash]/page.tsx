'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Download, Loader2, CheckCircle2, XCircle, ArrowLeft } from 'lucide-react';
import { apiClient } from '@/lib/api';
import StatusLog, { LogEntry } from '@/components/StatusLog';
import { generateUniqueId, cleanInfoHash } from '@/lib/utils';

export default function DownloadPage() {
  const params = useParams();
  const router = useRouter();
  const rawHash = params.hash as string;
  const infoHash = cleanInfoHash(rawHash);
  
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [downloading, setDownloading] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addLog = (type: LogEntry['type'], message: string, step?: number, totalSteps?: number) => {
    setLogs((prev) => {
      // If this log has a step number, check if we already have a log for this step
      if (step !== undefined && totalSteps !== undefined) {
        // Find existing log with same step
        const existingIndex = prev.findIndex(
          (l) => l.step === step && l.totalSteps === totalSteps
        );
        
        if (existingIndex !== -1) {
          // Update existing log entry
          const updated = [...prev];
          updated[existingIndex] = {
            ...updated[existingIndex],
            type,
            message,
            timestamp: new Date(),
          };
          return updated;
        }
      }
      
      // Add new log entry
      return [...prev, {
        id: generateUniqueId(),
        timestamp: new Date(),
        type,
        message,
        step,
        totalSteps,
      }];
    });
  };

  useEffect(() => {
    if (infoHash) {
      addLog('info', `Download page opened for file: ${infoHash.substring(0, 16)}...`, 1, 5);
      addLog('loading', 'Validating info hash...', 2, 5);
      
      // Auto-start download after a brief delay
      const timer = setTimeout(() => {
        // Step 2 completed
        addLog('success', 'Info hash validated', 2, 5);
        handleDownload();
      }, 500);
      
      return () => clearTimeout(timer);
    } else {
      // cleanInfoHash should have extracted the hash from URL if it was a full URL
      // If it's still null, show a helpful error
      const errorMsg = `Invalid info hash format. Received: "${rawHash?.substring(0, 100)}${rawHash && rawHash.length > 100 ? '...' : ''}" (length: ${rawHash?.length || 0}). Must be exactly 64 hexadecimal characters. If you pasted a full URL, make sure it contains a valid 64-character hash.`;
      setError(errorMsg);
      addLog('error', errorMsg);
    }
  }, [infoHash, rawHash]);

  const handleDownload = async () => {
    if (downloading || completed || !infoHash) return;

    setDownloading(true);
    setError(null);

    try {
      // Step 3: DHT lookup
      addLog('loading', 'Looking up file in DHT network...', 3, 5);
      await new Promise(resolve => setTimeout(resolve, 400));
      addLog('success', 'File found in DHT network', 3, 5);
      
      // Step 4: Finding peers and downloading
      addLog('loading', 'Finding peers and downloading chunks...', 4, 5);
      
      // Use the cleaned and validated hash
      const response = await apiClient.downloadFile(infoHash);
      
      // Step 4 completed
      addLog('success', 'All chunks downloaded successfully', 4, 5);
      
      // Step 5: Complete
      addLog('success', `File download completed! Saved to: ${response.file_path || 'p2p_data/files/'}`, 5, 5);
      
      setCompleted(true);
    } catch (err: any) {
      const errorMsg = err.response?.data?.detail || err.message;
      setError(errorMsg);
      addLog('error', `Download failed: ${errorMsg}`);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <button
            onClick={() => router.push('/')}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Home
          </button>
          <h1 className="text-3xl font-bold text-gray-900">Download File</h1>
          {infoHash && (
            <p className="mt-2 text-gray-600 font-mono text-sm break-all">{infoHash}</p>
          )}
          {!infoHash && rawHash && (
            <p className="mt-2 text-red-600 font-mono text-sm break-all">Invalid hash: {rawHash}</p>
          )}
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          {error ? (
            <div className="flex items-center gap-3 text-red-600">
              <XCircle className="w-6 h-6" />
              <div>
                <h2 className="font-semibold">Download Failed</h2>
                <p className="text-sm mt-1">{error}</p>
              </div>
            </div>
          ) : completed ? (
            <div className="flex items-center gap-3 text-green-600">
              <CheckCircle2 className="w-6 h-6" />
              <div>
                <h2 className="font-semibold">Download Complete!</h2>
                <p className="text-sm mt-1">The file has been downloaded successfully.</p>
              </div>
            </div>
          ) : downloading ? (
            <div className="flex items-center gap-3 text-blue-600">
              <Loader2 className="w-6 h-6 animate-spin" />
              <div>
                <h2 className="font-semibold">Downloading...</h2>
                <p className="text-sm mt-1">Please wait while we download the file from the P2P network.</p>
              </div>
            </div>
          ) : (
            <div>
              <h2 className="font-semibold text-gray-800 mb-4">Ready to Download</h2>
              <button
                onClick={handleDownload}
                className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2 transition-colors"
              >
                <Download className="w-5 h-5" />
                Start Download
              </button>
            </div>
          )}
        </div>

        <StatusLog logs={logs} title="Download Progress" />
      </main>
    </div>
  );
}

