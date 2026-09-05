import React from "react";
import { Search, ArrowUpRight, Zap, RefreshCw } from "lucide-react";
import type { RecoveryCase } from "../types";

interface CaseQueueProps {
  cases: RecoveryCase[];
  onSelectCase: (caseItem: RecoveryCase) => void;
  onRefresh?: () => void;
  statusFilter: string;
  setStatusFilter: (s: string) => void;
  searchQuery: string;
  setSearchQuery: (s: string) => void;
}

export const CaseQueue: React.FC<CaseQueueProps> = ({
  cases,
  onSelectCase,
  onRefresh,
  statusFilter,
  setStatusFilter,
  searchQuery,
  setSearchQuery,
}) => {
  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-6 shadow-xl space-y-4">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-gray-300 flex items-center space-x-2">
            <Zap className="w-4 h-4 text-emerald-400" />
            <span>Autonomous Recovery Queue</span>
          </h2>
          <p className="text-xs text-gray-400">Prioritized by expected value: P(recovery) × Amount × Customer Value Factor</p>
        </div>

        {/* Filters & Search */}
        <div className="flex items-center space-x-2.5">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search TX or Customer..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-gray-950/80 border border-gray-800 rounded-xl pl-8 pr-3 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500/50 w-44 sm:w-56"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-gray-950/80 border border-gray-800 rounded-xl px-3 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-emerald-500/50"
          >
            <option value="">All Statuses</option>
            <option value="RECOVERY_ELIGIBLE">Eligible</option>
            <option value="RECOVERY_IN_PROGRESS">In Progress</option>
            <option value="RECOVERED">Recovered</option>
            <option value="RECOVERY_EXHAUSTED">Exhausted</option>
            <option value="STOPPED">Stopped</option>
          </select>

          {onRefresh && (
            <button
              onClick={onRefresh}
              className="p-2 rounded-xl bg-gray-950/80 border border-gray-800 text-gray-400 hover:text-white transition-colors"
              title="Refresh Queue"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Case Table */}
      <div className="overflow-x-auto rounded-xl border border-gray-800/80">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-gray-950/90 text-gray-400 border-b border-gray-800 text-[11px] uppercase tracking-wider">
              <th className="py-3 px-4">Transaction / Customer</th>
              <th className="py-3 px-4">Revenue at Risk</th>
              <th className="py-3 px-4">P(Recovery)</th>
              <th className="py-3 px-4">Expected Recovery</th>
              <th className="py-3 px-4">Priority Score</th>
              <th className="py-3 px-4">Failure Reason</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60 bg-gray-900/40">
            {cases.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-gray-500">
                  No recovery cases found matching criteria.
                </td>
              </tr>
            ) : (
              cases.map((c) => {
                const isDemo = c.transaction?.external_id === "TX-DEMO-001";
                return (
                  <tr
                    key={c.id}
                    onClick={() => onSelectCase(c)}
                    className={`hover:bg-gray-800/60 cursor-pointer transition-colors ${
                      isDemo ? "bg-emerald-950/20 border-l-4 border-l-emerald-400" : ""
                    }`}
                  >
                    <td className="py-3.5 px-4">
                      <div className="flex items-center space-x-2">
                        <span className="font-extrabold text-white">{c.transaction?.external_id}</span>
                        {isDemo && (
                          <span className="text-[9px] font-black uppercase bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 px-1.5 py-0.5 rounded">
                            Demo
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-gray-400">{c.transaction?.customer?.name}</div>
                    </td>

                    <td className="py-3.5 px-4 font-bold text-white">
                      {formatCurrency(c.revenue_at_risk)}
                    </td>

                    <td className="py-3.5 px-4">
                      <div className="flex items-center space-x-1.5">
                        <div className="w-12 bg-gray-800 rounded-full h-1.5 overflow-hidden">
                          <div
                            className="bg-emerald-400 h-full rounded-full"
                            style={{ width: `${c.recovery_probability * 100}%` }}
                          />
                        </div>
                        <span className="font-extrabold text-emerald-400">
                          {(c.recovery_probability * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>

                    <td className="py-3.5 px-4 font-bold text-gray-200">
                      {formatCurrency(c.expected_recovery)}
                    </td>

                    <td className="py-3.5 px-4 font-extrabold text-purple-400">
                      {c.priority_score.toFixed(0)}
                    </td>

                    <td className="py-3.5 px-4 text-gray-300">
                      <span className="text-[11px] bg-gray-800/80 px-2 py-0.5 rounded text-gray-300">
                        {c.transaction?.payment_failure?.normalized_failure_type || "UNKNOWN"}
                      </span>
                    </td>

                    <td className="py-3.5 px-4">
                      <span
                        className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full border ${
                          c.status === "RECOVERED"
                            ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                            : c.status === "RECOVERY_ELIGIBLE"
                            ? "bg-blue-500/20 text-blue-300 border-blue-500/40"
                            : c.status === "STOPPED"
                            ? "bg-red-500/20 text-red-300 border-red-500/40"
                            : "bg-gray-800 text-gray-400 border-gray-700"
                        }`}
                      >
                        {c.status}
                      </span>
                    </td>

                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectCase(c);
                        }}
                        className="inline-flex items-center space-x-1 text-xs font-bold text-emerald-400 hover:text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 px-2.5 py-1 rounded-lg transition-all"
                      >
                        <span>Inspect & Execute</span>
                        <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
