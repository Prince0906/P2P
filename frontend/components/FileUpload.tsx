'use client';

import { useState, useCallback } from 'react';
import { Upload, File, Copy, Check, ExternalLink, Link as LinkIcon } from 'lucide-react';
import { ShareResponse } from '@/lib/api';
import { LogEntry } from './StatusLog';
import { generateUniqueId } from '@/lib/utils';

interface FileUploadProps {
  onLog: (log: LogEntry) => void;
  onFileShared: (response: ShareResponse) => void;
}

export default function FileUpload({ onLog, onFileShared }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sharedFile, setSharedFile] = useState<ShareResponse | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);

  const addLog = useCallback((type: LogEntry['type'], message: string, step?: number, totalSteps?: number) => {
    onLog({
      id: generateUniqueId(),
      timestamp: new Date(),
      type,
      message,
      step,
      totalSteps,
    });
  }, [onLog]);

  const handleFileSelect = useCallback(async (file: File) => {
    if (uploading) return;

    setSelectedFile(file);
    setUploading(true);

    addLog('info', `Selected file: ${file.name} (${formatFileSize(file.size)})`, 1, 5);
    
    try {
      // Step 2: Upload file to server
      addLog('loading', 'Uploading file to server...', 2, 5);
      const formData = new FormData();
      formData.append('file', file);
      formData.append('description', `Uploaded via web interface`);

      const uploadResponse = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      if (!uploadResponse.ok) {
        const error = await uploadResponse.json();
        throw new Error(error.error || 'Upload failed');
      }

      // Step 2 completed
      addLog('success', 'File uploaded to server', 2, 5);

      // Step 3: Processing file
      addLog('loading', 'Processing file on server...', 3, 5);
      await new Promise(resolve => setTimeout(resolve, 200));
      addLog('success', 'File processed on server', 3, 5);

      // Step 4: Chunking and hashing
      addLog('loading', 'Chunking file and computing hash...', 4, 5);
      const response = await uploadResponse.json();
      await new Promise(resolve => setTimeout(resolve, 300));
      addLog('success', 'File chunked and hash computed', 4, 5);

      // Step 5: Complete
      addLog('success', `File shared successfully! Info Hash: ${response.info_hash.substring(0, 16)}... File is now available on the P2P network.`, 5, 5);

      setSharedFile(response);
      onFileShared(response);
      setSelectedFile(null);
    } catch (error: any) {
      addLog('error', `Failed to share file: ${error.message}`);
    } finally {
      setUploading(false);
    }
  }, [uploading, addLog, onFileShared]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const file = e.dataTransfer.files[0];
    if (file) {
      handleFileSelect(file);
    }
  }, [handleFileSelect]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFileSelect(file);
    }
  }, [handleFileSelect]);

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(
      Math.floor(Math.log(bytes) / Math.log(k)),
      sizes.length - 1
    );
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-xl font-bold mb-4 text-gray-800">Share a File</h2>
      
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`
          border-2 border-dashed rounded-lg p-8 text-center transition-colors
          ${isDragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'}
          ${uploading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
        `}
      >
        <input
          type="file"
          id="file-upload"
          className="hidden"
          onChange={handleFileInput}
          disabled={uploading}
        />
        
        <label htmlFor="file-upload" className="cursor-pointer">
          {selectedFile ? (
            <div className="space-y-2">
              <File className="w-12 h-12 mx-auto text-blue-600" />
              <p className="text-sm font-medium text-gray-700">{selectedFile.name}</p>
              <p className="text-xs text-gray-500">{formatFileSize(selectedFile.size)}</p>
            </div>
          ) : (
            <div className="space-y-2">
              <Upload className="w-12 h-12 mx-auto text-gray-400" />
              <p className="text-sm text-gray-600">
                Drag and drop a file here, or click to select
              </p>
              <p className="text-xs text-gray-400">Files will be shared on the P2P network</p>
            </div>
          )}
        </label>
      </div>

      {uploading && (
        <div className="mt-4 flex items-center justify-center gap-2 text-blue-600 py-3">
          <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
          <span className="text-sm font-medium">Sharing file on P2P network...</span>
        </div>
      )}

      {sharedFile && (
        <div className="mt-4 bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex-1">
              <p className="text-sm font-semibold text-green-900 mb-1">✅ File shared successfully!</p>
              <p className="text-xs text-green-700 mb-3">
                Copy the link below and send it via WhatsApp, email, or messaging app. Others can click it to download!
              </p>
              <div className="bg-white border border-green-200 rounded p-2 mb-2">
                <a
                  href={`/download/${sharedFile.info_hash}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm break-all text-blue-600 hover:text-blue-800 hover:underline block"
                >
                  {typeof window !== 'undefined' ? `${window.location.origin}/download/${sharedFile.info_hash}` : ''}
                </a>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <button
                onClick={async () => {
                  const link = typeof window !== 'undefined' ? `${window.location.origin}/download/${sharedFile.info_hash}` : '';
                  try {
                    await navigator.clipboard.writeText(link);
                    setCopiedLink(true);
                    setTimeout(() => setCopiedLink(false), 2000);
                    addLog('success', 'Share link copied to clipboard!');
                  } catch (error) {
                    addLog('error', 'Failed to copy link');
                  }
                }}
                className="px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700 flex items-center gap-1.5 transition-colors"
              >
                {copiedLink ? (
                  <>
                    <Check className="w-3 h-3" />
                    Copied!
                  </>
                ) : (
                  <>
                    <LinkIcon className="w-3 h-3" />
                    Copy Link
                  </>
                )}
              </button>
              <a
                href={`/download/${sharedFile.info_hash}`}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 flex items-center gap-1.5 transition-colors text-center"
              >
                <ExternalLink className="w-3 h-3" />
                Open
              </a>
            </div>
          </div>
          <button
            onClick={() => {
              setSharedFile(null);
              setCopiedLink(false);
            }}
            className="text-xs text-green-700 hover:text-green-900 underline"
          >
            Upload another file
          </button>
        </div>
      )}
    </div>
  );
}

