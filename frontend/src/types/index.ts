export type PaymentMethod = "CARD" | "UPI" | "NETBANKING" | "WALLET" | "EMANDATE";

export type TransactionStatus =
  | "CREATED"
  | "AUTHORIZED"
  | "CAPTURED"
  | "FAILED"
  | "RECOVERY_ELIGIBLE"
  | "RECOVERY_IN_PROGRESS"
  | "RECOVERED"
  | "RECOVERY_EXHAUSTED"
  | "ESCALATED"
  | "STOPPED";

export type FailureType =
  | "TEMPORARY_BANK_DECLINE"
  | "INSUFFICIENT_FUNDS"
  | "BANK_DECLINE"
  | "NETWORK_ERROR"
  | "EXPIRED_METHOD"
  | "INVALID_DETAILS";

export type RecoveryActionType =
  | "RETRY_PAYMENT"
  | "DELAYED_RETRY"
  | "SEND_PAYMENT_LINK"
  | "SUGGEST_ALTERNATIVE_PAYMENT_METHOD"
  | "SEND_REMINDER"
  | "ESCALATE_TO_HUMAN"
  | "STOP_RECOVERY";

export type GuardrailDecision = "APPROVED" | "REJECTED";
export type OutcomeResult = "SUCCESS" | "FAILURE" | "SKIPPED";

export interface Customer {
  id: string;
  external_id: string;
  name: string;
  historical_success_rate: number;
  total_transaction_value: number;
  successful_payment_count: number;
  failed_payment_count: number;
  is_opted_out: boolean;
  has_open_dispute: boolean;
  created_at: string;
}

export interface PaymentFailure {
  id: string;
  transaction_id: string;
  error_code: string;
  error_description?: string;
  error_source?: string;
  error_step?: string;
  error_reason?: string;
  normalized_failure_type: FailureType;
  occurred_at: string;
}

export interface Transaction {
  id: string;
  external_id: string;
  customer_id: string;
  amount: number;
  currency: string;
  payment_method: PaymentMethod;
  status: TransactionStatus;
  created_at: string;
  updated_at: string;
  customer?: Customer;
  payment_failure?: PaymentFailure;
}

export interface RecoveryOutcome {
  id: string;
  recovery_action_id: string;
  result: OutcomeResult;
  recovered_amount: number;
  simulator_result: string;
  failure_reason?: string;
  metadata_payload?: Record<string, unknown>;
  occurred_at: string;
}

export interface RecoveryAction {
  id: string;
  recovery_case_id: string;
  idempotency_key: string;
  action_type: RecoveryActionType;
  recommendation_reason: string;
  confidence: number;
  expected_recovery: number;
  policy_version: string;
  guardrail_decision: GuardrailDecision;
  guardrail_reason?: string;
  status: string;
  created_at: string;
  executed_at?: string;
  outcome?: RecoveryOutcome;
}

export interface RecoveryCase {
  id: string;
  transaction_id: string;
  revenue_at_risk: number;
  recovery_probability: number;
  expected_recovery: number;
  priority_score: number;
  status: TransactionStatus;
  retry_count: number;
  message_count: number;
  created_at: string;
  updated_at: string;
  transaction?: Transaction;
  actions: RecoveryAction[];
}

export interface DashboardSummary {
  scope?: "CURRENT_BATCH" | "CUMULATIVE";
  batch_id?: string | null;
  total_payment_volume: number;
  failed_payment_value: number;
  revenue_at_risk: number;
  recovery_eligible_value: number;
  intervention_value: number;
  recovered_revenue: number;
  baseline_recovered_revenue: number;
  incremental_recovered_revenue: number;
  recovery_rate: number;
  active_cases_count: number;
  total_cases_count: number;
  successful_recoveries_count: number;
  guardrail_rejections_count: number;
  systemic_incidents_active: number;
  cumulative_total_payment_volume?: number;
  cumulative_failed_payment_value?: number;
  cumulative_recovered_revenue?: number;
  cumulative_baseline_recovered_revenue?: number;
  cumulative_incremental_recovered_revenue?: number;
  cumulative_successful_recoveries_count?: number;
  cumulative_total_cases_count?: number;
}

export interface AIRecommendation {
  recommended_action: RecoveryActionType;
  root_cause: string;
  reason: string;
  confidence: number;
  expected_recovery: number;
  risk_flags: string[];
  requires_human_review: boolean;
}

export interface RecoveryExecuteResponse {
  execution_id: string;
  recovery_case_id: string;
  transaction_id: string;
  action_type: RecoveryActionType;
  guardrail_status: GuardrailDecision;
  guardrail_reason: string;
  execution_status: string;
  outcome_result?: OutcomeResult;
  recovered_amount: number;
  simulator_reference?: string;
  new_case_status: TransactionStatus;
  correlation_id: string;
  audit_event_id?: string;
  executed_at: string;
}

export interface AuditEvent {
  id: string;
  correlation_id: string;
  entity_type: string;
  entity_id: string;
  event_type: string;
  actor_type: string;
  payload: Record<string, unknown>;
  policy_version?: string;
  agent_version?: string;
  created_at: string;
}

export interface ActivityFeedItem {
  id: string;
  event_type: string;
  title: string;
  description: string;
  amount?: number;
  status: "SUCCESS" | "FAILURE" | "WARNING" | "INFO";
  timestamp: string;
  correlation_id: string;
}

export interface DimensionRecovery {
  category: string;
  candidates_count?: number;
  attempted_count: number;
  successful_count: number;
  recovery_rate: number;
  recovered_amount: number;
  baseline_recovered?: number;
  incremental_recovered?: number;
  success_rate?: number;
  recommended_count?: number;
  approved_count?: number;
  rejected_count?: number;
  scope?: "CURRENT_BATCH" | "CUMULATIVE";
  batch_id?: string | null;
}

export interface PredictedVsActual {
  probability_bucket: string;
  total_cases: number;
  predicted_expected_revenue: number;
  actual_recovered_revenue: number;
  calibration_accuracy: number;
  average_predicted_probability?: number;
  actual_recovery_rate?: number;
}

export interface AnalyticsData {
  scope?: "CURRENT_BATCH" | "CUMULATIVE";
  batch_id?: string | null;
  generated_at?: string;
  recovery_by_failure_type: DimensionRecovery[];
  recovery_by_action: DimensionRecovery[];
  recovery_by_payment_method: DimensionRecovery[];
  predicted_vs_actual: PredictedVsActual[];
  total_interventions: number;
  total_recovered_amount: number;
  baseline_recovered_amount: number;
  incremental_recovered_amount: number;
}

export interface BatchRunSummary {
  batch_id: string;
  started_at: string;
  completed_at: string;
  seed: number;
  dry_run: boolean;
  total_candidates: number;
  ml_evaluated: number;
  ai_recommended: number;
  policy_approved: number;
  policy_rejected: number;
  actions_executed: number;
  successful_recoveries: number;
  failed_recoveries: number;
  escalated: number;
  stopped: number;
  skipped: number;
  baseline_recovered_revenue: number;
  agent_recovered_revenue: number;
  incremental_recovered_revenue: number;
  recovery_rate: number;
  incremental_lift: number;
  policy_block_rate: number;
  execution_success_rate: number;
  currency: string;
}

