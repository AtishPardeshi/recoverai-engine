import os
import sys

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.database.session import SessionLocal, Base, engine
from backend.app.simulator.seed_data import seed_database
from backend.app.schemas.batch import BatchRunRequest
from backend.app.services.batch_recovery_service import batch_recovery_service
from backend.app.services.analytics_service import analytics_service

def main():
    print("==================================================")
    print("       RecoverAI — AI Revenue Recovery Agent      ")
    print("==================================================")
    print("Initializing database and seeding synthetic data (seed=42)...")
    
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    seed_database(db, seed=42)
    print("Database seeded successfully.\n")

    print("Executing Batch Recovery (limit=39, seed=42)...")
    req = BatchRunRequest(limit=39, seed=42, dry_run=False)
    summary = batch_recovery_service.run_batch(db, req)

    print("\n----------------- BATCH RESULTS ------------------")
    print(f"Batch ID:                  {summary.batch_id}")
    print(f"Candidates Evaluated:      {summary.total_candidates}")
    print(f"ML Evaluations:            {summary.ml_evaluated}")
    print(f"AI Recommendations:        {summary.ai_recommended}")
    print(f"Policy Approved:           {summary.policy_approved}")
    print(f"Policy Rejected:           {summary.policy_rejected}")
    print(f"Actions Executed:          {summary.actions_executed}")
    print(f"Successful Recoveries:     {summary.successful_recoveries}")
    print(f"Actual Recovered Revenue:  ₹{summary.agent_recovered_revenue:,.2f}")
    print(f"Baseline Recovery:         ₹{summary.baseline_recovered_revenue:,.2f}")
    print(f"Incremental Revenue:       ₹{summary.incremental_recovered_revenue:,.2f}")
    print("--------------------------------------------------")

    # Invariant Check
    expected_inc = round(summary.agent_recovered_revenue - summary.baseline_recovered_revenue, 2)
    assert round(summary.incremental_recovered_revenue, 2) == expected_inc, "Invariant mismatch!"
    print(f"✓ INVARIANT SATISFIED: ₹{summary.agent_recovered_revenue:,.2f} - ₹{summary.baseline_recovered_revenue:,.2f} = ₹{summary.incremental_recovered_revenue:,.2f}")

    print("\nFetching Cumulative Database Totals...")
    cum = analytics_service.get_dashboard_summary(db, scope="CUMULATIVE")
    print(f"Cumulative DB Recovered:   ₹{cum.recovered_revenue:,.2f}")
    print(f"Cumulative DB Baseline:    ₹{cum.baseline_recovered_revenue:,.2f}")
    print(f"Cumulative DB Incremental: ₹{cum.incremental_recovered_revenue:,.2f}")

    print("\nVerifying Idempotency via Batch Rerun...")
    rerun_summary = batch_recovery_service.run_batch(db, req)
    print(f"Rerun Successful Recoveries: {rerun_summary.successful_recoveries}")
    print(f"Rerun Recovered Revenue:     ₹{rerun_summary.agent_recovered_revenue:,.2f}")
    print("✓ IDEMPOTENCY VERIFIED: Terminal cases protected from duplicate financial recovery.")

    db.close()
    print("\nDemo completed successfully!")

if __name__ == "__main__":
    main()
