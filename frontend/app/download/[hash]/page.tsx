'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { cleanInfoHash } from '@/lib/utils';
import DownloadVisualizer from '@/components/DownloadVisualizer';

export default function DownloadPage() {
  const params = useParams();
  const router = useRouter();
  const rawHash = params.hash as string;
  const infoHash = cleanInfoHash(rawHash);

  const [completed, setCompleted] = useState(false);
  const [filePath, setFilePath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!infoHash && rawHash) {
      setError(`Invalid info hash format. Received: "${rawHash?.substring(0, 100)}${rawHash && rawHash.length > 100 ? '...' : ''}" (length: ${rawHash?.length || 0}). Must be exactly 64 hexadecimal characters.`);
    }
  }, [infoHash, rawHash]);

  const handleComplete = (path: string) => {
    setCompleted(true);
    setFilePath(path);
  };

  const handleError = (err: string) => {
    setError(err);
  };

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
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
          {error && !infoHash && (
            <p className="mt-2 text-red-600 font-mono text-sm break-all">{error}</p>
          )}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {infoHash ? (
          <DownloadVisualizer
            infoHash={infoHash}
            onComplete={handleComplete}
            onError={handleError}
          />
        ) : (
          <div className="bg-white rounded-lg shadow-md p-6">
            <p className="text-red-600">{error || 'Invalid info hash'}</p>
          </div>
        )}

        {completed && filePath && (
          <div className="mt-6 bg-green-50 border border-green-200 rounded-lg p-6">
            <h3 className="font-semibold text-green-800 mb-2">✅ Download Complete!</h3>
            <p className="text-green-700">File saved to: <code className="bg-green-100 px-2 py-1 rounded">{filePath}</code></p>
          </div>
        )}
      </main>
    </div>
  );
}
