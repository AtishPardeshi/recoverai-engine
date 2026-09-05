import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  Legend,
} from "recharts";
import type { AnalyticsData } from "../types";
import { TrendingUp, BarChart3, Activity, CreditCard, Layers, Database } from "lucide-react";

interface AnalyticsViewProps {
  analytics: AnalyticsData | null;
  activeScope?: "CURRENT_BATCH" | "CUMULATIVE";
  onScopeChange?: (scope: "CURRENT_BATCH" | "CUMULATIVE") => void;
}

export const AnalyticsView: React.FC<AnalyticsViewProps> = ({
  analytics,
  activeScope = "CURRENT_BATCH",
  onScopeChange,
}) => {
  if (!analytics) return null;

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  const isBatchScope = (analytics.scope || activeScope) === "CURRENT_BATCH";

  return (
    <div className="space-y-6">
      {/* Scope Selector Header */}
      <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-4 shadow-lg flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs uppercase font-extrabold text-white">Analytics Scope:</span>
              <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded-md ${
                isBatchScope
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : "bg-blue-500/20 text-blue-300 border border-blue-500/40"
              }`}>
                {isBatchScope ? `CURRENT BATCH (${analytics.batch_id || "LATEST"})` : "CUMULATIVE DATABASE"}
              </span>
            </div>
            <p className="text-[11px] text-gray-400 mt-0.5">
              {isBatchScope
                ? "Showing strictly candidate, action, and outcome records for the selected batch run."
                : "Showing aggregated metrics across all historical database recovery records."}
            </p>
          </div>
        </div>

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

      {/* Top Intelligence Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-5 shadow-lg">
          <div className="text-xs uppercase font-bold text-gray-400 mb-1">Actions Executed</div>
          <div className="text-3xl font-black text-white">{analytics.total_interventions}</div>
          <p className="text-xs text-gray-500 mt-2">Policy-approved interventions</p>
        </div>
        <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-5 shadow-lg">
          <div className="text-xs uppercase font-bold text-gray-400 mb-1">Baseline Organic Win-back</div>
          <div className="text-3xl font-black text-gray-300">{formatCurrency(analytics.baseline_recovered_amount)}</div>
          <p className="text-xs text-gray-500 mt-2">Without autonomous agent</p>
        </div>
        <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-5 shadow-lg">
          <div className="text-xs uppercase font-bold text-blue-400 mb-1">Actual Agent Recovered</div>
          <div className="text-3xl font-black text-blue-400">{formatCurrency(analytics.total_recovered_amount)}</div>
          <p className="text-xs text-gray-500 mt-2">Persisted captured outcomes</p>
        </div>
        <div className="bg-gradient-to-br from-emerald-950/60 to-gray-900 border border-emerald-500/40 rounded-2xl p-5 shadow-lg glow-emerald">
          <div className="text-xs uppercase font-bold text-emerald-400 mb-1">Incremental Lift</div>
          <div className="text-3xl font-black text-emerald-400">
            {formatCurrency(analytics.incremental_recovered_amount)}
          </div>
          <p className="text-xs text-emerald-300/80 mt-2">Agent Recovered Revenue − Baseline Recovery</p>
        </div>
      </div>

      {/* Chart Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 1. Recovery by Failure Taxonomy */}
        <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center space-x-2">
            <BarChart3 className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              {isBatchScope ? "Batch Failure Taxonomy" : "Cumulative Failure Taxonomy"}
            </h3>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={analytics.recovery_by_failure_type}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
                <XAxis dataKey="category" tick={{ fill: "#9CA3AF", fontSize: 9 }} interval={0} angle={-15} textAnchor="end" height={45} />
                <YAxis tick={{ fill: "#9CA3AF", fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#111827", borderColor: "#374151", color: "#FFF" }}
                  formatter={(val: any) => [val, "Count"]}
                />
                <Bar dataKey="successful_count" fill="#10B981" name="Recovered" radius={[4, 4, 0, 0]} />
                <Bar dataKey="candidates_count" fill="#3B82F6" name="Candidates" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 2. Recovery by Payment Method */}
        <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center space-x-2">
            <CreditCard className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              {isBatchScope ? "Batch Payment Methods" : "Cumulative Payment Methods"}
            </h3>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={analytics.recovery_by_payment_method}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
                <XAxis dataKey="category" tick={{ fill: "#9CA3AF", fontSize: 10 }} />
                <YAxis tick={{ fill: "#9CA3AF", fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#111827", borderColor: "#374151", color: "#FFF" }}
                  formatter={(val: any) => [val, "Count"]}
                />
                <Bar dataKey="successful_count" fill="#06B6D4" name="Recovered" radius={[4, 4, 0, 0]} />
                <Bar dataKey="candidates_count" fill="#6366F1" name="Candidates" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 3. Recovery by Action Strategy */}
        <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center space-x-2">
            <Activity className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              {isBatchScope ? "Batch Action Strategies" : "Cumulative Action Strategies"}
            </h3>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={analytics.recovery_by_action}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
                <XAxis dataKey="category" tick={{ fill: "#9CA3AF", fontSize: 9 }} interval={0} angle={-20} textAnchor="end" height={50} />
                <YAxis tick={{ fill: "#9CA3AF", fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#111827", borderColor: "#374151", color: "#FFF" }}
                  formatter={(val: any) => [val, "Count"]}
                />
                <Bar dataKey="successful_count" fill="#8B5CF6" name="Successful Win-backs" radius={[4, 4, 0, 0]} />
                <Bar dataKey="attempted_count" fill="#4B5563" name="Actions Executed" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 4. ML Model Calibration: Predicted vs Actual Revenue */}
        <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                Predicted vs Actual Win-back
              </h3>
            </div>
            <span className="text-xs text-gray-400">P(Recovery) Buckets</span>
          </div>

          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={analytics.predicted_vs_actual}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
                <XAxis dataKey="probability_bucket" tick={{ fill: "#9CA3AF", fontSize: 11 }} />
                <YAxis tick={{ fill: "#9CA3AF", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#111827", borderColor: "#374151", color: "#FFF" }}
                  formatter={(val: any) => [formatCurrency(Number(val)), "Revenue"]}
                />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="predicted_expected_revenue"
                  stroke="#3B82F6"
                  fill="rgba(59, 130, 246, 0.2)"
                  name="Predicted Expected"
                />
                <Area
                  type="monotone"
                  dataKey="actual_recovered_revenue"
                  stroke="#10B981"
                  fill="rgba(16, 185, 129, 0.2)"
                  name="Actual Recovered"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};
