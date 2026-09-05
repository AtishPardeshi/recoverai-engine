import React from "react";
import { TrendingUp, AlertOctagon, Sparkles, Activity, Layers, Database } from "lucide-react";
import type { DashboardSummary } from "../types";

interface KPICardsProps {
  summary: DashboardSummary | null;
  activeScope?: "CURRENT_BATCH" | "CUMULATIVE";
  onScopeChange?: (scope: "CURRENT_BATCH" | "CUMULATIVE") => void;
}

export const KPICards: React.FC<KPICardsProps> = ({
  summary,
  activeScope = "CURRENT_BATCH",
  onScopeChange,
}) => {
  if (!summary) return null;

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  const isBatchScope = (summary.scope || activeScope) === "CURRENT_BATCH";

  return (
    <div className="space-y-4">
      {/* Scope Indicator & Segmented Selector Banner */}
      <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-3.5 shadow-lg flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs uppercase font-extrabold text-white">Dashboard Scope:</span>
              <span
                className={`text-xs font-mono font-bold px-2.5 py-0.5 rounded-full border ${
                  isBatchScope
                    ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                    : "bg-blue-500/20 text-blue-300 border-blue-500/40"
                }`}
              >
                {isBatchScope ? `CURRENT BATCH (${summary.batch_id || "LATEST"})` : "CUMULATIVE DATABASE (1,000 CASES)"}
              </span>
            </div>
            <p className="text-[11px] text-gray-400 mt-0.5">
              {isBatchScope
                ? "Displaying strictly candidate, intervention, and captured outcome records for the selected batch."
                : "Displaying aggregated all-time recovery outcomes across historical database records."}
            </p>
          </div>
        </div>

        {/* Scope Toggle Control */}
        {onScopeChange && (
          <div className="flex items-center space-x-1 bg-gray-950 p-1 rounded-xl border border-gray-800">
            <button
              onClick={() => onScopeChange("CURRENT_BATCH")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center space-x-1.5 ${
                isBatchScope
                  ? "bg-emerald-600 text-white shadow-sm"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Current Batch</span>
            </button>
            <button
              onClick={() => onScopeChange("CUMULATIVE")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center space-x-1.5 ${
                !isBatchScope
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              <Database className="w-3.5 h-3.5" />
              <span>Cumulative DB</span>
            </button>
          </div>
        )}
      </div>

      {/* TOP 4 HERO KPI CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. HERO KPI: REVENUE RECOVERED */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-emerald-950/80 via-gray-900 to-gray-900 border border-emerald-500/40 p-5 shadow-xl glow-emerald">
          <div className="absolute top-0 right-0 p-4 opacity-15">
            <Sparkles className="w-20 h-20 text-emerald-400" />
          </div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs uppercase font-extrabold tracking-wider text-emerald-400 flex items-center space-x-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              <span>Revenue Recovered</span>
            </span>
            <span className="text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded-full">
              Verified Captured
            </span>
          </div>
          <div className="text-3xl lg:text-4xl font-black text-white tracking-tight">
            {formatCurrency(summary.recovered_revenue)}
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-gray-400 border-t border-gray-800/80 pt-2.5">
            <span>Baseline: <strong className="text-gray-300">{formatCurrency(summary.baseline_recovered_revenue)}</strong></span>
            <span className="text-emerald-400 font-semibold">{summary.successful_recoveries_count} Recovered</span>
          </div>
        </div>

        {/* 2. INCREMENTAL REVENUE */}
        <div className="rounded-2xl bg-gradient-to-br from-blue-950/50 via-gray-900 to-gray-900 border border-blue-500/40 p-5 shadow-md hover:border-blue-500/60 transition-all">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs uppercase font-bold text-blue-400 flex items-center space-x-1.5">
              <TrendingUp className="w-4 h-4 text-blue-400" />
              <span>Incremental Revenue</span>
            </span>
            <span className="text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30 px-2 py-0.5 rounded-full">
              Net AI Lift
            </span>
          </div>
          <div className="text-3xl font-black text-blue-400 tracking-tight">
            {formatCurrency(summary.incremental_recovered_revenue)}
          </div>
          <div className="mt-3 text-[11px] text-gray-400 border-t border-gray-800/80 pt-2.5">
            Agent Recovered Revenue − Baseline Recovery
          </div>
        </div>

        {/* 3. REVENUE AT RISK */}
        <div className="rounded-2xl bg-gray-900/90 border border-gray-800 p-5 shadow-md hover:border-gray-700 transition-all">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs uppercase font-bold text-gray-400 flex items-center space-x-1.5">
              <AlertOctagon className="w-4 h-4 text-amber-400" />
              <span>Revenue at Risk</span>
            </span>
            <span className="text-[10px] font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded-full">
              Unrecovered Pool
            </span>
          </div>
          <div className="text-3xl font-black text-amber-300 tracking-tight">
            {formatCurrency(summary.revenue_at_risk)}
          </div>
          <div className="mt-3 text-[11px] text-gray-400 border-t border-gray-800/80 pt-2.5">
            {summary.active_cases_count} active recoverable payment declines
          </div>
        </div>

        {/* 4. RECOVERY RATE */}
        <div className="rounded-2xl bg-gray-900/90 border border-gray-800 p-5 shadow-md hover:border-gray-700 transition-all">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs uppercase font-bold text-gray-400 flex items-center space-x-1.5">
              <Activity className="w-4 h-4 text-purple-400" />
              <span>Recovery Rate</span>
            </span>
            <span className="text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30 px-2 py-0.5 rounded-full">
              Win-back %
            </span>
          </div>
          <div className="text-3xl font-black text-purple-400 tracking-tight">
            {(summary.recovery_rate * 100).toFixed(1)}%
          </div>
          <div className="mt-3 text-[11px] text-gray-400 border-t border-gray-800/80 pt-2.5">
            {summary.successful_recoveries_count} of {summary.total_cases_count} resolved cases
          </div>
        </div>
      </div>
    </div>
  );
};
