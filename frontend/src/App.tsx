import React, { useState, useEffect, useCallback } from "react";
import { Navbar } from "./components/Navbar";
import { KPICards } from "./components/KPICards";
import { RecoveryFunnel } from "./components/RecoveryFunnel";
import { CaseQueue } from "./components/CaseQueue";
import { CaseDetailModal } from "./components/CaseDetailModal";
import { AnalyticsView } from "./components/AnalyticsView";
import { AuditTimeline } from "./components/AuditTimeline";
import type {
  DashboardSummary,
  RecoveryCase,
  AnalyticsData,
  ActivityFeedItem,
} from "./types";
import { api } from "./services/api";
import { Zap, Sparkles, ArrowRight, CheckCircle2 } from "lucide-react";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"dashboard" | "queue" | "analytics" | "audit">("dashboard");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [cases, setCases] = useState<RecoveryCase[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [activityFeed, setActivityFeed] = useState<ActivityFeedItem[]>([]);
  const [selectedCase, setSelectedCase] = useState<RecoveryCase | null>(null);

  const [analyticsScope, setAnalyticsScope] = useState<"CURRENT_BATCH" | "CUMULATIVE">("CURRENT_BATCH");
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [systemicIncidentActive, setSystemicIncidentActive] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  const loadAllData = useCallback(async () => {
    try {
      const [sum, caseList, act] = await Promise.all([
        api.getDashboardSummary(selectedBatchId || undefined, analyticsScope),
        api.getRecoveryCases({
          status: statusFilter || undefined,
          search: searchQuery || undefined,
          page_size: 50,
        }),
        api.getActivityFeed(30),
      ]);
      setSummary(sum);
      setCases(caseList);
      setActivityFeed(act);
      setSystemicIncidentActive(sum.systemic_incidents_active > 0);

      if (activeTab === "analytics") {
        const an = await api.getAnalytics(selectedBatchId || undefined, analyticsScope);
        setAnalytics(an);
      }
    } catch (err: any) {
      console.error("Failed to load dashboard data:", err);
    }
  }, [statusFilter, searchQuery, activeTab, selectedBatchId, analyticsScope]);

  useEffect(() => {
    loadAllData();
    const interval = setInterval(loadAllData, 10000); // 10s live sync
    return () => clearInterval(interval);
  }, [loadAllData]);

  const handleReset = async () => {
    if (!confirm("Are you sure you want to reset all simulator and recovery data?")) return;
    setIsLoading(true);
    try {
      await api.resetSimulator();
      await api.seedSimulator(1000);
      setSelectedBatchId(null);
      setAnalyticsScope("CUMULATIVE");
      showToast("Database cleanly reset and re-seeded with 1,000 cases!");
      await loadAllData();
    } catch (err: any) {
      showToast("Reset failed: " + err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSeed = async () => {
    setIsLoading(true);
    try {
      await api.seedSimulator(1000);
      showToast("Seeded 1,000 synthetic payment cases & TX-DEMO-001");
      await loadAllData();
    } catch (err: any) {
      showToast("Seeding failed: " + err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleIncident = async () => {
    const newState = !systemicIncidentActive;
    try {
      await api.toggleSystemicIncident(newState);
      setSystemicIncidentActive(newState);
      showToast(
        newState
          ? "Simulated 45% failure spike on HDFC_BANK. Circuit-breaker active!"
          : "Systemic outage resolved. Automated retries resumed."
      );
      await loadAllData();
    } catch (err: any) {
      showToast("Failed to toggle incident: " + err.message);
    }
  };

  const handleBatchRun = async () => {
    setIsLoading(true);
    try {
      const summaryResult = await api.runBatchRecovery({ limit: 500, seed: 42, dry_run: false });
      setSelectedBatchId(summaryResult.batch_id);
      setAnalyticsScope("CURRENT_BATCH");
      showToast(
        `Batch ${summaryResult.batch_id} complete: ${summaryResult.successful_recoveries} recovered of ${summaryResult.total_candidates} candidates! Incremental: ₹${summaryResult.incremental_recovered_revenue.toLocaleString("en-IN")}`
      );
      await loadAllData();
      if (activeTab === "analytics") {
        const an = await api.getAnalytics(summaryResult.batch_id, "CURRENT_BATCH");
        setAnalytics(an);
      }
    } catch (err: any) {
      showToast("Batch run failed: " + err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // Find TX-DEMO-001 for hero showcase
  const demoCase = cases.find((c) => c.transaction?.external_id === "TX-DEMO-001");

  return (
    <div className="min-h-screen bg-fintech-dark text-gray-100 flex flex-col selection:bg-emerald-500 selection:text-black">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-gray-900 border border-emerald-500/50 text-white px-4 py-2.5 rounded-xl shadow-2xl flex items-center space-x-2 text-xs font-semibold animate-bounce glow-emerald">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Navigation */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        systemicIncidentActive={systemicIncidentActive}
        onToggleIncident={handleToggleIncident}
        onReset={handleReset}
        onSeed={handleSeed}
        onBatchRun={handleBatchRun}
        isLoading={isLoading}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-6 space-y-6">
        {/* OVERVIEW TAB */}
        {activeTab === "dashboard" && (
          <div className="space-y-6">
            {/* Primary Demo Showcase Card (If eligible) */}
            {demoCase && demoCase.status === "RECOVERY_ELIGIBLE" && (
              <div className="bg-gradient-to-r from-emerald-950/80 via-gray-900 to-indigo-950/60 border border-emerald-500/40 rounded-2xl p-5 shadow-xl flex flex-col md:flex-row items-center justify-between gap-4 glow-emerald">
                <div className="flex items-center space-x-4">
                  <div className="w-12 h-12 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center flex-shrink-0">
                    <Sparkles className="w-6 h-6 text-emerald-400 animate-pulse" />
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs uppercase font-extrabold tracking-wider bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 px-2 py-0.5 rounded-full">
                        Primary Demo Showcase
                      </span>
                      <span className="text-sm font-black text-white">TX-DEMO-001 (Arjun Verma)</span>
                    </div>
                    <p className="text-xs text-gray-300 mt-1">
                      ₹12,500 declined due to temporary bank throttle. ML predicts <strong className="text-emerald-400">87% recovery probability</strong>.
                    </p>
                  </div>
                </div>

                <button
                  onClick={() => setSelectedCase(demoCase)}
                  className="w-full md:w-auto px-6 py-2.5 rounded-xl font-extrabold text-xs text-white bg-emerald-500 hover:bg-emerald-400 text-gray-950 transition-all flex items-center justify-center space-x-2 shadow-lg shadow-emerald-900/40"
                >
                  <Zap className="w-4 h-4 text-black fill-black" />
                  <span className="text-black">EXECUTE RECOVERY DEMO</span>
                  <ArrowRight className="w-4 h-4 text-black" />
                </button>
              </div>
            )}

            {/* KPI Cards */}
            <KPICards summary={summary} />

            {/* Revenue Recovery Funnel */}
            <RecoveryFunnel summary={summary} />

            {/* Two-Column Grid: Live Queue Preview + Activity Feed */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2">
                <CaseQueue
                  cases={cases.slice(0, 15)}
                  onSelectCase={(c) => setSelectedCase(c)}
                  onRefresh={loadAllData}
                  statusFilter={statusFilter}
                  setStatusFilter={setStatusFilter}
                  searchQuery={searchQuery}
                  setSearchQuery={setSearchQuery}
                />
              </div>

              <div>
                <AuditTimeline activityFeed={activityFeed.slice(0, 10)} onRefresh={loadAllData} />
              </div>
            </div>
          </div>
        )}

        {/* QUEUE TAB */}
        {activeTab === "queue" && (
          <CaseQueue
            cases={cases}
            onSelectCase={(c) => setSelectedCase(c)}
            onRefresh={loadAllData}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
          />
        )}

        {/* ANALYTICS TAB */}
        {activeTab === "analytics" && (
          <AnalyticsView
            analytics={analytics}
            activeScope={analyticsScope}
            onScopeChange={(scope) => {
              setAnalyticsScope(scope);
            }}
          />
        )}

        {/* AUDIT TAB */}
        {activeTab === "audit" && <AuditTimeline activityFeed={activityFeed} onRefresh={loadAllData} />}
      </main>

      {/* Case Detail & Execution Modal */}
      {selectedCase && (
        <CaseDetailModal
          recoveryCase={selectedCase}
          onClose={() => setSelectedCase(null)}
          onExecutionComplete={async () => {
            await loadAllData();
            // Refresh currently selected case data
            const updated = await api.getRecoveryCase(selectedCase.id);
            setSelectedCase(updated);
          }}
        />
      )}

      {/* Footer */}
      <footer className="border-t border-gray-900 py-4 px-6 text-center text-xs text-gray-600">
        RecoverAI • Razorpay Ideathon Track 03 • Autonomous, Bounded Revenue Recovery Loop
      </footer>
    </div>
  );
};
export default App;
