import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { AlertCircle, Zap } from "lucide-react";
import type { AnalyticsData } from "../types";

interface RootCauseAndStrategyProps {
  analytics: AnalyticsData | null;
}

export const RootCauseAndStrategySection: React.FC<RootCauseAndStrategyProps> = ({ analytics }) => {
  if (!analytics) return null;

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  const failureData = analytics.recovery_by_failure_type || [];
  const actionData = analytics.recovery_by_action || [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* SECTION 4: ROOT CAUSE INTELLIGENCE */}
      <div className="bg-gray-900/90 border border-gray-800/90 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-gray-800/80 pb-3">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Root Cause Intelligence
            </h3>
          </div>
          <span className="text-xs text-gray-400">Failure Taxonomy</span>
        </div>

        <p className="text-xs text-gray-400">
          Distribution of failed payment volume and recovery success rates across underlying failure reasons.
        </p>

        {/* Chart */}
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={failureData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
              <XAxis
                dataKey="category"
                tick={{ fill: "#9CA3AF", fontSize: 9 }}
                interval={0}
                angle={-15}
                textAnchor="end"
                height={45}
              />
              <YAxis tick={{ fill: "#9CA3AF", fontSize: 10 }} />
              <Tooltip
                contentStyle={{ backgroundColor: "#111827", borderColor: "#374151", color: "#FFF" }}
                formatter={(val: any, name: any) => [
                  name === "Recovered Revenue" ? formatCurrency(Number(val)) : val,
                  name,
                ]}
              />
              <Bar dataKey="candidates_count" fill="#3B82F6" name="Total Candidates" radius={[4, 4, 0, 0]} />
              <Bar dataKey="successful_count" fill="#10B981" name="Recovered" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Key Failure Breakdown Badges */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-2">
          {failureData.slice(0, 6).map((item, idx) => {
            const total = item.candidates_count || 0;
            const success = item.successful_count || 0;
            const winRate = total > 0 ? ((success / total) * 100).toFixed(0) : "0";
            return (
              <div key={idx} className="bg-gray-950/70 border border-gray-800 rounded-lg p-2.5 space-y-1">
                <div className="text-[10px] font-bold text-gray-300 truncate" title={item.category}>
                  {item.category.replace(/_/g, " ")}
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-emerald-400 font-bold">{winRate}% win</span>
                  <span className="text-gray-400">{success}/{total}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* SECTION 5: RECOVERY STRATEGY PERFORMANCE */}
      <div className="bg-gray-900/90 border border-gray-800/90 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-gray-800/80 pb-3">
          <div className="flex items-center space-x-2">
            <Zap className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Recovery Strategy Performance
            </h3>
          </div>
          <span className="text-xs text-gray-400">Autonomous Interventions</span>
        </div>

        <p className="text-xs text-gray-400">
          Conversion rates and recovered revenue achieved across policy-approved recovery action strategies.
        </p>

        {/* Chart */}
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={actionData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" />
              <XAxis
                dataKey="category"
                tick={{ fill: "#9CA3AF", fontSize: 9 }}
                interval={0}
                angle={-18}
                textAnchor="end"
                height={45}
              />
              <YAxis tick={{ fill: "#9CA3AF", fontSize: 10 }} />
              <Tooltip
                contentStyle={{ backgroundColor: "#111827", borderColor: "#374151", color: "#FFF" }}
                formatter={(val: any, name: any) => [
                  name === "Recovered Revenue" ? formatCurrency(Number(val)) : val,
                  name,
                ]}
              />
              <Bar dataKey="attempted_count" fill="#6366F1" name="Actions Executed" radius={[4, 4, 0, 0]} />
              <Bar dataKey="successful_count" fill="#8B5CF6" name="Successful Win-backs" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Strategy Breakdown Badges */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-2">
          {actionData.slice(0, 6).map((item, idx) => {
            const attempted = item.attempted_count || 0;
            const success = item.successful_count || 0;
            const successRate = attempted > 0 ? ((success / attempted) * 100).toFixed(0) : "0";
            return (
              <div key={idx} className="bg-gray-950/70 border border-gray-800 rounded-lg p-2.5 space-y-1">
                <div className="text-[10px] font-bold text-gray-300 truncate" title={item.category}>
                  {item.category.replace(/_/g, " ")}
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-purple-400 font-bold">{successRate}% succ</span>
                  <span className="text-gray-400">{success}/{attempted}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
