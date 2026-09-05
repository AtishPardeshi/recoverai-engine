import React from "react";
import type { ActivityFeedItem } from "../types";
import { CheckCircle2, AlertTriangle, XCircle, Info, ShieldCheck, Clock } from "lucide-react";

interface AuditTimelineProps {
  activityFeed: ActivityFeedItem[];
  onRefresh: () => void;
}

export const AuditTimeline: React.FC<AuditTimelineProps> = ({ activityFeed, onRefresh }) => {
  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-6 shadow-xl space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-gray-300 flex items-center space-x-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Immutable Recovery Activity & Audit Feed</span>
          </h2>
          <p className="text-xs text-gray-400">Database-backed chronological event ledger with deterministic correlation IDs</p>
        </div>
        <button
          onClick={onRefresh}
          className="text-xs font-semibold text-gray-400 hover:text-white bg-gray-800 px-3 py-1.5 rounded-lg transition-colors"
        >
          Refresh Feed
        </button>
      </div>

      <div className="divide-y divide-gray-800/80 rounded-xl border border-gray-800/80 overflow-hidden bg-gray-950/40">
        {activityFeed.length === 0 ? (
          <div className="p-8 text-center text-xs text-gray-500">No activity events recorded yet.</div>
        ) : (
          activityFeed.map((item) => {
            const isSuccess = item.status === "SUCCESS";
            const isWarning = item.status === "WARNING";
            const isFailure = item.status === "FAILURE";

            return (
              <div
                key={item.id}
                className="p-4 hover:bg-gray-900/60 transition-colors flex items-start justify-between gap-4"
              >
                <div className="flex items-start space-x-3">
                  <div
                    className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 ${
                      isSuccess
                        ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                        : isWarning
                        ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                        : isFailure
                        ? "bg-red-500/20 text-red-400 border border-red-500/30"
                        : "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                    }`}
                  >
                    {isSuccess ? (
                      <CheckCircle2 className="w-4 h-4" />
                    ) : isWarning ? (
                      <AlertTriangle className="w-4 h-4" />
                    ) : isFailure ? (
                      <XCircle className="w-4 h-4" />
                    ) : (
                      <Info className="w-4 h-4" />
                    )}
                  </div>

                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-bold text-gray-200">{item.title}</span>
                      <span className="text-[10px] font-mono bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">
                        {item.event_type}
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">{item.description}</p>
                    <div className="text-[10px] text-gray-500 font-mono mt-1">
                      Correlation: {item.correlation_id}
                    </div>
                  </div>
                </div>

                <div className="text-[11px] text-gray-500 whitespace-nowrap flex items-center space-x-1">
                  <Clock className="w-3 h-3" />
                  <span>{new Date(item.timestamp).toLocaleTimeString()}</span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
