import React from "react";
import type { DashboardSummary } from "../types";
import { ArrowRight, DollarSign } from "lucide-react";

interface RecoveryFunnelProps {
  summary: DashboardSummary | null;
}

export const RecoveryFunnel: React.FC<RecoveryFunnelProps> = ({ summary }) => {
  if (!summary) return null;

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  const stages = [
    {
      title: "1. Failed Payment Value",
      amount: summary.failed_payment_value,
      subtitle: "Gross payment decline volume",
      color: "from-red-500/20 to-red-500/5",
      border: "border-red-500/30",
      textColor: "text-red-400",
    },
    {
      title: "2. Revenue at Risk",
      amount: summary.revenue_at_risk,
      subtitle: "Active unrecovered failure pool",
      color: "from-amber-500/20 to-amber-500/5",
      border: "border-amber-500/30",
      textColor: "text-amber-400",
    },
    {
      title: "3. Recovery Eligible",
      amount: summary.recovery_eligible_value,
      subtitle: "Passed root-cause & policy triage",
      color: "from-blue-500/20 to-blue-500/5",
      border: "border-blue-500/30",
      textColor: "text-blue-400",
    },
    {
      title: "4. Intervention Value",
      amount: summary.intervention_value,
      subtitle: "Targeted by autonomous agent",
      color: "from-purple-500/20 to-purple-500/5",
      border: "border-purple-500/30",
      textColor: "text-purple-400",
    },
    {
      title: "5. Money Recovered",
      amount: summary.recovered_revenue,
      subtitle: "Verified payment capture in DB",
      color: "from-emerald-500/30 to-emerald-500/10",
      border: "border-emerald-500/50",
      textColor: "text-emerald-400 font-extrabold",
    },
  ];

  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-6 shadow-xl">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-gray-300 flex items-center space-x-2">
            <DollarSign className="w-4 h-4 text-emerald-400" />
            <span>Autonomous Recovery Funnel</span>
          </h2>
          <p className="text-xs text-gray-400">Step-by-step conversion of failed payment volume into recovered capital</p>
        </div>
        <span className="text-xs font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-full">
          {(summary.recovery_rate * 100).toFixed(1)}% Win-back Conversion
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-center">
        {stages.map((stage, idx) => (
          <div key={idx} className="relative">
            <div
              className={`bg-gradient-to-b ${stage.color} border ${stage.border} rounded-xl p-4 transition-all hover:scale-[1.02]`}
            >
              <div className="text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1">
                {stage.title}
              </div>
              <div className={`text-lg lg:text-xl font-black ${stage.textColor} tracking-tight`}>
                {formatCurrency(stage.amount)}
              </div>
              <div className="text-[10px] text-gray-400 mt-1 leading-tight">
                {stage.subtitle}
              </div>
            </div>
            {idx < stages.length - 1 && (
              <div className="hidden md:block absolute -right-3.5 top-1/2 -translate-y-1/2 z-10 text-gray-600">
                <ArrowRight className="w-4 h-4" />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
