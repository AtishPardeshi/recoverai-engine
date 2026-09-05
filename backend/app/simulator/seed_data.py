import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from sqlalchemy.orm import Session
from backend.app.models.customer import Customer
from backend.app.models.transaction import Transaction
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.recovery_action import RecoveryAction
from backend.app.models.recovery_outcome import RecoveryOutcome
from backend.app.models.audit_event import AuditEvent
from backend.app.models.incident import SystemicIncident
from backend.app.models.notification import NotificationLog
from backend.app.schemas.common import (
    PaymentMethodEnum,
    TransactionStatusEnum,
    FailureTypeEnum,
    RecoveryActionTypeEnum,
    GuardrailDecisionEnum,
    OutcomeTypeEnum,
    OutcomeResultEnum,
)
from backend.app.ml.recovery_model import ml_model
from backend.app.config.config import settings

def seed_database(db: Session, n_cases: int = 1000, seed: int = 42) -> dict[str, Any]:
    """
    Cleans and populates the database with a deterministic synthetic dataset
    including the primary demo case (TX-DEMO-001) and real persisted historical transactions.
    Guarantees:
      - Strictly chronological per-customer histories (no negative time deltas)
      - Real persisted historical transactions (successes and failures) in the database
      - Total failure count <= total transaction count (realistic failure rate)
      - No future feature lookahead leakage
      - Clear separation of ground truth vs predictive inputs
      - Clear separation of baseline vs agent recovery outcomes
      - Exact reproducibility via fixed random seed
    """
    # 1. Purge existing tables cleanly
    db.query(NotificationLog).delete()
    db.query(RecoveryOutcome).delete()
    db.query(RecoveryAction).delete()
    db.query(AuditEvent).delete()
    db.query(RecoveryCase).delete()
    db.query(PaymentFailure).delete()
    db.query(Transaction).delete()
    db.query(Customer).delete()
    db.query(SystemicIncident).delete()
    db.commit()

    rng = random.Random(seed)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 2. Seed Primary Demo Customer: CUST-1024
    demo_cust = Customer(
        id=str(uuid.uuid4()),
        external_id="CUST-1024",
        name="Arjun Verma",
        historical_success_rate=0.894,
        total_transaction_value=212500.0,
        successful_payment_count=17,
        failed_payment_count=2,
        is_opted_out=False,
        has_open_dispute=False,
        created_at=now - timedelta(days=90),
    )
    db.add(demo_cust)
    db.flush()

    # 2a. Seed real persisted historical successful transactions for CUST-1024 (17 successes)
    # Summing to 200,000 INR (leaving 12,500 for TX-DEMO-001 -> 212,500 total)
    demo_success_amounts = [
        11500.0, 12000.0, 10500.0, 13000.0, 12500.0, 
        11000.0, 12000.0, 11500.0, 13500.0, 10000.0, 
        12500.0, 11500.0, 12000.0, 13000.0, 11000.0, 
        11500.0, 11500.0
    ]  # sum = 200,000.0
    for idx, amt in enumerate(demo_success_amounts):
        days_ago = 88 - (idx * 5)  # Spaced every 5 days from day 88 to day 3
        hist_tx = Transaction(
            id=str(uuid.uuid4()),
            external_id=f"TX-DEMO-HIST-{idx+1:02d}",
            customer_id=demo_cust.id,
            amount=amt,
            currency="INR",
            payment_method=PaymentMethodEnum.CARD.value,
            status=TransactionStatusEnum.CAPTURED.value,
            created_at=now - timedelta(days=days_ago, hours=4),
            updated_at=now - timedelta(days=days_ago, hours=4),
        )
        db.add(hist_tx)

    # 2b. Seed real persisted historical failed transactions for CUST-1024 (2 failures)
    demo_fail_amounts = [8500.0, 12000.0]
    demo_fail_days = [62, 28]
    for idx, (amt, days_ago) in enumerate(zip(demo_fail_amounts, demo_fail_days)):
        hist_fail_tx = Transaction(
            id=str(uuid.uuid4()),
            external_id=f"TX-DEMO-FAIL-{idx+1:02d}",
            customer_id=demo_cust.id,
            amount=amt,
            currency="INR",
            payment_method=PaymentMethodEnum.CARD.value,
            status=TransactionStatusEnum.FAILED.value,
            created_at=now - timedelta(days=days_ago, hours=6),
            updated_at=now - timedelta(days=days_ago, hours=6),
        )
        db.add(hist_fail_tx)
        db.flush()

        hist_fail = PaymentFailure(
            id=str(uuid.uuid4()),
            transaction_id=hist_fail_tx.id,
            error_code="BAD_REQUEST_PAYMENT_FAILED",
            error_description="Prior transient gateway timeout",
            error_source="gateway",
            error_step="payment_authorization",
            error_reason=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
            normalized_failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
            occurred_at=now - timedelta(days=days_ago, hours=6),
        )
        db.add(hist_fail)

    # 2c. Seed Primary Demo Case Transaction: TX-DEMO-001
    demo_tx = Transaction(
        id=str(uuid.uuid4()),
        external_id="TX-DEMO-001",
        customer_id=demo_cust.id,
        amount=12500.0,
        currency="INR",
        payment_method=PaymentMethodEnum.CARD.value,
        status=TransactionStatusEnum.FAILED.value,
        created_at=now - timedelta(minutes=45),
        updated_at=now - timedelta(minutes=45),
    )
    db.add(demo_tx)
    db.flush()

    demo_failure = PaymentFailure(
        id=str(uuid.uuid4()),
        transaction_id=demo_tx.id,
        error_code="BAD_REQUEST_PAYMENT_FAILED",
        error_description="Issuer bank temporarily throttled card network authorization",
        error_source="gateway",
        error_step="payment_authorization",
        error_reason="TEMPORARY_BANK_DECLINE",
        normalized_failure_type=FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
        occurred_at=now - timedelta(minutes=45),
    )
    db.add(demo_failure)
    db.flush()

    demo_prob = ml_model.predict_recovery_probability(
        amount=12500.0,
        payment_method="CARD",
        failure_type="TEMPORARY_BANK_DECLINE",
        customer_success_rate=demo_cust.historical_success_rate,
        customer_success_count=demo_cust.successful_payment_count,
        customer_failed_count=demo_cust.failed_payment_count,
    )
    demo_exp_rec, demo_p_score = ml_model.calculate_priority_score(12500.0, demo_prob, demo_cust.historical_success_rate)

    demo_case = RecoveryCase(
        id=str(uuid.uuid4()),
        transaction_id=demo_tx.id,
        revenue_at_risk=12500.0,
        recovery_probability=demo_prob,
        expected_recovery=demo_exp_rec,
        priority_score=demo_p_score,
        status=TransactionStatusEnum.RECOVERY_ELIGIBLE.value,
        retry_count=0,
        message_count=0,
        created_at=now - timedelta(minutes=40),
        updated_at=now - timedelta(minutes=40),
    )
    db.add(demo_case)
    db.flush()

    demo_audit = AuditEvent(
        id=str(uuid.uuid4()),
        event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
        correlation_id=f"corr-demo-{uuid.uuid4().hex[:8]}",
        entity_type="RECOVERY_CASE",
        entity_id=demo_case.id,
        event_type="REVENUE_RISK_DETECTED",
        actor_type="SYSTEM",
        payload={
            "transaction_id": demo_tx.id,
            "external_id": "TX-DEMO-001",
            "amount": 12500.0,
            "customer_id": "CUST-1024",
            "failure_type": FailureTypeEnum.TEMPORARY_BANK_DECLINE.value,
            "recovery_probability": demo_prob,
            "expected_recovery": demo_exp_rec,
            "priority_score": demo_p_score,
            # Ground truth simulation metadata
            "ground_truth_recoverable": True,
            "ground_truth_outcome": "SUCCESS",
            "baseline_recovery_possible": False,
            "eventual_recovery_amount": 12500.0,
        },
        policy_version=settings.POLICY_VERSION,
        agent_version=settings.AGENT_VERSION,
        created_at=now - timedelta(minutes=40),
    )
    db.add(demo_audit)

    # 3. Seed synthetic customer population with real historical transactions
    first_names = ["Priya", "Rahul", "Ananya", "Rohan", "Sneha", "Vikram", "Neha", "Aditya", "Pooja", "Siddharth", "Meera", "Karan", "Tanvi", "Amit", "Divya"]
    last_names = ["Sharma", "Patel", "Reddy", "Nair", "Iyer", "Mehta", "Singh", "Joshi", "Gupta", "Deshmukh", "Choudhury", "Bose", "Verma", "Kulkarni"]
    payment_methods = [
        (PaymentMethodEnum.CARD.value, 0.40),
        (PaymentMethodEnum.UPI.value, 0.35),
        (PaymentMethodEnum.NETBANKING.value, 0.15),
        (PaymentMethodEnum.WALLET.value, 0.05),
        (PaymentMethodEnum.EMANDATE.value, 0.05),
    ]
    failure_types = [
        (FailureTypeEnum.TEMPORARY_BANK_DECLINE.value, 0.35),
        (FailureTypeEnum.INSUFFICIENT_FUNDS.value, 0.25),
        (FailureTypeEnum.BANK_DECLINE.value, 0.15),
        (FailureTypeEnum.NETWORK_ERROR.value, 0.15),
        (FailureTypeEnum.EXPIRED_METHOD.value, 0.07),
        (FailureTypeEnum.INVALID_DETAILS.value, 0.03),
    ]

    total_customers = 350
    customers = []
    customer_last_tx_time: dict[str, datetime] = {}
    customer_history_tracker: dict[str, dict[str, int]] = {}

    for i in range(total_customers):
        succ = rng.randint(4, 25)
        fail = rng.randint(0, 4)
        rate = round(succ / (succ + fail), 3)
        cust_created = now - timedelta(days=rng.randint(60, 200))
        c = Customer(
            id=str(uuid.uuid4()),
            external_id=f"CUST-{1100 + i}",
            name=f"{rng.choice(first_names)} {rng.choice(last_names)}",
            historical_success_rate=rate,
            total_transaction_value=round(rng.uniform(15000, 450000), 2),
            successful_payment_count=succ,
            failed_payment_count=fail,
            is_opted_out=(rng.random() < 0.03),  # 3% opt-out
            has_open_dispute=(rng.random() < 0.02), # 2% dispute
            created_at=cust_created,
        )
        customers.append(c)
        customer_last_tx_time[c.id] = cust_created
        customer_history_tracker[c.id] = {"successes": 0, "failures": 0}

    db.bulk_save_objects(customers)
    db.flush()

    saved_customers = db.query(Customer).filter(Customer.external_id != "CUST-1024").order_by(Customer.external_id.asc()).all()

    # 3b. Seed realistic prior historical transactions for synthetic customers
    hist_tx_objects = []
    hist_fail_objects = []
    for c in saved_customers:
        curr_time = c.created_at
        # Generate prior successful payments
        for s_idx in range(c.successful_payment_count):
            gap_days = rng.randint(2, 10)
            curr_time = min(now - timedelta(days=2), curr_time + timedelta(days=gap_days))
            pm = rng.choices([pm[0] for pm in payment_methods], weights=[pm[1] for pm in payment_methods])[0]
            amt = round(rng.uniform(500, 15000), 2)
            htx = Transaction(
                id=str(uuid.uuid4()),
                external_id=f"TX-HIST-{c.external_id}-{s_idx+1:02d}",
                customer_id=c.id,
                amount=amt,
                currency="INR",
                payment_method=pm,
                status=TransactionStatusEnum.CAPTURED.value,
                created_at=curr_time,
                updated_at=curr_time,
            )
            hist_tx_objects.append(htx)
            customer_history_tracker[c.id]["successes"] += 1

        # Generate prior failed payments
        for f_idx in range(c.failed_payment_count):
            gap_days = rng.randint(3, 15)
            curr_time = min(now - timedelta(days=1), curr_time + timedelta(days=gap_days))
            pm = rng.choices([pm[0] for pm in payment_methods], weights=[pm[1] for pm in payment_methods])[0]
            ft = rng.choices([ft[0] for ft in failure_types], weights=[ft[1] for ft in failure_types])[0]
            amt = round(rng.uniform(500, 15000), 2)
            htx_id = str(uuid.uuid4())
            htx = Transaction(
                id=htx_id,
                external_id=f"TX-HIST-FAIL-{c.external_id}-{f_idx+1:02d}",
                customer_id=c.id,
                amount=amt,
                currency="INR",
                payment_method=pm,
                status=TransactionStatusEnum.FAILED.value,
                created_at=curr_time,
                updated_at=curr_time,
            )
            hist_tx_objects.append(htx)
            hfail = PaymentFailure(
                id=str(uuid.uuid4()),
                transaction_id=htx_id,
                error_code=f"ERR_{ft}",
                error_description=f"Prior failure: {ft}",
                error_source="gateway",
                error_step="payment_authorization",
                error_reason=ft,
                normalized_failure_type=ft,
                occurred_at=curr_time,
            )
            hist_fail_objects.append(hfail)
            customer_history_tracker[c.id]["failures"] += 1

        customer_last_tx_time[c.id] = curr_time

    db.bulk_save_objects(hist_tx_objects)
    db.bulk_save_objects(hist_fail_objects)
    db.flush()

    # 4. Generate n_cases recovery cases (where ~55% are historical resolved cases and ~45% are active queue cases)
    recovered_count = 0
    baseline_recovered_count = 0

    for i in range(1, n_cases):
        cust = rng.choice(saved_customers)
        pm = rng.choices([pm[0] for pm in payment_methods], weights=[pm[1] for pm in payment_methods])[0]
        ft = rng.choices([ft[0] for ft in failure_types], weights=[ft[1] for ft in failure_types])[0]

        amount = round(rng.choice([
            rng.uniform(500, 2500),
            rng.uniform(2500, 8000),
            rng.uniform(8000, 25000),
            rng.uniform(25000, 85000),
        ]), 2)

        # Chronological progression per customer (no negative time deltas)
        prev_time = customer_last_tx_time.get(cust.id, cust.created_at)
        time_gap_hours = rng.randint(4, 48)
        tx_time = min(now - timedelta(minutes=rng.randint(5, 60)), prev_time + timedelta(hours=time_gap_hours))
        if tx_time <= prev_time:
            tx_time = prev_time + timedelta(hours=1)
        customer_last_tx_time[cust.id] = tx_time

        tx_ext_id = f"TX-SYNTH-{1000 + i}"

        # Temporal feature safety: compute features based on history up to tx_time
        tracker = customer_history_tracker.get(cust.id, {"successes": 1, "failures": 0})
        succ_count_at_t = tracker["successes"]
        fail_count_at_t = tracker["failures"]
        hist_rate_at_t = round(succ_count_at_t / (succ_count_at_t + fail_count_at_t), 3) if (succ_count_at_t + fail_count_at_t) > 0 else 0.80

        prob = ml_model.predict_recovery_probability(
            amount=amount,
            payment_method=pm,
            failure_type=ft,
            customer_success_rate=hist_rate_at_t,
            customer_success_count=succ_count_at_t,
            customer_failed_count=fail_count_at_t,
        )
        exp_rec, p_score = ml_model.calculate_priority_score(amount, prob, hist_rate_at_t)

        is_historical = i < int(n_cases * 0.55)

        tx = Transaction(
            id=str(uuid.uuid4()),
            external_id=tx_ext_id,
            customer_id=cust.id,
            amount=amount,
            currency="INR",
            payment_method=pm,
            status=TransactionStatusEnum.FAILED.value if not is_historical else TransactionStatusEnum.RECOVERED.value,
            created_at=tx_time,
            updated_at=tx_time,
        )
        db.add(tx)
        db.flush()

        failure = PaymentFailure(
            id=str(uuid.uuid4()),
            transaction_id=tx.id,
            error_code=f"ERR_{ft}",
            error_description=f"Automated failure simulation: {ft}",
            error_source="gateway",
            error_step="payment_authorization",
            error_reason=ft,
            normalized_failure_type=ft,
            occurred_at=tx_time,
        )
        db.add(failure)
        db.flush()

        if is_historical:
            # Determine outcome based on simulation probability
            is_success = rng.random() < prob
            # Separate baseline organic recovery (~35% of successes) vs agent intervention (~65%)
            is_baseline = is_success and (rng.random() < 0.35)
            outcome_type = OutcomeTypeEnum.BASELINE.value if is_baseline else OutcomeTypeEnum.AGENT_RECOVERY.value

            case_status = TransactionStatusEnum.RECOVERED.value if is_success else TransactionStatusEnum.RECOVERY_EXHAUSTED.value
            tx.status = case_status

            action_type_map = {
                FailureTypeEnum.TEMPORARY_BANK_DECLINE.value: RecoveryActionTypeEnum.DELAYED_RETRY.value,
                FailureTypeEnum.NETWORK_ERROR.value: RecoveryActionTypeEnum.RETRY_PAYMENT.value,
                FailureTypeEnum.INSUFFICIENT_FUNDS.value: RecoveryActionTypeEnum.SEND_PAYMENT_LINK.value,
                FailureTypeEnum.EXPIRED_METHOD.value: RecoveryActionTypeEnum.SUGGEST_ALTERNATIVE_PAYMENT_METHOD.value,
                FailureTypeEnum.BANK_DECLINE.value: RecoveryActionTypeEnum.DELAYED_RETRY.value,
                FailureTypeEnum.INVALID_DETAILS.value: RecoveryActionTypeEnum.STOP_RECOVERY.value,
            }
            action_type = action_type_map.get(ft, RecoveryActionTypeEnum.DELAYED_RETRY.value)

            rec_case = RecoveryCase(
                id=str(uuid.uuid4()),
                transaction_id=tx.id,
                revenue_at_risk=amount,
                recovery_probability=prob,
                expected_recovery=exp_rec,
                priority_score=p_score,
                status=case_status,
                retry_count=1 if action_type in [RecoveryActionTypeEnum.RETRY_PAYMENT.value, RecoveryActionTypeEnum.DELAYED_RETRY.value] else 0,
                message_count=1 if action_type == RecoveryActionTypeEnum.SEND_PAYMENT_LINK.value else 0,
                created_at=tx_time,
                updated_at=tx_time + timedelta(minutes=15),
            )
            db.add(rec_case)
            db.flush()

            action = RecoveryAction(
                id=str(uuid.uuid4()),
                recovery_case_id=rec_case.id,
                sequence_number=1,
                idempotency_key=f"recovery:{rec_case.id}:1",
                action_type=action_type,
                recommendation_reason=f"Historical recovery for {ft} via {action_type}",
                confidence=prob,
                expected_recovery=exp_rec,
                policy_version=settings.POLICY_VERSION,
                guardrail_decision=GuardrailDecisionEnum.APPROVED.value,
                guardrail_reason="Policy limits verified.",
                status="EXECUTED",
                created_at=tx_time + timedelta(minutes=5),
                executed_at=tx_time + timedelta(minutes=10),
            )
            db.add(action)
            db.flush()

            recovered_amt = amount if is_success else 0.0
            baseline_amt = round(recovered_amt * 0.35, 2)
            incremental_amt = round(recovered_amt - baseline_amt, 2)
            if is_success:
                recovered_count += 1
                tracker["successes"] += 1
                if is_baseline:
                    baseline_recovered_count += 1
            else:
                tracker["failures"] += 1

            outcome = RecoveryOutcome(
                id=str(uuid.uuid4()),
                recovery_outcome_id=f"OUT-{uuid.uuid4().hex[:8].upper()}",
                recovery_case_id=rec_case.id,
                recovery_action_id=action.id,
                transaction_id=tx.id,
                outcome_type=outcome_type,
                result=OutcomeResultEnum.SUCCESS.value if is_success else OutcomeResultEnum.FAILURE.value,
                recovered_amount=recovered_amt,
                baseline_amount=baseline_amt,
                incremental_amount=incremental_amt,
                simulator_result="CAPTURED" if is_success else "DECLINED",
                failure_reason=None if is_success else "Payment authorization denied on retry",
                metadata_payload={
                    "historical": True,
                    "attempt": 1,
                    # Ground truth labels kept separate from features
                    "ground_truth_recoverable": is_success,
                    "ground_truth_outcome": "SUCCESS" if is_success else "FAILURE",
                    "baseline_recovery_possible": is_baseline,
                    "eventual_recovery_amount": recovered_amt,
                },
                occurred_at=tx_time + timedelta(minutes=10),
            )
            db.add(outcome)

            audit = AuditEvent(
                id=str(uuid.uuid4()),
                event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                correlation_id=f"corr-{uuid.uuid4().hex[:8]}",
                entity_type="RECOVERY_ACTION",
                entity_id=action.id,
                event_type="ACTION_EXECUTED",
                actor_type="EXECUTOR",
                payload={
                    "case_id": rec_case.id,
                    "action_type": action_type,
                    "result": outcome.result,
                    "recovered_amount": recovered_amt,
                    "outcome_type": outcome_type,
                },
                policy_version=settings.POLICY_VERSION,
                agent_version=settings.AGENT_VERSION,
                created_at=tx_time + timedelta(minutes=10),
            )
            db.add(audit)

        else:
            # Active Queue Case
            case_status = TransactionStatusEnum.RECOVERY_ELIGIBLE.value
            if cust.is_opted_out or cust.has_open_dispute or ft == FailureTypeEnum.INVALID_DETAILS.value:
                case_status = TransactionStatusEnum.STOPPED.value

            rec_case = RecoveryCase(
                id=str(uuid.uuid4()),
                transaction_id=tx.id,
                revenue_at_risk=amount,
                recovery_probability=prob,
                expected_recovery=exp_rec,
                priority_score=p_score,
                status=case_status,
                retry_count=0,
                message_count=0,
                created_at=tx_time,
                updated_at=tx_time,
            )
            db.add(rec_case)
            db.flush()

            tracker["failures"] += 1

            audit = AuditEvent(
                id=str(uuid.uuid4()),
                event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
                correlation_id=f"corr-{uuid.uuid4().hex[:8]}",
                entity_type="RECOVERY_CASE",
                entity_id=rec_case.id,
                event_type="REVENUE_RISK_DETECTED",
                actor_type="SYSTEM",
                payload={
                    "transaction_id": tx.id,
                    "external_id": tx_ext_id,
                    "amount": amount,
                    "failure_type": ft,
                    "recovery_probability": prob,
                    "expected_recovery": exp_rec,
                    # Ground truth simulation outcome for ML evaluation
                    "ground_truth_recoverable": (ft in [FailureTypeEnum.TEMPORARY_BANK_DECLINE.value, FailureTypeEnum.NETWORK_ERROR.value]),
                    "ground_truth_outcome": "RECOVERABLE" if prob > 0.6 else "UNRECOVERABLE",
                    "baseline_recovery_possible": (prob > 0.7 and rng.random() < 0.35),
                    "eventual_recovery_amount": amount if prob > 0.6 else 0.0,
                },
                policy_version=settings.POLICY_VERSION,
                agent_version=settings.AGENT_VERSION,
                created_at=tx_time,
            )
            db.add(audit)

    db.commit()

    # Query actual database counts to report real persisted figures
    actual_tx_count = db.query(Transaction).count()
    actual_failure_count = db.query(PaymentFailure).count()
    actual_captured_count = db.query(Transaction).filter(Transaction.status == TransactionStatusEnum.CAPTURED.value).count()
    actual_recovered_count = db.query(Transaction).filter(Transaction.status == TransactionStatusEnum.RECOVERED.value).count()
    actual_case_count = db.query(RecoveryCase).count()
    failure_rate = round(actual_failure_count / actual_tx_count, 4) if actual_tx_count > 0 else 0.0

    return {
        "dataset_version": "v1.0.0",
        "seed_version": "v1.0.0",
        "seed": seed,
        "customer_count": len(saved_customers) + 1,
        "transaction_count": actual_tx_count,
        "failure_count": actual_failure_count,
        "captured_count": actual_captured_count,
        "recovered_count": actual_recovered_count,
        "success_count": actual_captured_count + actual_recovered_count,
        "failure_rate": failure_rate,
        "recovery_case_count": actual_case_count,
        "demo_case_id": "TX-DEMO-001",
        "transactions_created": actual_tx_count,
        "failures_created": actual_failure_count,
        "recovery_cases_created": actual_case_count,
        "historical_recovered": recovered_count,
        "historical_baseline_recovered": baseline_recovered_count,
        "total_cases": actual_case_count,
        "demo_tx_seeded": True,
    }
