"""Changelog entries for NetBox users.

NetBox does not change-log ``users.User`` (the model has no ``ChangeLoggingMixin``), so ``core.ObjectChange``
never contains user changes and the audit would have nothing to show. This module records them in the same
table, in the same format NetBox uses for the other object types (pre / post change snapshot, user, request ID),
so the rest of the plugin (watched fields, severities, reports, e-mails) treats users like any other object type.

Passwords and ``last_login`` are never stored: a password hash would leak into the changelog, and ``last_login``
changes on every login. Saves that change nothing else (e.g. a login, or a password change) leave no record.
If a future NetBox change-logs users itself, the handlers switch themselves off to avoid duplicates.
"""

from __future__ import annotations

import logging
import threading
import uuid

from django.db import transaction
from django.db.models.signals import m2m_changed, post_save, pre_delete, pre_save

logger = logging.getLogger(__name__)

USER_TYPE = "users.user"
EXCLUDED_FIELDS = ("password", "last_login", "user_permissions")
M2M_ACTIONS = ("post_add", "post_remove", "post_clear")
NO_REQUEST_USER = "(no web request)"  # shell, management commands: NetBox needs a user name
UID = "netbox_self_audit.userlog"


def _user_model():
    from users.models import User

    return User


def _active() -> bool:
    return not hasattr(_user_model(), "to_objectchange")


def snapshot(user) -> dict:
    """Changelog-style snapshot of a user (NetBox's own serializer, without secrets)."""
    from utilities.serialization import serialize_object

    return serialize_object(user, exclude=EXCLUDED_FIELDS)


def _stored_snapshot(pk):
    user = _user_model().objects.filter(pk=pk).first()
    return snapshot(user) if user is not None else None


def _request():
    from netbox.context import current_request

    return current_request.get()


def _write(user, action: str, prechange, postchange) -> None:
    """Create an ObjectChange, or merge into the one this request already made for the same user."""
    from django.contrib.contenttypes.models import ContentType

    from core.choices import ObjectChangeActionChoices
    from core.models import ObjectChange

    request = _request()
    object_type = ContentType.objects.get_for_model(user)
    try:
        with transaction.atomic():
            if request is not None and action == ObjectChangeActionChoices.ACTION_UPDATE:
                previous = ObjectChange.objects.filter(
                    changed_object_type=object_type, changed_object_id=user.pk, request_id=request.id,
                    action__in=(ObjectChangeActionChoices.ACTION_CREATE, ObjectChangeActionChoices.ACTION_UPDATE),
                ).order_by("-time", "-pk").first()
                if previous is not None:
                    previous.postchange_data = postchange
                    previous.save(update_fields=["postchange_data"])
                    return
            actor = getattr(request, "user", None)
            if actor is not None and not getattr(actor, "is_authenticated", False):
                actor = None
            ObjectChange.objects.create(
                user=actor,
                user_name=actor.get_username() if actor is not None else NO_REQUEST_USER,
                request_id=request.id if request is not None else uuid.uuid4(),
                action=action,
                changed_object_type=object_type,
                changed_object_id=user.pk,
                object_repr=str(user)[:200],
                prechange_data=prechange,
                postchange_data=postchange,
            )
    except Exception:  # auditing must never block saving a user (e.g. no table yet during the first migration)
        logger.exception("NetBoxSelf Audit: could not record the change of user %s", user.pk)


def _record_update(user, prechange) -> None:
    from core.choices import ObjectChangeActionChoices

    postchange = snapshot(user)
    if prechange == postchange:
        return
    _write(user, ObjectChangeActionChoices.ACTION_UPDATE, prechange, postchange)


def on_pre_save(sender, instance, raw=False, **kwargs):
    if raw or not _active():
        return
    instance._self_audit_prechange = _stored_snapshot(instance.pk) if instance.pk else None


def on_post_save(sender, instance, created=False, raw=False, **kwargs):
    if raw or not _active():
        return
    from core.choices import ObjectChangeActionChoices

    if created:
        # Groups and permissions are assigned after the save (m2m_changed), which merges into this entry.
        _write(instance, ObjectChangeActionChoices.ACTION_CREATE, None, snapshot(instance))
        return
    prechange = getattr(instance, "_self_audit_prechange", None)
    if prechange is not None:
        _record_update(instance, prechange)


def _m2m_users(instance, reverse, model, pk_set):
    """Users whose group / permission assignment a many-to-many signal changes."""
    User = _user_model()
    if not reverse:
        return [instance] if isinstance(instance, User) else []
    if model is not User:
        return []
    if pk_set is None:  # clear() on the group / permission side: every user currently assigned
        return list(instance.users.all())
    return list(User.objects.filter(pk__in=pk_set))


def on_m2m_pre(sender, instance, action, reverse, model, pk_set, **kwargs):
    """The post_* signals cannot tell what the state was, so remember it before the change."""
    if action not in ("pre_add", "pre_remove", "pre_clear") or not _active():
        return
    for user in _m2m_users(instance, reverse, model, pk_set):
        _BEFORE.before.setdefault(user.pk, _stored_snapshot(user.pk))


def on_m2m_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    if action not in M2M_ACTIONS or not _active():
        return
    from core.choices import ObjectChangeActionChoices

    if action == "post_clear":
        pks = list(_BEFORE.before)
    else:
        pks = [user.pk for user in _m2m_users(instance, reverse, model, pk_set)]
    for pk in pks:
        before = _BEFORE.before.pop(pk, None)
        user = _user_model().objects.filter(pk=pk).first()
        if before is None or user is None:
            continue
        after = snapshot(user)
        if before != after:
            _write(user, ObjectChangeActionChoices.ACTION_UPDATE, before, after)


class _State(threading.local):
    def __init__(self):
        self.before: dict = {}


_BEFORE = _State()


def on_pre_delete(sender, instance, **kwargs):
    if not _active():
        return
    from core.choices import ObjectChangeActionChoices

    _write(instance, ObjectChangeActionChoices.ACTION_DELETE, snapshot(instance), None)


def connect() -> None:
    User = _user_model()
    pre_save.connect(on_pre_save, sender=User, dispatch_uid=f"{UID}.pre_save")
    post_save.connect(on_post_save, sender=User, dispatch_uid=f"{UID}.post_save")
    pre_delete.connect(on_pre_delete, sender=User, dispatch_uid=f"{UID}.pre_delete")
    for field in ("groups", "object_permissions"):
        through = getattr(User, field).through
        m2m_changed.connect(on_m2m_pre, sender=through, dispatch_uid=f"{UID}.m2m_pre.{field}")
        m2m_changed.connect(on_m2m_changed, sender=through, dispatch_uid=f"{UID}.m2m.{field}")
