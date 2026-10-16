"""User auditing: NetBox does not change-log users, so the plugin records them (userlog.py)."""

import uuid
from types import SimpleNamespace

from django.test import TestCase

from core.models import ObjectChange
from netbox.context import current_request
from netbox_self_audit import rules, userlog
from netbox_self_audit.i18n import LANGUAGES, MESSAGES
from netbox_self_audit.models import SelfAuditRule, SelfAuditSettings
from users.models import Group, User

KEY = "users.user"


class RequestMixin:
    def start_request(self, actor):
        self.request = SimpleNamespace(id=uuid.uuid4(), user=actor)
        token = current_request.set(self.request)
        self.addCleanup(current_request.reset, token)

    def changes(self, **filters):
        return ObjectChange.objects.filter(changed_object_type__app_label="users", changed_object_type__model="user", **filters).order_by("pk")


class WatchableTests(TestCase):
    def test_user_type_is_offered_but_other_users_models_are_not(self):
        keys = {key for _app, items in rules.watchable_types() for key, _label in items}
        self.assertIn(KEY, keys)
        self.assertFalse({"users.token", "users.group", "users.objectpermission", "users.userconfig"} & keys)

    def test_user_fields(self):
        names = {name for name, _label, _kind in rules.discover_fields(KEY)}
        self.assertTrue({"username", "first_name", "last_name", "email", "is_active", "is_superuser", "groups", "object_permissions"} <= names)
        self.assertFalse({"password", "last_login", "user_permissions"} & names)

    def test_other_types_still_listed(self):
        keys = {key for _app, items in rules.watchable_types() for key, _label in items}
        self.assertTrue({"dcim.device", "ipam.prefix", "tenancy.tenant"} <= keys)

    def test_translations_complete(self):
        for key in ("self.users_hint",):
            self.assertTrue(all(MESSAGES[key].get(code) for code, _name in LANGUAGES), key)


class UserLogTests(RequestMixin, TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="x", is_superuser=True)
        self.start_request(self.admin)

    def test_create_records_snapshot_without_secrets(self):
        user = User.objects.create_user(username="alice", password="secret", email="a@example.com")
        change = self.changes(changed_object_id=user.pk).get()
        self.assertEqual(change.action, "create")
        self.assertEqual(change.user, self.admin)
        self.assertEqual(change.postchange_data["username"], "alice")
        for secret in userlog.EXCLUDED_FIELDS:
            self.assertNotIn(secret, change.postchange_data)

    def test_update_records_old_and_new(self):
        user = User.objects.create_user(username="bob")
        self.start_request(self.admin)  # new request: no merging with the create
        user.is_superuser = True
        user.email = "b@example.com"
        user.save()
        change = self.changes(changed_object_id=user.pk, action="update").get()
        self.assertFalse(change.prechange_data["is_superuser"])
        self.assertTrue(change.postchange_data["is_superuser"])
        self.assertEqual(change.postchange_data["email"], "b@example.com")

    def test_login_and_password_change_leave_no_record(self):
        user = User.objects.create_user(username="carol")
        self.start_request(self.admin)
        from django.utils import timezone
        user.last_login = timezone.now()
        user.save()
        user.set_password("new-password")
        user.save()
        self.assertFalse(self.changes(changed_object_id=user.pk, action="update").exists())

    def test_groups_are_recorded_and_merged_into_the_create(self):
        group = Group.objects.create(name="ops")
        user = User.objects.create_user(username="dave")
        user.groups.add(group)
        change = self.changes(changed_object_id=user.pk).get()  # still one entry for the request
        self.assertEqual(change.action, "create")
        self.assertEqual(change.postchange_data["groups"], [group.pk])

    def test_groups_change_in_a_later_request_is_an_update(self):
        group = Group.objects.create(name="ops")
        user = User.objects.create_user(username="erin")
        self.start_request(self.admin)
        user.groups.add(group)
        change = self.changes(changed_object_id=user.pk, action="update").get()
        self.assertEqual(change.prechange_data["groups"], [])
        self.assertEqual(change.postchange_data["groups"], [group.pk])
        self.start_request(self.admin)
        group.users.remove(user)  # reverse direction
        last = self.changes(changed_object_id=user.pk, action="update").last()
        self.assertEqual(last.postchange_data["groups"], [])
        self.start_request(self.admin)
        user.groups.add(group)
        group.users.clear()
        self.assertEqual(self.changes(changed_object_id=user.pk, action="update").last().postchange_data["groups"], [])

    def test_delete_is_recorded(self):
        user = User.objects.create_user(username="frank")
        pk = user.pk
        self.start_request(self.admin)
        user.delete()
        change = self.changes(changed_object_id=pk, action="delete").get()
        self.assertEqual(change.prechange_data["username"], "frank")
        self.assertEqual(change.object_repr, "frank")

    def test_no_request_still_records_without_user(self):
        current_request.set(None)
        user = User.objects.create_user(username="gina")
        change = self.changes(changed_object_id=user.pk).get()
        self.assertIsNone(change.user)


class UserAuditTests(RequestMixin, TestCase):
    """The recorded changes flow through the normal audit (rules -> entries)."""

    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="x", is_superuser=True)
        self.settings = SelfAuditSettings.load()
        for field in (rules.CREATE, rules.DELETE, "is_superuser", "email", "groups"):
            SelfAuditRule.objects.create(object_type=KEY, field=field, severity="high", enabled=True)
        self.start_request(self.admin)

    def test_admin_flag_email_group_create_delete(self):
        group = Group.objects.create(name="ops")
        user = User.objects.create_user(username="heidi")
        self.start_request(self.admin)
        user.is_superuser = True
        user.email = "h@example.com"
        user.save()
        user.groups.add(group)
        pk = user.pk
        self.start_request(self.admin)
        user.delete()
        entries = [e for e in rules.collect(self.settings, None, None) if e["object_type_key"] == KEY and e["object_id"] == pk]
        found = {(e["action"], e["field"]) for e in entries}
        self.assertEqual(found, {("create", rules.CREATE), ("update", "is_superuser"), ("update", "email"), ("update", "groups"), ("delete", rules.DELETE)})
        flag = next(e for e in entries if e["field"] == "is_superuser")
        self.assertEqual((flag["old"], flag["new"], flag["user"]), ("✗", "✓", "admin"))
        groups = next(e for e in entries if e["field"] == "groups")
        self.assertEqual(groups["added"], ["ops"])


class UserPagesTests(RequestMixin, TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="root", password="x", email="r@example.com")
        self.client.force_login(self.admin)

    def test_rules_page_for_users_saves_and_audit_page_renders(self):
        from django.urls import reverse

        response = self.client.get(reverse("plugins:netbox_self_audit:rules"), {"type": KEY})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="watch__is_superuser"')
        self.assertNotContains(response, 'name="watch__password"')
        self.assertContains(response, "NetBox does not log changes of users itself")
        response = self.client.get(reverse("plugins:netbox_self_audit:audit"), {"period": "all", "type": KEY})
        self.assertEqual(response.status_code, 200)

    def test_netbox_changelog_pages_handle_user_entries(self):
        from django.urls import reverse

        user = User.objects.create_user(username="ivan")
        change = ObjectChange.objects.filter(changed_object_id=user.pk, changed_object_type__model="user").first()
        self.assertIsNotNone(change)
        self.assertEqual(self.client.get(reverse("core:objectchange_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:objectchange", args=[change.pk])).status_code, 200)
