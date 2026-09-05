import React from "react";
import { Shield, RefreshCw, Database, AlertTriangle } from "lucide-react";

interface NavbarProps {
  activeTab: "dashboard" | "queue" | "analytics" | "audit";
  setActiveTab: (tab: "dashboard" | "queue" | "analytics" | "audit") => void;
  systemicIncidentActive: boolean;
  onToggleIncident: () => void;
  onReset: () => void;
  onSeed: () => void;
  onBatchRun: () => void;
  isLoading: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  systemicIncidentActive,
  onToggleIncident,
  onReset,
  onSeed,
  onBatchRun,
  isLoading,
}) => {
  return (
    <header className="sticky top-0 z-40 bg-fintech-dark/90 backdrop-blur-md border-b border-fintech-border/70 px-6 py-3">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        {/* Brand & Tagline */}
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2.5">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-900/40">
              <Shield className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-xl font-black tracking-tight text-white">Recover<span className="text-emerald-400">AI</span></span>
                <span className="text-[10px] uppercase font-bold tracking-widest bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-full">
                  Autonomous Agent
                </span>
              </div>
              <p className="text-xs text-gray-400">Autonomous Revenue Recovery Platform</p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="hidden md:flex items-center ml-8 space-x-1 bg-gray-900/80 p-1 rounded-xl border border-gray-800">
            <button
              onClick={() => setActiveTab("dashboard")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === "dashboard"
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shadow-sm"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Overview & KPIs
            </button>
            <button
              onClick={() => setActiveTab("queue")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === "queue"
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shadow-sm"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Active Recovery Queue
            </button>
            <button
              onClick={() => setActiveTab("analytics")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === "analytics"
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shadow-sm"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Intelligence & Analytics
            </button>
            <button
              onClick={() => setActiveTab("audit")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === "audit"
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shadow-sm"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Audit Trail & Feed
            </button>
          </nav>
        </div>

        {/* Demo Simulator Controls */}
        <div className="flex items-center space-x-2.5">
          {/* Run Batch Recovery */}
          <button
            onClick={onBatchRun}
            disabled={isLoading}
            className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/30 transition-all disabled:opacity-50 glow-emerald"
            title="Execute batch recovery across all eligible cases through ML -> AI -> Policy -> Executor"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            <span>Run Batch Recovery</span>
          </button>

          {/* Outage Circuit Breaker Toggle */}
          <button
            onClick={onToggleIncident}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
              systemicIncidentActive
                ? "bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse"
                : "bg-gray-800/80 text-gray-400 border-gray-700 hover:text-gray-200"
            }`}
            title="Simulate correlated bank outage spike to test guardrail circuit breaker"
          >
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            <span>{systemicIncidentActive ? "Outage Sim Active" : "Simulate Outage"}</span>
          </button>

          {/* Seed Dataset */}
          <button
            onClick={onSeed}
            disabled={isLoading}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-gray-800/80 hover:bg-gray-700 text-gray-300 border border-gray-700 transition-all disabled:opacity-50"
            title="Re-seed 1,000 synthetic payment cases + TX-DEMO-001"
          >
            <Database className="w-3.5 h-3.5 text-blue-400" />
            <span>Seed 1k Cases</span>
          </button>

          {/* Reset Demo */}
          <button
            onClick={onReset}
            disabled={isLoading}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-950/30 hover:bg-red-900/40 text-red-400 border border-red-800/40 transition-all disabled:opacity-50"
            title="Clean reset all database state"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            <span>Reset Demo</span>
          </button>
        </div>
      </div>

      {/* Systemic Incident Active Banner */}
      {systemicIncidentActive && (
        <div className="mt-2.5 max-w-7xl mx-auto bg-amber-500/15 border border-amber-500/40 rounded-lg px-4 py-2 flex items-center justify-between text-xs text-amber-200">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 animate-bounce" />
            <span className="font-semibold">
              SYSTEMIC INCIDENT CIRCUIT-BREAKER TRIPPED: 45% failure spike detected on HDFC_BANK.
            </span>
            <span className="hidden sm:inline text-amber-300/80">
              Policy Guardrails have automatically throttled automated retries to prevent cascade.
            </span>
          </div>
          <button
            onClick={onToggleIncident}
            className="text-amber-400 underline hover:text-amber-300 font-bold ml-4"
          >
            Resolve Outage
          </button>
        </div>
      )}
    </header>
  );
};
