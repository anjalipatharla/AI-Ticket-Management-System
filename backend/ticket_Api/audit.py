from .models import AuditLog


def log_audit_event(
    request,
    action,
    entity_type,
    entity_id,
    description="",
    metadata=None
):
    actor = request.user if request.user.is_authenticated else None

    ip_address = request.META.get("REMOTE_ADDR")

    AuditLog.objects.create(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        description=description,
        ip_address=ip_address,
        metadata=metadata or {}
    )
