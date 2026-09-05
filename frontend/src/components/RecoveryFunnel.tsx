import React from "react";
import type { DashboardSummary } from "../types";
import { ArrowRight, Layers, ShieldCheck, Zap, CheckCircle2, AlertOctagon } from "lucide-react";

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
      step: "01",
      title: "Revenue at Risk",
      amount: summary.revenue_at_risk || summary.failed_payment_value,
      subtitle: "Gross recoverable failure pool",
      icon: AlertOctagon,
      color: "from-amber-500/15 to-amber-500/5",
      border: "border-amber-500/30",
      textColor: "text-amber-400",
      iconColor: "text-amber-400",
    },
    {
      step: "02",
      title: "AI Analysis",
      amount: summary.recovery_eligible_value,
      subtitle: "ML scored & root-cause triaged",
      icon: Layers,
      color: "from-blue-500/15 to-blue-500/5",
      border: "border-blue-500/30",
      textColor: "text-blue-400",
      iconColor: "text-blue-400",
    },
    {
      step: "03",
      title: "Policy Approved",
      amount: summary.intervention_value,
      subtitle: "Guardrail & cooldown cleared",
      icon: ShieldCheck,
      color: "from-teal-500/15 to-teal-500/5",
      border: "border-teal-500/30",
      textColor: "text-teal-400",
      iconColor: "text-teal-400",
    },
    {
      step: "04",
      title: "Action Executed",
      amount: summary.intervention_value,
      subtitle: "Idempotent payment link / retry",
      icon: Zap,
      color: "from-purple-500/15 to-purple-500/5",
      border: "border-purple-500/30",
      textColor: "text-purple-400",
      iconColor: "text-purple-400",
    },
    {
      step: "05",
      title: "Recovered",
      amount: summary.recovered_revenue,
      subtitle: "Persisted captured revenue in DB",
      icon: CheckCircle2,
      color: "from-emerald-500/25 to-emerald-500/5",
      border: "border-emerald-500/40",
      textColor: "text-emerald-400 font-black",
      iconColor: "text-emerald-400",
    },
  ];

  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-2xl p-6 shadow-xl space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-800/80 pb-3">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-white flex items-center space-x-2">
            <Zap className="w-4 h-4 text-emerald-400" />
            <span>Autonomous Recovery Pipeline</span>
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Step-by-step conversion from payment decline through AI triage, policy guardrails, execution to captured money
          </p>
        </div>
        <span className="text-xs font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1 rounded-full self-start sm:self-auto">
          {(summary.recovery_rate * 100).toFixed(1)}% Conversion
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-center pt-1">
        {stages.map((stage, idx) => {
          const Icon = stage.icon;
          return (
            <div key={idx} className="relative">
              <div
                className={`bg-gradient-to-b ${stage.color} border ${stage.border} rounded-xl p-4 transition-all hover:border-gray-600 space-y-2`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono text-gray-400 uppercase font-bold">Stage {stage.step}</span>
                  <Icon className={`w-4 h-4 ${stage.iconColor}`} />
                </div>
                <div className="text-[11px] font-bold text-gray-300 uppercase tracking-wider">
                  {stage.title}
                </div>
                <div className={`text-lg lg:text-xl font-black ${stage.textColor} tracking-tight`}>
                  {formatCurrency(stage.amount)}
                </div>
                <div className="text-[10px] text-gray-400 leading-tight">
                  {stage.subtitle}
                </div>
              </div>
              {idx < stages.length - 1 && (
                <div className="hidden md:block absolute -right-3.5 top-1/2 -translate-y-1/2 z-10 text-gray-600">
                  <ArrowRight className="w-4 h-4" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
