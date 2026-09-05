import type {
  DashboardSummary,
  RecoveryCase,
  AIRecommendation,
  RecoveryExecuteResponse,
  AuditEvent,
  ActivityFeedItem,
  AnalyticsData,
  RecoveryActionType,
  BatchRunSummary,
} from "../types";

const API_BASE = "http://localhost:8000/api";

export const api = {
  async getDashboardSummary(batchId?: string, scope?: string): Promise<DashboardSummary> {
    const params = new URLSearchParams();
    if (batchId) params.append("batch_id", batchId);
    if (scope) params.append("scope", scope);
    const query = params.toString() ? `?${params.toString()}` : "";
    const res = await fetch(`${API_BASE}/dashboard/summary${query}`);
    if (!res.ok) throw new Error("Failed to fetch dashboard summary");
    return res.json();
  },

  async getRecoveryCases(params?: {
    status?: string;
    payment_method?: string;
    failure_type?: string;
    search?: string;
    page?: number;
    page_size?: number;
  }): Promise<RecoveryCase[]> {
    const query = new URLSearchParams();
    if (params?.status) query.append("status", params.status);
    if (params?.payment_method) query.append("payment_method", params.payment_method);
    if (params?.failure_type) query.append("failure_type", params.failure_type);
    if (params?.search) query.append("search", params.search);
    if (params?.page) query.append("page", params.page.toString());
    if (params?.page_size) query.append("page_size", params.page_size.toString());

    const res = await fetch(`${API_BASE}/recovery-cases?${query.toString()}`);
    if (!res.ok) throw new Error("Failed to fetch recovery cases");
    return res.json();
  },

  async getRecoveryCase(id: string): Promise<RecoveryCase> {
    const res = await fetch(`${API_BASE}/recovery-cases/${id}`);
    if (!res.ok) throw new Error("Failed to fetch recovery case detail");
    return res.json();
  },

  async getAIRecommendation(caseId: string): Promise<AIRecommendation> {
    const res = await fetch(`${API_BASE}/recovery-cases/${caseId}/recommend`, {
      method: "POST",
    });
    if (!res.ok) throw new Error("Failed to generate AI recommendation");
    return res.json();
  },

  async executeRecovery(
    caseId: string,
    actionType?: RecoveryActionType,
    overrideReason?: string
  ): Promise<RecoveryExecuteResponse> {
    const res = await fetch(`${API_BASE}/recovery-cases/${caseId}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action_type: actionType,
        override_reason: overrideReason,
      }),
    });
    if (!res.ok) throw new Error("Failed to execute recovery action");
    return res.json();
  },

  async getCaseAuditTrail(caseId: string): Promise<AuditEvent[]> {
    const res = await fetch(`${API_BASE}/recovery-cases/${caseId}/audit`);
    if (!res.ok) throw new Error("Failed to fetch audit trail");
    return res.json();
  },

  async getAnalytics(batchId?: string, scope?: string): Promise<AnalyticsData> {
    const params = new URLSearchParams();
    if (batchId) params.append("batch_id", batchId);
    if (scope) params.append("scope", scope);
    const query = params.toString() ? `?${params.toString()}` : "";
    const res = await fetch(`${API_BASE}/analytics/recovery${query}`);
    if (!res.ok) throw new Error("Failed to fetch analytics");
    return res.json();
  },

  async getActivityFeed(limit: number = 30): Promise<ActivityFeedItem[]> {
    const res = await fetch(`${API_BASE}/activity?limit=${limit}`);
    if (!res.ok) throw new Error("Failed to fetch activity feed");
    return res.json();
  },

  async resetSimulator(): Promise<void> {
    const res = await fetch(`${API_BASE}/simulator/reset`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to reset simulator");
  },

  async seedSimulator(cases: number = 1000): Promise<void> {
    const res = await fetch(`${API_BASE}/simulator/seed?n_cases=${cases}`, {
      method: "POST",
    });
    if (!res.ok) throw new Error("Failed to seed simulator data");
  },

  async toggleSystemicIncident(active: boolean): Promise<void> {
    const res = await fetch(`${API_BASE}/simulator/incident`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider_or_bank: "HDFC_BANK",
        failure_type: "TEMPORARY_BANK_DECLINE",
        active,
        spike_rate: 0.45,
      }),
    });
    if (!res.ok) throw new Error("Failed to toggle incident");
  },

  async runBatchRecovery(params?: { limit?: number; seed?: number; dry_run?: boolean }): Promise<BatchRunSummary> {
    const res = await fetch(`${API_BASE}/recovery/batch-run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        limit: params?.limit ?? 500,
        seed: params?.seed ?? 42,
        dry_run: params?.dry_run ?? false,
      }),
    });
    if (!res.ok) throw new Error("Failed to run batch recovery");
    return res.json();
  },

  async getBatchHistory(): Promise<BatchRunSummary[]> {
    const res = await fetch(`${API_BASE}/recovery/batch-history`);
    if (!res.ok) throw new Error("Failed to fetch batch history");
    return res.json();
  },
};

