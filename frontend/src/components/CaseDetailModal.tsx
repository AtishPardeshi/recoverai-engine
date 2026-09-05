import React, { useState, useEffect } from "react";
import {
  X,
  Shield,
  Zap,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  User,
  CreditCard,
  History,
  Lock,
} from "lucide-react";
import type {
  RecoveryCase,
  AIRecommendation,
  RecoveryExecuteResponse,
  AuditEvent,
  RecoveryActionType,
} from "../types";
import { api } from "../services/api";

interface CaseDetailModalProps {
  recoveryCase: RecoveryCase | null;
  onClose: () => void;
  onExecutionComplete: () => void;
}

type ExecutionStage =
  | "IDLE"
  | "ANALYZING"
  | "AI_RECOMMENDATION"
  | "POLICY_VALIDATION"
  | "ACTION_APPROVED"
  | "EXECUTION"
  | "SIMULATOR_RESULT"
  | "OUTCOME_RECORDED";

export const CaseDetailModal: React.FC<CaseDetailModalProps> = ({
  recoveryCase,
  onClose,
  onExecutionComplete,
}) => {
  if (!recoveryCase) return null;

  const tx = recoveryCase.transaction;
  const cust = tx?.customer;
  const failure = tx?.payment_failure;

  const [recommendation, setRecommendation] = useState<AIRecommendation | null>(null);
  const [auditTrail, setAuditTrail] = useState<AuditEvent[]>([]);
  const [selectedAction, setSelectedAction] = useState<RecoveryActionType | null>(null);
  const [stage, setStage] = useState<ExecutionStage>("IDLE");
  const [executionResult, setExecutionResult] = useState<RecoveryExecuteResponse | null>(null);
  const [isLoadingRec, setIsLoadingRec] = useState<boolean>(true);

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(val);
  };

  useEffect(() => {
    let isMounted = true;
    const loadData = async () => {
      setIsLoadingRec(true);
      try {
        const [rec, audits] = await Promise.all([
          api.getAIRecommendation(recoveryCase.id),
          api.getCaseAuditTrail(recoveryCase.id),
        ]);
        if (isMounted) {
          setRecommendation(rec);
          setSelectedAction(rec.recommended_action);
          setAuditTrail(audits);
        }
      } catch (err: any) {
        console.error("Failed to load case data:", err);
      } finally {
        if (isMounted) setIsLoadingRec(false);
      }
    };

    loadData();
    return () => {
      isMounted = false;
    };
  }, [recoveryCase.id]);

  const handleExecute = async () => {
    try {
      // 1. ANALYZING
      setStage("ANALYZING");
      await new Promise((r) => setTimeout(r, 400));

      // 2. AI RECOMMENDATION
      setStage("AI_RECOMMENDATION");
      await new Promise((r) => setTimeout(r, 450));

      // 3. POLICY VALIDATION
      setStage("POLICY_VALIDATION");
      await new Promise((r) => setTimeout(r, 400));

      // Execute on backend
      const res = await api.executeRecovery(recoveryCase.id, selectedAction || undefined);
      setExecutionResult(res);

      if (res.guardrail_status === "REJECTED") {
        setStage("OUTCOME_RECORDED");
        const updatedAudits = await api.getCaseAuditTrail(recoveryCase.id);
        setAuditTrail(updatedAudits);
        onExecutionComplete();
        return;
      }

      // 4. ACTION APPROVED
      setStage("ACTION_APPROVED");
      await new Promise((r) => setTimeout(r, 400));

      // 5. EXECUTION
      setStage("EXECUTION");
      await new Promise((r) => setTimeout(r, 500));

      // 6. SIMULATOR RESULT
      setStage("SIMULATOR_RESULT");
      await new Promise((r) => setTimeout(r, 450));

      // 7. OUTCOME RECORDED & AUDIT LOGGED
      setStage("OUTCOME_RECORDED");
      const updatedAudits = await api.getCaseAuditTrail(recoveryCase.id);
      setAuditTrail(updatedAudits);
      onExecutionComplete();
    } catch (err: any) {
      console.error("Execution error:", err);
      setStage("IDLE");
    }
  };

  const isTerminal =
    recoveryCase.status === "RECOVERED" ||
    recoveryCase.status === "STOPPED" ||
    recoveryCase.status === "RECOVERY_EXHAUSTED";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
      <div className="relative w-full max-w-4xl bg-gray-900 border border-gray-800 rounded-2xl shadow-2xl overflow-hidden my-8">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 bg-gray-950/60">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
              <Zap className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-base font-black text-white">{tx?.external_id || "TX-UNKNOWN"}</h2>
                <span
                  className={`text-[10px] font-extrabold uppercase px-2.5 py-0.5 rounded-full border ${
                    recoveryCase.status === "RECOVERED"
                      ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                      : recoveryCase.status === "RECOVERY_ELIGIBLE"
                      ? "bg-blue-500/20 text-blue-300 border-blue-500/40"
                      : recoveryCase.status === "STOPPED"
                      ? "bg-red-500/20 text-red-300 border-red-500/40"
                      : "bg-gray-700/50 text-gray-300 border-gray-600"
                  }`}
                >
                  {recoveryCase.status}
                </span>
                {tx?.external_id === "TX-DEMO-001" && (
                  <span className="text-[10px] font-black uppercase bg-purple-500/20 text-purple-300 border border-purple-500/40 px-2 py-0.5 rounded-full">
                    ★ Primary Demo Case
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400">Created: {new Date(recoveryCase.created_at).toLocaleString()}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-6 max-h-[75vh] overflow-y-auto">
          {/* Top Grid: Transaction & Customer Profile */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Transaction & Failure Card */}
            <div className="bg-gray-950/50 border border-gray-800/80 rounded-xl p-4 space-y-3">
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center space-x-1.5">
                <CreditCard className="w-4 h-4 text-blue-400" />
                <span>Transaction & Failure Context</span>
              </div>
              <div className="flex justify-between items-baseline">
                <span className="text-2xl font-black text-white">{formatCurrency(recoveryCase.revenue_at_risk)}</span>
                <span className="text-xs font-semibold bg-gray-800 text-gray-300 px-2 py-0.5 rounded">
                  {tx?.payment_method}
                </span>
              </div>
              <div className="text-xs space-y-1 bg-red-950/20 border border-red-900/30 rounded-lg p-2.5">
                <div className="text-red-400 font-bold flex items-center space-x-1">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <span>Failure: {failure?.normalized_failure_type || "DECLINE"}</span>
                </div>
                <div className="text-gray-400 text-[11px]">{failure?.error_description || "Declined by gateway"}</div>
              </div>
            </div>

            {/* Customer Reliability Profile */}
            <div className="bg-gray-950/50 border border-gray-800/80 rounded-xl p-4 space-y-3">
              <div className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center space-x-1.5">
                <User className="w-4 h-4 text-emerald-400" />
                <span>Customer Profile & Health</span>
              </div>
              <div>
                <div className="text-sm font-bold text-gray-200">{cust?.name || "Customer"}</div>
                <div className="text-xs text-gray-400">ID: {cust?.external_id}</div>
              </div>
              <div className="grid grid-cols-3 gap-2 pt-1">
                <div className="bg-gray-900/80 rounded-lg p-2 text-center border border-gray-800">
                  <div className="text-[10px] text-gray-400">Success Rate</div>
                  <div className="text-xs font-extrabold text-emerald-400">
                    {((cust?.historical_success_rate || 0) * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="bg-gray-900/80 rounded-lg p-2 text-center border border-gray-800">
                  <div className="text-[10px] text-gray-400">Past Paid</div>
                  <div className="text-xs font-extrabold text-blue-400">{cust?.successful_payment_count || 0}</div>
                </div>
                <div className="bg-gray-900/80 rounded-lg p-2 text-center border border-gray-800">
                  <div className="text-[10px] text-gray-400">Past Fails</div>
                  <div className="text-xs font-extrabold text-amber-400">{cust?.failed_payment_count || 0}</div>
                </div>
              </div>
            </div>
          </div>

          {/* ML Recovery Intelligence & Rationale Banner */}
          <div className="bg-gradient-to-br from-emerald-950/40 via-gray-900 to-gray-950 border border-emerald-500/30 rounded-xl p-4 shadow-lg">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-extrabold uppercase tracking-wider text-emerald-400 flex items-center space-x-1.5">
                <TrendingUp className="w-4 h-4" />
                <span>ML Recovery Intelligence & Agent Recommendation</span>
              </div>
              <span className="text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded-full">
                HistGradientBoostingClassifier
              </span>
            </div>

            {isLoadingRec ? (
              <div className="py-6 text-center text-xs text-gray-400 animate-pulse">
                Evaluating ML feature weights & root-cause taxonomy...
              </div>
            ) : recommendation ? (
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="bg-gray-900/80 border border-gray-800 rounded-lg p-3">
                    <span className="text-[10px] uppercase font-bold text-gray-400">Recovery Probability</span>
                    <div className="text-xl font-black text-emerald-400">
                      {(recoveryCase.recovery_probability * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="bg-gray-900/80 border border-gray-800 rounded-lg p-3">
                    <span className="text-[10px] uppercase font-bold text-gray-400">Expected Recovery</span>
                    <div className="text-xl font-black text-white">
                      {formatCurrency(recoveryCase.expected_recovery)}
                    </div>
                  </div>
                  <div className="bg-gray-900/80 border border-gray-800 rounded-lg p-3">
                    <span className="text-[10px] uppercase font-bold text-gray-400">Priority Score</span>
                    <div className="text-xl font-black text-purple-400">
                      {recoveryCase.priority_score.toFixed(0)}
                    </div>
                  </div>
                </div>

                <div className="bg-gray-950/70 border border-emerald-500/20 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold text-emerald-300">
                      Recommended Action: {recommendation.recommended_action}
                    </span>
                    <span className="text-[10px] text-gray-400">
                      Confidence: {(recommendation.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="text-xs text-gray-300 leading-relaxed">{recommendation.reason}</p>
                </div>
              </div>
            ) : null}
          </div>

          {/* Live 7-Stage Execution Stepper */}
          {stage !== "IDLE" && (
            <div className="bg-gray-950 border border-gray-800 rounded-xl p-4 space-y-3">
              <div className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center space-x-2">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                <span>Autonomous Execution Pipeline</span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {[
                  { key: "ANALYZING", label: "1. Analyzing Risk" },
                  { key: "AI_RECOMMENDATION", label: "2. AI Strategy" },
                  { key: "POLICY_VALIDATION", label: "3. Policy Guardrail" },
                  { key: "ACTION_APPROVED", label: "4. Approved" },
                  { key: "EXECUTION", label: "5. Execution" },
                  { key: "SIMULATOR_RESULT", label: "6. Gateway Sim" },
                  { key: "OUTCOME_RECORDED", label: "7. Money Captured" },
                ].map((s) => {
                  const stageOrder = [
                    "ANALYZING",
                    "AI_RECOMMENDATION",
                    "POLICY_VALIDATION",
                    "ACTION_APPROVED",
                    "EXECUTION",
                    "SIMULATOR_RESULT",
                    "OUTCOME_RECORDED",
                  ];
                  const currentIdx = stageOrder.indexOf(stage);
                  const stepIdx = stageOrder.indexOf(s.key);
                  const isDone = currentIdx >= stepIdx;
                  const isCurrent = currentIdx === stepIdx;

                  return (
                    <div
                      key={s.key}
                      className={`text-[11px] font-semibold p-2 rounded-lg border flex items-center space-x-1.5 transition-all ${
                        isDone
                          ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-300"
                          : isCurrent
                          ? "bg-blue-500/20 border-blue-500/40 text-blue-300 animate-pulse"
                          : "bg-gray-900/40 border-gray-800 text-gray-500"
                      }`}
                    >
                      {isDone ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Clock className="w-3.5 h-3.5" />
                      )}
                      <span>{s.label}</span>
                    </div>
                  );
                })}
              </div>

              {/* Execution Result Banner */}
              {executionResult && stage === "OUTCOME_RECORDED" && (
                <div
                  className={`mt-3 p-3.5 rounded-xl border text-xs leading-relaxed ${
                    executionResult.guardrail_status === "REJECTED"
                      ? "bg-amber-950/30 border-amber-500/40 text-amber-200"
                      : executionResult.outcome_result === "SUCCESS"
                      ? "bg-emerald-950/40 border-emerald-500/50 text-emerald-200 glow-emerald"
                      : "bg-red-950/30 border-red-500/40 text-red-200"
                  }`}
                >
                  <div className="flex items-center space-x-2 font-bold text-sm mb-1">
                    {executionResult.guardrail_status === "REJECTED" ? (
                      <>
                        <Shield className="w-4 h-4 text-amber-400" />
                        <span>GUARDRAIL REJECTED ACTION</span>
                      </>
                    ) : executionResult.outcome_result === "SUCCESS" ? (
                      <>
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        <span>RECOVERY SUCCESSFUL: {formatCurrency(executionResult.recovered_amount)} RECOVERED</span>
                      </>
                    ) : (
                      <>
                        <XCircle className="w-4 h-4 text-red-400" />
                        <span>ACTION EXECUTED: RECOVERY ATTEMPT DENIED</span>
                      </>
                    )}
                  </div>
                  <div>{executionResult.guardrail_reason}</div>
                  {executionResult.simulator_reference && (
                    <div className="text-[10px] text-gray-400 mt-1">
                      Gateway Reference: {executionResult.simulator_reference} • Correlation: {executionResult.correlation_id}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Audit History Log */}
          <div className="space-y-2">
            <div className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center space-x-1.5">
              <History className="w-4 h-4 text-gray-400" />
              <span>Immutable Case Audit Trail</span>
            </div>
            <div className="bg-gray-950/70 border border-gray-800 rounded-xl divide-y divide-gray-800/80 max-h-48 overflow-y-auto">
              {auditTrail.length === 0 ? (
                <div className="p-4 text-center text-xs text-gray-500">No audit events recorded yet</div>
              ) : (
                auditTrail.map((ev) => (
                  <div key={ev.id} className="p-3 text-xs flex items-start justify-between">
                    <div>
                      <div className="font-bold text-gray-300 flex items-center space-x-1.5">
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-800 text-gray-300">
                          {ev.actor_type}
                        </span>
                        <span>{ev.event_type}</span>
                      </div>
                      <div className="text-gray-400 text-[11px] mt-0.5">
                        {JSON.stringify(ev.payload)}
                      </div>
                    </div>
                    <div className="text-[10px] text-gray-500 font-mono whitespace-nowrap ml-4">
                      {new Date(ev.created_at).toLocaleTimeString()}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-800 bg-gray-950/80">
          <div className="text-xs text-gray-400">
            {isTerminal ? (
              <span className="text-gray-400 flex items-center space-x-1">
                <Lock className="w-3.5 h-3.5" />
                <span>Case in terminal state ({recoveryCase.status}). Guardrail protects against re-charging.</span>
              </span>
            ) : (
              <span>Ready for autonomous execution. Guardrails active.</span>
            )}
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-gray-400 hover:text-white bg-gray-800/80 hover:bg-gray-700 rounded-xl transition-all"
            >
              Close
            </button>
            <button
              onClick={handleExecute}
              disabled={isTerminal || stage !== "IDLE"}
              className="flex items-center space-x-2 px-5 py-2 text-xs font-bold text-white bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 rounded-xl shadow-lg shadow-emerald-900/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed glow-emerald"
            >
              <Zap className="w-4 h-4 text-white" />
              <span>{stage !== "IDLE" ? "Executing Recovery..." : "EXECUTE RECOVERY"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
