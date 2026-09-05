import React from "react";
import { TrendingUp, AlertOctagon, CheckCircle2, ShieldCheck } from "lucide-react";
import type { DashboardSummary } from "../types";

interface RevenueOverviewProps {
  summary: DashboardSummary | null;
}

export const RevenueOverview: React.FC<RevenueOverviewProps> = ({ summary }) => {
  if (!summary) return null;

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  const revenueAtRisk = summary.revenue_at_risk;
  const baselineRecovery = summary.baseline_recovered_revenue;
  const agentRecovery = summary.recovered_revenue;
  const incrementalRecovery = summary.incremental_recovered_revenue;

  // Percentage calculations against total revenue at risk (capped for clean visualization)
  const baselinePct = revenueAtRisk > 0 ? Math.min(100, Math.round((baselineRecovery / revenueAtRisk) * 100)) : 0;
  const agentPct = revenueAtRisk > 0 ? Math.min(100, Math.round((agentRecovery / revenueAtRisk) * 100)) : 0;
  const incrementalPct = revenueAtRisk > 0 ? Math.min(100, Math.round((incrementalRecovery / revenueAtRisk) * 100)) : 0;

  return (
    <div className="bg-gray-900/90 border border-gray-800/90 rounded-2xl p-6 shadow-xl space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-800/80 pb-4">
        <div>
          <div className="flex items-center space-x-2">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
            <h2 className="text-base font-extrabold text-white tracking-tight">Revenue Recovery Overview</h2>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            Real-time reconciliation of capital at risk against organic recovery and autonomous AI lift
          </p>
        </div>
        <div className="flex items-center space-x-2 text-xs font-mono bg-gray-950 px-3 py-1.5 rounded-xl border border-gray-800">
          <span className="text-gray-400">Formula Invariant:</span>
          <span className="text-emerald-400 font-bold">Incremental = Agent − Baseline</span>
        </div>
      </div>

      {/* Visual 4-Column Waterfall Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* 1. Revenue at Risk */}
        <div className="bg-gray-950/70 border border-amber-500/30 rounded-xl p-4.5 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-amber-400 flex items-center space-x-1.5">
              <AlertOctagon className="w-3.5 h-3.5 text-amber-400" />
              <span>Revenue at Risk</span>
            </span>
            <span className="text-[10px] bg-amber-500/15 text-amber-300 font-mono px-2 py-0.5 rounded-md">Pool</span>
          </div>
          <div className="text-2xl font-black text-amber-300">{formatCurrency(revenueAtRisk)}</div>
          <p className="text-[11px] text-gray-400">
            {summary.active_cases_count} active recoverable payment declines
          </p>
        </div>

        {/* 2. Baseline Organic Recovery */}
        <div className="bg-gray-950/70 border border-gray-700/60 rounded-xl p-4.5 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-gray-300 flex items-center space-x-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-gray-400" />
              <span>Baseline Organic</span>
            </span>
            <span className="text-[10px] bg-gray-800 text-gray-300 font-mono px-2 py-0.5 rounded-md">{baselinePct}%</span>
          </div>
          <div className="text-2xl font-black text-gray-200">{formatCurrency(baselineRecovery)}</div>
          <p className="text-[11px] text-gray-400">
            Estimated organic win-backs without AI intervention
          </p>
        </div>

        {/* 3. Agent Recovered Revenue */}
        <div className="bg-gray-950/70 border border-blue-500/30 rounded-xl p-4.5 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-blue-400 flex items-center space-x-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-blue-400" />
              <span>Agent Recovered</span>
            </span>
            <span className="text-[10px] bg-blue-500/15 text-blue-300 font-mono px-2 py-0.5 rounded-md">{agentPct}%</span>
          </div>
          <div className="text-2xl font-black text-blue-400">{formatCurrency(agentRecovery)}</div>
          <p className="text-[11px] text-gray-400">
            Total persisted captured recoveries via RecoverAI
          </p>
        </div>

        {/* 4. Net Incremental Lift */}
        <div className="bg-gradient-to-br from-emerald-950/50 to-gray-950 border border-emerald-500/40 rounded-xl p-4.5 space-y-2 glow-emerald">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-400 flex items-center space-x-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
              <span>Incremental Lift</span>
            </span>
            <span className="text-[10px] bg-emerald-500/20 text-emerald-300 font-mono px-2 py-0.5 rounded-md font-bold">
              +{incrementalPct}% Net
            </span>
          </div>
          <div className="text-2xl font-black text-emerald-400">{formatCurrency(incrementalRecovery)}</div>
          <p className="text-[11px] text-emerald-300/80">
            Pure incremental money won back by the agent
          </p>
        </div>
      </div>

      {/* Visual Recovery Progress Bar */}
      <div className="space-y-2 pt-1">
        <div className="flex items-center justify-between text-xs text-gray-400">
          <span className="font-semibold text-gray-300">Recovery Value Distribution</span>
          <div className="flex items-center space-x-4">
            <span className="flex items-center space-x-1.5 text-[11px]">
              <span className="w-2.5 h-2.5 rounded-sm bg-gray-600 inline-block" />
              <span>Baseline Organic: {formatCurrency(baselineRecovery)}</span>
            </span>
            <span className="flex items-center space-x-1.5 text-[11px]">
              <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500 inline-block" />
              <span className="text-emerald-400 font-semibold">Incremental AI Lift: {formatCurrency(incrementalRecovery)}</span>
            </span>
          </div>
        </div>

        <div className="h-3 w-full bg-gray-950 rounded-full overflow-hidden flex border border-gray-800">
          <div
            className="bg-gray-600 transition-all duration-500"
            style={{ width: `${baselinePct}%` }}
            title={`Baseline: ${formatCurrency(baselineRecovery)}`}
          />
          <div
            className="bg-emerald-500 transition-all duration-500"
            style={{ width: `${incrementalPct}%` }}
            title={`Incremental: ${formatCurrency(incrementalRecovery)}`}
          />
          <div
            className="bg-gray-800/40 flex-1"
            title={`Unrecovered: ${formatCurrency(Math.max(0, revenueAtRisk - agentRecovery))}`}
          />
        </div>
      </div>
    </div>
  );
};
