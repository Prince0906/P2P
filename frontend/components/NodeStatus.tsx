'use client';

import { useEffect, useState } from 'react';
import { Activity, Users, HardDrive, Network } from 'lucide-react';
import { apiClient, NodeStatus as NodeStatusType } from '@/lib/api';

export default function NodeStatus() {
  const [status, setStatus] = useState<NodeStatusType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 3000); // Refresh every 3 seconds
    return () => clearInterval(interval);
  }, []);

  const loadStatus = async () => {
    try {
      const data = await apiClient.getStatus();
      setStatus(data);
      setError(null);
    } catch (error: any) {
      console.error('Failed to load status:', error);
      if (error.code === 'ERR_NETWORK' || error.message?.includes('Network Error')) {
        setError('Cannot connect to backend. Make sure backend is running on http://localhost:8080');
      } else {
        setError(error.message || 'Failed to load status');
      }
    } finally {
      setLoading(false);
    }
  };

  if (loading && !status) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-bold mb-4 text-gray-800">Node Status</h2>
        <div className="text-center py-4 text-gray-400">Loading...</div>
      </div>
    );
  }

  if (error && !status) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-xl font-bold mb-4 text-gray-800">Node Status</h2>
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800 font-semibold mb-2">⚠️ Connection Error</p>
          <p className="text-sm text-red-700 mb-3">{error}</p>
          <div className="text-xs text-red-600 space-y-1">
            <p><strong>Fix:</strong></p>
            <ol className="list-decimal list-inside space-y-1 ml-2">
              <li>Make sure backend is running: <code className="bg-red-100 px-1 rounded">python cli.py start</code></li>
              <li>Check backend is on port 8080</li>
              <li>Verify .env.local has: <code className="bg-red-100 px-1 rounded">NEXT_PUBLIC_API_URL=http://localhost:8080</code></li>
              <li>Restart frontend: <code className="bg-red-100 px-1 rounded">npm run dev</code></li>
            </ol>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-xl font-bold mb-4 text-gray-800">Node Status</h2>
      
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-blue-50 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-5 h-5 text-blue-600" />
            <span className="text-sm font-medium text-gray-600">Status</span>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${status.running ? 'bg-green-500' : 'bg-red-500'}`}></div>
            <span className="text-lg font-bold text-gray-800">
              {status.running ? 'Running' : 'Stopped'}
            </span>
          </div>
        </div>

        <div className="bg-green-50 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <Network className="w-5 h-5 text-green-600" />
            <span className="text-sm font-medium text-gray-600">DHT Nodes</span>
          </div>
          <span className="text-2xl font-bold text-gray-800">{status.dht_nodes}</span>
        </div>

        <div className="bg-purple-50 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <Users className="w-5 h-5 text-purple-600" />
            <span className="text-sm font-medium text-gray-600">Peers</span>
          </div>
          <span className="text-2xl font-bold text-gray-800">{status.discovered_peers}</span>
        </div>

        <div className="bg-orange-50 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <HardDrive className="w-5 h-5 text-orange-600" />
            <span className="text-sm font-medium text-gray-600">Shared Files</span>
          </div>
          <span className="text-2xl font-bold text-gray-800">{status.shared_files}</span>
        </div>
      </div>

      <div className="mt-4 pt-4 border-t border-gray-200">
        <p className="text-xs text-gray-500 font-mono">Node ID: {status.node_id}</p>
      </div>
    </div>
  );
}

