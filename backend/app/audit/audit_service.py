from sqlalchemy.orm import Session
from backend.app.models.audit_event import AuditEvent
from backend.app.schemas.audit import AuditEventResponse, ActivityFeedItem

from backend.app.models.recovery_action import RecoveryAction

class AuditService:
    """
    Audit and activity feed service.
    Generates persisted activity feed items and retrieves case audit history.
    """

    def get_case_audit_trail(self, db: Session, case_id: str) -> list[AuditEventResponse]:
        # Retrieve all action IDs for this case
        action_ids = [a[0] for a in db.query(RecoveryAction.id).filter(RecoveryAction.recovery_case_id == case_id).all()]
        all_ids = [case_id] + action_ids

        events = (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_id.in_(all_ids))
            .order_by(AuditEvent.created_at.desc())
            .all()
        )
        return [AuditEventResponse.from_orm(e) for e in events]

    def get_activity_feed(self, db: Session, limit: int = 30) -> list[ActivityFeedItem]:
        events = (
            db.query(AuditEvent)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
            .all()
        )

        feed = []
        for e in events:
            p = e.payload or {}
            event_type = e.event_type
            title = ""
            desc = ""
            amt = None
            status = "INFO"

            if event_type == "ACTION_EXECUTED":
                result = p.get("result", "UNKNOWN")
                amt = p.get("recovered_amount", 0.0)
                action_type = p.get("action_type", "ACTION")
                if result == "SUCCESS":
                    title = f"₹{amt:,.2f} Recovered"
                    desc = f"Action {action_type} succeeded. Payment captured."
                    status = "SUCCESS"
                elif result == "SKIPPED":
                    title = "Recovery Stopped"
                    desc = f"Action {action_type} completed with safe stop."
                    status = "WARNING"
                else:
                    title = "Retry Attempted"
                    desc = f"Action {action_type} failed. Moving to next recovery cycle."
                    status = "FAILURE"

            elif event_type == "GUARDRAIL_REJECTED":
                title = "Guardrail Blocked Action"
                desc = p.get("reason", "Policy violation prevented execution")
                status = "WARNING"

            elif event_type == "REVENUE_RISK_DETECTED":
                amt = p.get("amount")
                ft = p.get("failure_type", "DECLINE")
                title = f"₹{amt:,.2f} Revenue At Risk" if amt else "Revenue Risk Detected"
                desc = f"Failed payment detected: {ft}. Risk score & recovery probability generated."
                status = "INFO"

            else:
                title = event_type.replace("_", " ").title()
                desc = f"Audit logged by {e.actor_type}"
                status = "INFO"

            feed.append(ActivityFeedItem(
                id=e.id,
                event_type=event_type,
                title=title,
                description=desc,
                amount=amt,
                status=status,
                timestamp=e.created_at,
                correlation_id=e.correlation_id,
            ))

        return feed

audit_service = AuditService()
