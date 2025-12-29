from __future__ import annotations

import datetime
import logging

import post_office.mail
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.backends import FreeIPAUser
from core.models import Membership, MembershipLog, MembershipRequest, MembershipType, OrganizationSponsorship

logger = logging.getLogger(__name__)


def previous_expires_at_for_extension(*, username: str, membership_type: MembershipType) -> datetime.datetime | None:
    """Return the expiry for an active membership if it can be extended.

    Only extend active memberships; if the current row is missing or already
    expired, return None so approval starts a new term.
    """

    logger.debug(
        "previous_expires_at_for_extension: start username=%r membership_type=%s",
        username,
        membership_type.code,
    )

    current = Membership.objects.filter(target_username=username, membership_type=membership_type).first()
    if current is None or current.expires_at is None:
        logger.debug(
            "previous_expires_at_for_extension: no current membership (or expires_at missing) username=%r membership_type=%s",
            username,
            membership_type.code,
        )
        return None

    now = timezone.now()
    if current.expires_at <= now:
        logger.debug(
            "previous_expires_at_for_extension: expired username=%r membership_type=%s expires_at=%s now=%s",
            username,
            membership_type.code,
            current.expires_at,
            now,
        )
        return None

    logger.debug(
        "previous_expires_at_for_extension: extendable username=%r membership_type=%s expires_at=%s now=%s",
        username,
        membership_type.code,
        current.expires_at,
        now,
    )
    return current.expires_at


def previous_expires_at_for_org_extension(*, organization_id: int) -> datetime.datetime | None:
    logger.debug(
        "previous_expires_at_for_org_extension: start organization_id=%s",
        organization_id,
    )

    current = OrganizationSponsorship.objects.filter(organization_id=organization_id).first()
    if current is None or current.expires_at is None:
        logger.debug(
            "previous_expires_at_for_org_extension: no current sponsorship (or expires_at missing) organization_id=%s",
            organization_id,
        )
        return None

    now = timezone.now()
    if current.expires_at <= now:
        logger.debug(
            "previous_expires_at_for_org_extension: expired organization_id=%s expires_at=%s now=%s",
            organization_id,
            current.expires_at,
            now,
        )
        return None

    logger.debug(
        "previous_expires_at_for_org_extension: extendable organization_id=%s expires_at=%s now=%s",
        organization_id,
        current.expires_at,
        now,
    )
    return current.expires_at


def record_membership_request_created(
    *,
    membership_request: MembershipRequest,
    actor_username: str,
    send_submitted_email: bool,
) -> None:
    """Record the initial request audit log and optionally email the requester."""

    membership_type = membership_request.membership_type

    logger.debug(
        "record_membership_request_created: start request_id=%s actor=%r membership_type=%s requested_username=%r requested_org_id=%s send_submitted_email=%s",
        membership_request.pk,
        actor_username,
        membership_type.code,
        membership_request.requested_username,
        membership_request.requested_organization_id,
        send_submitted_email,
    )

    if membership_request.requested_username:
        try:
            log = MembershipLog.create_for_request(
                actor_username=actor_username,
                target_username=membership_request.requested_username,
                membership_type=membership_type,
                membership_request=membership_request,
            )
        except Exception:
            logger.exception(
                "record_membership_request_created: failed to create requested log (user) request_id=%s actor=%r target=%r membership_type=%s",
                membership_request.pk,
                actor_username,
                membership_request.requested_username,
                membership_type.code,
            )
            raise

        logger.debug(
            "record_membership_request_created: created requested log log_id=%s request_id=%s target=%r membership_type=%s",
            log.pk,
            membership_request.pk,
            membership_request.requested_username,
            membership_type.code,
        )

        if send_submitted_email:
            logger.debug(
                "record_membership_request_created: sending submitted email request_id=%s target=%r membership_type=%s",
                membership_request.pk,
                membership_request.requested_username,
                membership_type.code,
            )
            try:
                target = FreeIPAUser.get(membership_request.requested_username)
            except Exception:
                logger.exception(
                    "record_membership_request_created: FreeIPAUser.get failed for submitted email request_id=%s target=%r",
                    membership_request.pk,
                    membership_request.requested_username,
                )
                raise

            if target is not None and target.email:
                try:
                    post_office.mail.send(
                        recipients=[target.email],
                        sender=settings.DEFAULT_FROM_EMAIL,
                        template=settings.MEMBERSHIP_REQUEST_SUBMITTED_EMAIL_TEMPLATE_NAME,
                        context={
                            "username": target.username,
                            "membership_type": membership_type.name,
                            "membership_type_code": membership_type.code,
                        },
                    )
                except Exception:
                    logger.exception(
                        "record_membership_request_created: sending submitted email failed request_id=%s target=%r",
                        membership_request.pk,
                        membership_request.requested_username,
                    )
                    raise
            else:
                logger.debug(
                    "record_membership_request_created: submitted email skipped (missing email) request_id=%s target=%r",
                    membership_request.pk,
                    membership_request.requested_username,
                )

        logger.debug(
            "record_membership_request_created: done request_id=%s",
            membership_request.pk,
        )
        return

    # Organization request.
    org = membership_request.requested_organization
    if org is not None:
        try:
            log = MembershipLog.create_for_org_request(
                actor_username=actor_username,
                target_organization=org,
                membership_type=membership_type,
                membership_request=membership_request,
            )
        except Exception:
            logger.exception(
                "record_membership_request_created: failed to create requested log (org) request_id=%s actor=%r org_id=%s membership_type=%s",
                membership_request.pk,
                actor_username,
                org.pk,
                membership_type.code,
            )
            raise

        logger.debug(
            "record_membership_request_created: created requested log (org) log_id=%s request_id=%s org_id=%s membership_type=%s",
            log.pk,
            membership_request.pk,
            org.pk,
            membership_type.code,
        )
        logger.debug(
            "record_membership_request_created: done request_id=%s",
            membership_request.pk,
        )
        return

    # A request can point to a non-existent org via requested_organization_code.
    try:
        log = MembershipLog.objects.create(
            actor_username=actor_username,
            target_username="",
            target_organization=None,
            target_organization_code=membership_request.requested_organization_code,
            target_organization_name=membership_request.requested_organization_name,
            membership_type=membership_type,
            membership_request=membership_request,
            requested_group_cn=membership_type.group_cn,
            action=MembershipLog.Action.requested,
            expires_at=None,
        )
    except Exception:
        logger.exception(
            "record_membership_request_created: failed to create requested log (org code) request_id=%s actor=%r org_code=%r membership_type=%s",
            membership_request.pk,
            actor_username,
            membership_request.requested_organization_code,
            membership_type.code,
        )
        raise

    logger.debug(
        "record_membership_request_created: created requested log (org code) log_id=%s request_id=%s org_code=%r membership_type=%s",
        log.pk,
        membership_request.pk,
        membership_request.requested_organization_code,
        membership_type.code,
    )
    logger.debug(
        "record_membership_request_created: done request_id=%s",
        membership_request.pk,
    )


def approve_membership_request(
    *,
    membership_request: MembershipRequest,
    actor_username: str,
    send_approved_email: bool,
    status_note: str = "",
    decided_at: datetime.datetime | None = None,
) -> MembershipLog:
    """Approve a membership request using the same code path as the UI.

    This function applies FreeIPA side-effects and records the approval log.
    It updates the request status fields and optionally emails the requester.
    """

    membership_type = membership_request.membership_type
    decided = decided_at or timezone.now()

    logger.debug(
        "approve_membership_request: start request_id=%s actor=%r membership_type=%s requested_username=%r requested_org_id=%s decided_at=%s send_approved_email=%s status_note_present=%s",
        membership_request.pk,
        actor_username,
        membership_type.code,
        membership_request.requested_username,
        membership_request.requested_organization_id,
        decided,
        send_approved_email,
        bool(str(status_note or "").strip()),
    )

    if membership_request.requested_username == "":
        org = membership_request.requested_organization
        if org is None:
            logger.debug(
                "approve_membership_request: org not found request_id=%s org_code=%r",
                membership_request.pk,
                membership_request.requested_organization_code,
            )
            raise ValidationError("Organization not found")

        logger.debug(
            "approve_membership_request: approving org request request_id=%s org_id=%s membership_type=%s",
            membership_request.pk,
            org.pk,
            membership_type.code,
        )

        org.membership_level = membership_type
        try:
            org.save(update_fields=["membership_level"])
        except Exception:
            logger.exception(
                "approve_membership_request: failed to save org membership_level request_id=%s org_id=%s",
                membership_request.pk,
                org.pk,
            )
            raise

        try:
            previous_expires_at = previous_expires_at_for_org_extension(organization_id=org.pk)
            log = MembershipLog.create_for_org_approval_at(
                actor_username=actor_username,
                target_organization=org,
                membership_type=membership_type,
                approved_at=decided,
                previous_expires_at=previous_expires_at,
                membership_request=membership_request,
            )
        except Exception:
            logger.exception(
                "approve_membership_request: failed to create org approval log request_id=%s org_id=%s membership_type=%s",
                membership_request.pk,
                org.pk,
                membership_type.code,
            )
            raise

        logger.debug(
            "approve_membership_request: created org approval log log_id=%s request_id=%s org_id=%s membership_type=%s",
            log.pk,
            membership_request.pk,
            org.pk,
            membership_type.code,
        )

        membership_request.status = MembershipRequest.Status.approved
        membership_request.decided_at = decided
        membership_request.decided_by_username = actor_username
        try:
            membership_request.save(update_fields=["status", "decided_at", "decided_by_username"])
        except Exception:
            logger.exception(
                "approve_membership_request: failed to update request status (org) request_id=%s org_id=%s",
                membership_request.pk,
                org.pk,
            )
            raise

        logger.debug(
            "approve_membership_request: done (org) request_id=%s log_id=%s",
            membership_request.pk,
            log.pk,
        )
        return log

    if not membership_type.group_cn:
        logger.debug(
            "approve_membership_request: missing group_cn request_id=%s membership_type=%s",
            membership_request.pk,
            membership_type.code,
        )
        raise ValidationError("This membership type is not linked to a group")

    logger.debug(
        "approve_membership_request: approving user request request_id=%s target=%r group_cn=%r membership_type=%s",
        membership_request.pk,
        membership_request.requested_username,
        membership_type.group_cn,
        membership_type.code,
    )

    try:
        target = FreeIPAUser.get(membership_request.requested_username)
    except Exception:
        logger.exception(
            "approve_membership_request: FreeIPAUser.get failed request_id=%s target=%r",
            membership_request.pk,
            membership_request.requested_username,
        )
        raise
    if target is None:
        logger.debug(
            "approve_membership_request: requested user not found request_id=%s target=%r",
            membership_request.pk,
            membership_request.requested_username,
        )
        raise ValidationError("Unable to load the requested user from FreeIPA")

    logger.debug(
        "approve_membership_request: add_to_group start request_id=%s target=%r group_cn=%r",
        membership_request.pk,
        target.username,
        membership_type.group_cn,
    )
    try:
        target.add_to_group(group_name=membership_type.group_cn)
    except Exception:
        logger.exception(
            "approve_membership_request: add_to_group failed request_id=%s target=%r group_cn=%r",
            membership_request.pk,
            target.username,
            membership_type.group_cn,
        )
        raise

    logger.debug(
        "approve_membership_request: add_to_group success request_id=%s target=%r group_cn=%r",
        membership_request.pk,
        target.username,
        membership_type.group_cn,
    )

    note = str(status_note or "").strip()
    if note:
        # Note updates should only happen if the group membership succeeded.
        logger.debug(
            "approve_membership_request: set_status_note start request_id=%s target=%r",
            membership_request.pk,
            target.username,
        )
        try:
            FreeIPAUser.set_status_note(target.username, note)
        except Exception:
            logger.exception(
                "approve_membership_request: set_status_note failed request_id=%s target=%r",
                membership_request.pk,
                target.username,
            )
            raise
        logger.debug(
            "approve_membership_request: set_status_note success request_id=%s target=%r",
            membership_request.pk,
            target.username,
        )
    else:
        logger.debug(
            "approve_membership_request: no status note request_id=%s",
            membership_request.pk,
        )

    try:
        previous_expires_at = previous_expires_at_for_extension(
            username=membership_request.requested_username,
            membership_type=membership_type,
        )
        log = MembershipLog.create_for_approval_at(
            actor_username=actor_username,
            target_username=membership_request.requested_username,
            membership_type=membership_type,
            approved_at=decided,
            previous_expires_at=previous_expires_at,
            membership_request=membership_request,
        )
    except Exception:
        logger.exception(
            "approve_membership_request: failed to create approval log request_id=%s target=%r membership_type=%s",
            membership_request.pk,
            membership_request.requested_username,
            membership_type.code,
        )
        raise

    logger.debug(
        "approve_membership_request: created approval log log_id=%s request_id=%s target=%r membership_type=%s",
        log.pk,
        membership_request.pk,
        membership_request.requested_username,
        membership_type.code,
    )

    membership_request.status = MembershipRequest.Status.approved
    membership_request.decided_at = decided
    membership_request.decided_by_username = actor_username
    try:
        membership_request.save(update_fields=["status", "decided_at", "decided_by_username"])
    except Exception:
        logger.exception(
            "approve_membership_request: failed to update request status (user) request_id=%s target=%r",
            membership_request.pk,
            membership_request.requested_username,
        )
        raise

    if send_approved_email and target.email:
        logger.debug(
            "approve_membership_request: sending approved email request_id=%s target=%r membership_type=%s",
            membership_request.pk,
            target.username,
            membership_type.code,
        )
        try:
            post_office.mail.send(
                recipients=[target.email],
                sender=settings.DEFAULT_FROM_EMAIL,
                template=settings.MEMBERSHIP_REQUEST_APPROVED_EMAIL_TEMPLATE_NAME,
                context={
                    "username": target.username,
                    "membership_type": membership_type.name,
                    "membership_type_code": membership_type.code,
                    "group_cn": membership_type.group_cn,
                },
            )
        except Exception:
            logger.exception(
                "approve_membership_request: sending approved email failed request_id=%s target=%r",
                membership_request.pk,
                target.username,
            )
            raise
    else:
        logger.debug(
            "approve_membership_request: approved email skipped request_id=%s send_approved_email=%s has_email=%s",
            membership_request.pk,
            send_approved_email,
            bool(target.email),
        )

    logger.debug(
        "approve_membership_request: done (user) request_id=%s log_id=%s",
        membership_request.pk,
        log.pk,
    )

    return log
