import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.orm import Session
from backend.app.models.transaction import Transaction
from backend.app.models.payment_failure import PaymentFailure
from backend.app.models.recovery_case import RecoveryCase
from backend.app.models.customer import Customer
from backend.app.models.audit_event import AuditEvent
from backend.app.schemas.common import TransactionStatusEnum, FailureTypeEnum
from backend.app.ml.recovery_model import ml_model
from backend.app.config.config import settings

# In-memory LRU cache for processed webhook event deduplication
_PROCESSED_EVENT_IDS: set[str] = set()

def normalize_razorpay_error(
    error_code: str,
    error_description: str | None,
    error_step: str | None,
    error_reason: str | None,
) -> str:
    """
    Translates provider error taxonomy into internal normalized failure types.
    """
    code_upper = (error_code or "").upper()
    desc_upper = (error_description or "").upper()
    reason_upper = (error_reason or "").upper()

    if "BAD_REQUEST_AUTHENTICATION" in code_upper or "INVALID" in code_upper or "INCORRECT_CVV" in reason_upper or "INVALID_DETAILS" in reason_upper:
        return FailureTypeEnum.INVALID_DETAILS.value
    if "EXPIRED" in code_upper or "EXPIRED_CARD" in reason_upper or "MANDATE_EXPIRED" in desc_upper or "EXPIRED_METHOD" in reason_upper:
        return FailureTypeEnum.EXPIRED_METHOD.value
    if "INSUFFICIENT" in code_upper or "INSUFFICIENT_FUNDS" in reason_upper or "BALANCE" in desc_upper:
        return FailureTypeEnum.INSUFFICIENT_FUNDS.value
    if "NETWORK" in code_upper or "TIMEOUT" in desc_upper or "GATEWAY_TIMEOUT" in code_upper or "NETWORK_ERROR" in reason_upper:
        return FailureTypeEnum.NETWORK_ERROR.value
    if "TEMPORARY" in code_upper or "THROTTLED" in desc_upper or "BANK_SYSTEM_OUTAGE" in reason_upper or "TECHNICAL_ERROR" in reason_upper or "TEMPORARY_BANK_DECLINE" in reason_upper:
        return FailureTypeEnum.TEMPORARY_BANK_DECLINE.value

    return FailureTypeEnum.BANK_DECLINE.value


def ingest_payment_event(
    db: Session,
    event_id: str,
    event_type: str,
    payload: dict[str, Any],
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Ingests payment events with deduplication, out-of-order state precedence, and automated recovery case generation.
    Supported Event Types:
      - payment.failed
      - payment.authorized
      - payment.captured
      - order.paid
      - subscription.charged
      - subscription.pending
      - subscription.halted
      - invoice.paid
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc)

    # 1. Deduplication check (memory + database audit check)
    if event_id in _PROCESSED_EVENT_IDS:
        return {
            "status": "DEDUPLICATED",
            "message": f"Event {event_id} already ingested.",
            "event_id": event_id,
            "correlation_id": correlation_id,
        }

    existing_audit = db.query(AuditEvent).filter(AuditEvent.event_id == f"EVT-{event_id}").first()
    if existing_audit:
        _PROCESSED_EVENT_IDS.add(event_id)
        return {
            "status": "DEDUPLICATED",
            "message": f"Event {event_id} already persisted.",
            "event_id": event_id,
            "correlation_id": correlation_id,
        }

    _PROCESSED_EVENT_IDS.add(event_id)

    tx_data = payload.get("transaction", {})
    cust_data = payload.get("customer", {})
    err_data = payload.get("error", {})

    external_id = tx_data.get("id") or tx_data.get("external_id") or f"TX-{uuid.uuid4().hex[:8].upper()}"
    cust_ext_id = cust_data.get("id") or cust_data.get("external_id") or f"CUST-{uuid.uuid4().hex[:6].upper()}"

    # 2. Handle Payment Success / Capture Events (payment.captured, order.paid, subscription.charged, invoice.paid)
    if event_type in ["payment.captured", "order.paid", "subscription.charged", "invoice.paid"]:
        tx = db.query(Transaction).filter(Transaction.external_id == external_id).first()
        if tx:
            tx.status = TransactionStatusEnum.RECOVERED.value
            tx.updated_at = now
            # Close active recovery case if present
            case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == tx.id).first()
            if case:
                case.status = TransactionStatusEnum.RECOVERED.value
                case.closed_at = now
                case.updated_at = now

            audit = AuditEvent(
                id=str(uuid.uuid4()),
                event_id=f"EVT-{event_id}",
                correlation_id=correlation_id,
                entity_type="TRANSACTION",
                entity_id=tx.id,
                event_type="PAYMENT_CAPTURED",
                actor_type="SYSTEM",
                payload={"event_id": event_id, "event_type": event_type, "external_id": external_id},
                policy_version=settings.POLICY_VERSION,
                agent_version=settings.AGENT_VERSION,
                created_at=now,
            )
            db.add(audit)
            db.commit()

            return {
                "status": "TRANSACTION_CAPTURED",
                "transaction_id": tx.id,
                "event_id": event_id,
                "correlation_id": correlation_id,
            }

        # Create captured transaction if not existing
        customer = db.query(Customer).filter(Customer.external_id == cust_ext_id).first()
        if not customer:
            customer = Customer(
                id=str(uuid.uuid4()),
                external_id=cust_ext_id,
                name=cust_data.get("name", "Merchant Customer"),
                historical_success_rate=cust_data.get("historical_success_rate", 0.90),
                total_transaction_value=cust_data.get("total_transaction_value", 50000.0),
                successful_payment_count=cust_data.get("successful_payment_count", 5),
                failed_payment_count=cust_data.get("failed_payment_count", 0),
            )
            db.add(customer)
            db.flush()

        tx = Transaction(
            id=str(uuid.uuid4()),
            external_id=external_id,
            customer_id=customer.id,
            amount=float(tx_data.get("amount", 1000.0)),
            currency=tx_data.get("currency", "INR"),
            payment_method=tx_data.get("payment_method", "CARD"),
            status=TransactionStatusEnum.CAPTURED.value,
            created_at=now,
            updated_at=now,
        )
        db.add(tx)
        db.flush()

        audit = AuditEvent(
            id=str(uuid.uuid4()),
            event_id=f"EVT-{event_id}",
            correlation_id=correlation_id,
            entity_type="TRANSACTION",
            entity_id=tx.id,
            event_type="PAYMENT_CAPTURED",
            actor_type="SYSTEM",
            payload={"event_id": event_id, "event_type": event_type, "external_id": external_id},
            policy_version=settings.POLICY_VERSION,
            agent_version=settings.AGENT_VERSION,
            created_at=now,
        )
        db.add(audit)
        db.commit()

        return {
            "status": "TRANSACTION_CAPTURED",
            "transaction_id": tx.id,
            "event_id": event_id,
            "correlation_id": correlation_id,
        }

    # 3. Handle Payment Authorization Events (payment.authorized)
    if event_type == "payment.authorized":
        tx = db.query(Transaction).filter(Transaction.external_id == external_id).first()
        if tx:
            if tx.status not in [TransactionStatusEnum.CAPTURED.value, TransactionStatusEnum.RECOVERED.value]:
                tx.status = TransactionStatusEnum.AUTHORIZED.value
                tx.updated_at = now
            db.commit()
            return {
                "status": "PAYMENT_AUTHORIZED",
                "transaction_id": tx.id,
                "event_id": event_id,
                "correlation_id": correlation_id,
            }

    # 4. Handle Payment Failed Events (payment.failed)
    if event_type == "payment.failed":
        # Check if transaction already exists and is in terminal CAPTURED or RECOVERED state (Out-of-order tolerance)
        existing_tx = db.query(Transaction).filter(Transaction.external_id == external_id).first()
        if existing_tx and existing_tx.status in [TransactionStatusEnum.CAPTURED.value, TransactionStatusEnum.RECOVERED.value]:
            # Terminal state protection: Do NOT revert captured transaction to failed
            audit = AuditEvent(
                id=str(uuid.uuid4()),
                event_id=f"EVT-{event_id}",
                correlation_id=correlation_id,
                entity_type="TRANSACTION",
                entity_id=existing_tx.id,
                event_type="OUT_OF_ORDER_EVENT_IGNORED",
                actor_type="SYSTEM",
                payload={
                    "event_id": event_id,
                    "event_type": event_type,
                    "reason": "Payment already captured; terminal state protected.",
                },
                policy_version=settings.POLICY_VERSION,
                agent_version=settings.AGENT_VERSION,
                created_at=now,
            )
            db.add(audit)
            db.commit()

            return {
                "status": "IGNORED_OUT_OF_ORDER",
                "message": f"Transaction {external_id} is already in terminal state '{existing_tx.status}'. Failed event ignored.",
                "transaction_id": existing_tx.id,
                "correlation_id": correlation_id,
            }

        # Get or create customer
        customer = db.query(Customer).filter(Customer.external_id == cust_ext_id).first()
        if not customer:
            customer = Customer(
                id=str(uuid.uuid4()),
                external_id=cust_ext_id,
                name=cust_data.get("name", "Merchant Customer"),
                historical_success_rate=cust_data.get("historical_success_rate", 0.75),
                total_transaction_value=cust_data.get("total_transaction_value", 50000.0),
                successful_payment_count=cust_data.get("successful_payment_count", 5),
                failed_payment_count=cust_data.get("failed_payment_count", 1),
                is_opted_out=cust_data.get("is_opted_out", False),
                has_open_dispute=cust_data.get("has_open_dispute", False),
            )
            db.add(customer)
            db.flush()

        tx = existing_tx
        if not tx:
            tx = Transaction(
                id=str(uuid.uuid4()),
                external_id=external_id,
                customer_id=customer.id,
                amount=float(tx_data.get("amount", 1000.0)),
                currency=tx_data.get("currency", "INR"),
                payment_method=tx_data.get("payment_method", "CARD"),
                status=TransactionStatusEnum.FAILED.value,
                created_at=now,
                updated_at=now,
            )
            db.add(tx)
            db.flush()
        else:
            tx.status = TransactionStatusEnum.FAILED.value
            tx.updated_at = now
            db.flush()

        # Classify root cause failure
        norm_type = normalize_razorpay_error(
            err_data.get("code", "BAD_REQUEST_ERROR"),
            err_data.get("description", "Temporary bank decline"),
            err_data.get("step", "payment_authorization"),
            err_data.get("reason", "TEMPORARY_BANK_DECLINE"),
        )

        failure = db.query(PaymentFailure).filter(PaymentFailure.transaction_id == tx.id).first()
        if not failure:
            failure = PaymentFailure(
                id=str(uuid.uuid4()),
                transaction_id=tx.id,
                error_code=err_data.get("code", "BAD_REQUEST_ERROR"),
                error_description=err_data.get("description", "Temporary decline"),
                error_source=err_data.get("source", "gateway"),
                error_step=err_data.get("step", "payment_authorization"),
                error_reason=err_data.get("reason", norm_type),
                normalized_failure_type=norm_type,
                occurred_at=now,
            )
            db.add(failure)
            db.flush()

        # Create or update RecoveryCase
        existing_case = db.query(RecoveryCase).filter(RecoveryCase.transaction_id == tx.id).first()
        if not existing_case:
            base_prob = ml_model.predict_recovery_probability(
                amount=tx.amount,
                payment_method=tx.payment_method,
                failure_type=norm_type,
                customer_success_rate=customer.historical_success_rate,
                customer_success_count=customer.successful_payment_count,
                customer_failed_count=customer.failed_payment_count,
            )
            expected_rec, p_score = ml_model.calculate_priority_score(
                tx.amount, base_prob, customer.historical_success_rate
            )

            case_status = TransactionStatusEnum.RECOVERY_ELIGIBLE.value
            if customer.is_opted_out or customer.has_open_dispute or norm_type == FailureTypeEnum.INVALID_DETAILS.value:
                case_status = TransactionStatusEnum.STOPPED.value

            rec_case = RecoveryCase(
                id=str(uuid.uuid4()),
                transaction_id=tx.id,
                revenue_at_risk=tx.amount,
                recovery_probability=base_prob,
                expected_recovery=expected_rec,
                priority_score=p_score,
                status=case_status,
                retry_count=0,
                message_count=0,
                created_at=now,
                updated_at=now,
            )
            db.add(rec_case)
            db.flush()

            # Record Ingestion Audit Event
            audit = AuditEvent(
                id=str(uuid.uuid4()),
                event_id=f"EVT-{event_id}",
                correlation_id=correlation_id,
                entity_type="RECOVERY_CASE",
                entity_id=rec_case.id,
                event_type="REVENUE_RISK_DETECTED",
                actor_type="SYSTEM",
                payload={
                    "event_id": event_id,
                    "event_type": event_type,
                    "transaction_id": tx.id,
                    "external_id": external_id,
                    "amount": tx.amount,
                    "failure_type": norm_type,
                    "recovery_probability": base_prob,
                    "expected_recovery": expected_rec,
                },
                policy_version=settings.POLICY_VERSION,
                agent_version=settings.AGENT_VERSION,
                created_at=now,
            )
            db.add(audit)
            db.commit()

            return {
                "status": "RECOVERY_CASE_CREATED",
                "case_id": rec_case.id,
                "transaction_id": tx.id,
                "correlation_id": correlation_id,
            }

    db.commit()
    return {
        "status": "EVENT_PROCESSED",
        "event_id": event_id,
        "correlation_id": correlation_id,
    }
