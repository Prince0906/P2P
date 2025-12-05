'use client';

import { useEffect, useRef } from 'react';
import { CheckCircle2, XCircle, Loader2, Info, AlertCircle } from 'lucide-react';

export interface LogEntry {
  id: string;
  timestamp: Date;
  type: 'info' | 'success' | 'error' | 'warning' | 'loading';
  message: string;
  step?: number;
  totalSteps?: number;
}

interface StatusLogProps {
  logs: LogEntry[];
  title?: string;
}

const iconMap = {
  info: Info,
  success: CheckCircle2,
  error: XCircle,
  warning: AlertCircle,
  loading: Loader2,
};

const colorMap = {
  info: 'text-blue-600',
  success: 'text-green-600',
  error: 'text-red-600',
  warning: 'text-yellow-600',
  loading: 'text-blue-600 animate-spin',
};

export default function StatusLog({ logs, title = 'Activity Log' }: StatusLogProps) {
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <div className="bg-white rounded-lg shadow-md p-6 h-full flex flex-col">
      <h2 className="text-xl font-bold mb-4 text-gray-800">{title}</h2>
      <div className="flex-1 overflow-y-auto space-y-2 min-h-[300px]">
        {logs.length === 0 ? (
          <div className="text-gray-400 text-center py-8">
            No activity yet. Start sharing or downloading files to see what's happening!
          </div>
        ) : (
          logs.map((log, index) => {
            const Icon = iconMap[log.type];
            const colorClass = colorMap[log.type];
            // Use combination of id and index to ensure unique keys
            const uniqueKey = `${log.id}-${index}`;

            return (
              <div
                key={uniqueKey}
                className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors"
              >
                {log.type === 'loading' ? (
                  <div className="flex-shrink-0 mt-0.5">
                    <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
                  </div>
                ) : (
                  <Icon className={`w-5 h-5 ${colorClass} flex-shrink-0 mt-0.5`} />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {log.step && log.totalSteps && (
                      <span className="text-xs font-semibold text-gray-500 bg-gray-200 px-2 py-0.5 rounded">
                        Step {log.step}/{log.totalSteps}
                      </span>
                    )}
                    <span className="text-xs text-gray-400">
                      {log.timestamp.toLocaleTimeString()}
                    </span>
                  </div>
                  <p className={`text-sm mt-1 ${log.type === 'loading' ? 'text-blue-600' : colorClass} font-medium`}>
                    {log.message}
                  </p>
                </div>
              </div>
            );
          })
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}

