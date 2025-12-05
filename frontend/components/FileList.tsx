'use client';

import { useEffect, useState } from 'react';
import { Download, File, Share2, Copy, Check, ExternalLink, Link as LinkIcon } from 'lucide-react';
import { apiClient, FileInfo } from '@/lib/api';
import { QRCodeSVG } from 'qrcode.react';

interface FileListProps {
  onDownload: (infoHash: string) => void;
  onLog: (message: string) => void;
}

export default function FileList({ onDownload, onLog }: FileListProps) {
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState<string | null>(null);

  useEffect(() => {
    loadFiles();
    const interval = setInterval(loadFiles, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const loadFiles = async () => {
    try {
      const fileList = await apiClient.listFiles();
      setFiles(fileList);
    } catch (error: any) {
      onLog(`Error loading files: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const copyToClipboard = async (text: string, type: 'hash' | 'link' = 'hash') => {
    try {
      await navigator.clipboard.writeText(text);
      if (type === 'hash') {
        setCopiedHash(text);
        setTimeout(() => setCopiedHash(null), 2000);
        onLog('Info hash copied to clipboard!');
      } else {
        setCopiedLink(text);
        setTimeout(() => setCopiedLink(null), 2000);
        onLog('Share link copied to clipboard! Send it via WhatsApp, email, or messaging app.');
      }
    } catch (error) {
      onLog('Failed to copy to clipboard');
    }
  };

  const shareLink = (infoHash: string) => {
    if (typeof window !== 'undefined') {
      return `${window.location.origin}/download/${infoHash}`;
    }
    return '';
  };

  const handleWebShare = async (file: FileInfo) => {
    const link = shareLink(file.info_hash);
    const shareData = {
      title: `Download ${file.name}`,
      text: `Download ${file.name} (${formatFileSize(file.size)}) via P2P`,
      url: link,
    };

    try {
      if (navigator.share) {
        await navigator.share(shareData);
        onLog('Shared via native share dialog!');
      } else {
        // Fallback: copy to clipboard
        await copyToClipboard(link, 'link');
      }
    } catch (error: any) {
      if (error.name !== 'AbortError') {
        // User cancelled or error - fallback to copy
        await copyToClipboard(link, 'link');
      }
    }
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-bold mb-4 text-gray-800">Shared Files</h2>
        <div className="text-center py-8 text-gray-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-xl font-bold mb-4 text-gray-800">Shared Files</h2>
      
      {files.length === 0 ? (
        <div className="text-center py-8 text-gray-400">
          No files shared yet. Upload a file to get started!
        </div>
      ) : (
        <div className="space-y-3">
          {files.map((file) => (
            <div
              key={file.info_hash}
              className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3 flex-1">
                  <File className="w-6 h-6 text-blue-600 mt-1" />
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-gray-800 truncate">{file.name}</h3>
                    <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
                      <span>{formatFileSize(file.size)}</span>
                      <span>{file.chunk_count} chunks</span>
                      <span className="font-mono text-xs">{file.info_hash.substring(0, 16)}...</span>
                    </div>
                  </div>
                </div>
                
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onDownload(file.info_hash)}
                    className="p-2 text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                    title="Download"
                  >
                    <Download className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => setSelectedFile(selectedFile === file.info_hash ? null : file.info_hash)}
                    className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                    title="Share"
                  >
                    <Share2 className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => copyToClipboard(file.info_hash)}
                    className="p-2 text-gray-600 hover:bg-gray-50 rounded-lg transition-colors"
                    title="Copy hash"
                  >
                    {copiedHash === file.info_hash ? (
                      <Check className="w-5 h-5 text-green-600" />
                    ) : (
                      <Copy className="w-5 h-5" />
                    )}
                  </button>
                </div>
              </div>

              {selectedFile === file.info_hash && (
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <p className="text-sm font-medium text-gray-700 mb-3">Share this file:</p>
                  
                  {/* Share Link - Most Important */}
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-blue-900 mb-1">Share Link (Click to open):</p>
                        <a
                          href={shareLink(file.info_hash)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm break-all text-blue-600 hover:text-blue-800 hover:underline block mb-2"
                        >
                          {shareLink(file.info_hash)}
                        </a>
                        <p className="text-xs text-blue-700">
                          Copy this link and send it via WhatsApp, email, or messaging app. Others can click it to download!
                        </p>
                      </div>
                      <div className="flex flex-col gap-2">
                        <button
                          onClick={() => copyToClipboard(shareLink(file.info_hash), 'link')}
                          className="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 flex items-center gap-1.5 transition-colors"
                          title="Copy link"
                        >
                          {copiedLink === shareLink(file.info_hash) ? (
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
                        <button
                          onClick={() => handleWebShare(file)}
                          className="px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700 flex items-center gap-1.5 transition-colors"
                          title="Share via..."
                        >
                          <Share2 className="w-3 h-3" />
                          Share
                        </button>
                        <a
                          href={shareLink(file.info_hash)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-3 py-1.5 bg-gray-600 text-white text-xs rounded-lg hover:bg-gray-700 flex items-center gap-1.5 transition-colors text-center"
                          title="Open in new tab"
                        >
                          <ExternalLink className="w-3 h-3" />
                          Open
                        </a>
                      </div>
                    </div>
                  </div>

                  {/* Info Hash - Secondary */}
                  <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 mb-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-semibold text-gray-700 mb-1">Info Hash (for manual download):</p>
                        <p className="font-mono text-xs break-all text-gray-600">{file.info_hash}</p>
                      </div>
                      <button
                        onClick={() => copyToClipboard(file.info_hash, 'hash')}
                        className="px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 rounded transition-colors flex items-center gap-1"
                        title="Copy hash"
                      >
                        {copiedHash === file.info_hash ? (
                          <>
                            <Check className="w-3 h-3 text-green-600" />
                            Copied
                          </>
                        ) : (
                          <>
                            <Copy className="w-3 h-3" />
                            Copy
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* QR Code - Optional, for mobile users */}
                  <div className="flex items-center gap-3">
                    <div className="bg-white p-2 rounded-lg border border-gray-200">
                      <QRCodeSVG value={shareLink(file.info_hash)} size={100} />
                    </div>
                    <div className="flex-1">
                      <p className="text-xs font-medium text-gray-700 mb-1">QR Code (for mobile):</p>
                      <p className="text-xs text-gray-500">
                        If someone is nearby with their phone, they can scan this QR code to download the file.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

