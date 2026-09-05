import React from "react";
import { TrendingUp, AlertOctagon, Sparkles, ShieldCheck, Activity, Layers, Database } from "lucide-react";
import type { DashboardSummary } from "../types";

interface KPICardsProps {
  summary: DashboardSummary | null;
}

export const KPICards: React.FC<KPICardsProps> = ({ summary }) => {
  if (!summary) return null;

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  const isBatchScope = summary.scope === "CURRENT_BATCH" && summary.batch_id;

  return (
    <div className="space-y-3">
      {/* Scope Indicator Banner */}
      <div className="flex items-center justify-between px-1 text-xs">
        <div className="flex items-center space-x-2">
          <Layers className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-gray-400 font-medium">Dashboard Scope:</span>
          {isBatchScope ? (
            <span className="font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 px-2.5 py-0.5 rounded-full font-mono text-[11px]">
              CURRENT BATCH ({summary.batch_id})
            </span>
          ) : (
            <span className="font-bold bg-blue-500/20 text-blue-300 border border-blue-500/40 px-2.5 py-0.5 rounded-full font-mono text-[11px]">
              ALL-TIME CUMULATIVE DATABASE
            </span>
          )}
        </div>
        {summary.cumulative_recovered_revenue !== undefined && isBatchScope && (
          <div className="hidden md:flex items-center space-x-3 text-gray-400 text-[11px]">
            <span className="flex items-center space-x-1">
              <Database className="w-3 h-3 text-gray-500" />
              <span>Cumulative DB Recovered:</span>
              <strong className="text-gray-200">{formatCurrency(summary.cumulative_recovered_revenue)}</strong>
            </span>
            <span>•</span>
            <span>
              Cumulative Lift: <strong className="text-emerald-400">+{formatCurrency(summary.cumulative_incremental_recovered_revenue || 0)}</strong>
            </span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        {/* 1. HERO KPI: ₹ MONEY RECOVERED */}
        <div className="xl:col-span-2 relative overflow-hidden rounded-2xl bg-gradient-to-br from-emerald-950/80 via-gray-900 to-gray-900 border border-emerald-500/40 p-5 shadow-xl glow-emerald">
          <div className="absolute top-0 right-0 p-4 opacity-15">
            <Sparkles className="w-24 h-24 text-emerald-400" />
          </div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs uppercase font-extrabold tracking-wider text-emerald-400 flex items-center space-x-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              <span>{isBatchScope ? "Batch Money Recovered" : "Actual Money Recovered"}</span>
            </span>
            <span className="text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded-full">
              Database Verified
            </span>
          </div>
          <div className="text-3xl lg:text-4xl font-black text-white tracking-tight">
            {formatCurrency(summary.recovered_revenue)}
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-gray-400 border-t border-gray-800/80 pt-2.5">
            <span>
              Baseline Organic: <strong className="text-gray-300">{formatCurrency(summary.baseline_recovered_revenue)}</strong>
            </span>
            <span className="text-emerald-400 font-semibold flex items-center space-x-1">
              <TrendingUp className="w-3.5 h-3.5" />
              <span>+{formatCurrency(summary.incremental_recovered_revenue)} Incremental</span>
            </span>
          </div>
        </div>

        {/* 2. REVENUE AT RISK */}
        <div className="rounded-2xl bg-gray-900/90 border border-gray-800 p-5 shadow-md hover:border-gray-700 transition-all">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs uppercase font-bold text-gray-400 flex items-center space-x-1">
              <AlertOctagon className="w-3.5 h-3.5 text-amber-400" />
              <span>Revenue at Risk</span>
            </span>
          </div>
          <div className="text-2xl font-black text-amber-300 tracking-tight">
            {formatCurrency(summary.revenue_at_risk)}
          </div>
          <p className="text-[11px] text-gray-400 mt-2">
            {summary.active_cases_count} active recoverable cases
          </p>
        </div>

        {/* 3. INCREMENTAL RECOVERY */}
        <div className="rounded-2xl bg-gray-900/90 border border-gray-800 p-5 shadow-md hover:border-gray-700 transition-all">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs uppercase font-bold text-gray-400 flex items-center space-x-1">
              <TrendingUp className="w-3.5 h-3.5 text-blue-400" />
              <span>AI Incremental Lift</span>
            </span>
          </div>
          <div className="text-2xl font-black text-blue-400 tracking-tight">
            {formatCurrency(summary.incremental_recovered_revenue)}
          </div>
          <p className="text-[11px] text-gray-400 mt-2">
            Agent minus Baseline
          </p>
        </div>

        {/* 4. RECOVERY RATE */}
        <div className="rounded-2xl bg-gray-900/90 border border-gray-800 p-5 shadow-md hover:border-gray-700 transition-all">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs uppercase font-bold text-gray-400 flex items-center space-x-1">
              <Activity className="w-3.5 h-3.5 text-purple-400" />
              <span>Recovery Rate</span>
            </span>
          </div>
          <div className="text-2xl font-black text-purple-400 tracking-tight">
            {(summary.recovery_rate * 100).toFixed(1)}%
          </div>
          <p className="text-[11px] text-gray-400 mt-2">
            {summary.successful_recoveries_count} of {summary.total_cases_count} resolved
          </p>
        </div>

        {/* 5. GUARDRAIL COMPLIANCE */}
        <div className="rounded-2xl bg-gray-900/90 border border-gray-800 p-5 shadow-md hover:border-gray-700 transition-all">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs uppercase font-bold text-gray-400 flex items-center space-x-1">
              <ShieldCheck className="w-3.5 h-3.5 text-teal-400" />
              <span>Policy Guardrails</span>
            </span>
          </div>
          <div className="text-2xl font-black text-teal-400 tracking-tight">
            {summary.guardrail_rejections_count} Blocked
          </div>
          <p className="text-[11px] text-gray-400 mt-2">
            Cooldowns & opt-outs enforced
          </p>
        </div>
      </div>
    </div>
  );
};
