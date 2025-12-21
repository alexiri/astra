import logging
from functools import lru_cache
import threading
from collections.abc import Callable
from typing import TypeVar

from django.conf import settings
from django.contrib.auth.backends import BaseBackend
from django.core.cache import cache
from django.utils.crypto import salted_hmac
from python_freeipa import ClientMeta, exceptions

logger = logging.getLogger(__name__)

_service_client_local = threading.local()

_T = TypeVar("_T")


class FreeIPAOperationFailed(RuntimeError):
    """Raised when FreeIPA returns a structured failure without raising."""


def _compact_repr(value: object, *, limit: int = 400) -> str:
    rendered = repr(value)
    if len(rendered) > limit:
        return f"{rendered[:limit]}…"
    return rendered


def _has_truthy_failure(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        # A non-empty dict usually indicates at least one member entry failed.
        return len(value) > 0
    return bool(value)


def _raise_if_freeipa_failed(result: object, *, action: str, subject: str) -> None:
    if not isinstance(result, dict):
        return

    failed = result.get("failed")
    if not failed:
        return

    # FreeIPA's group_{add,remove}_member often returns a `failed` skeleton even
    # on success, e.g. {'member': {'user': [], 'group': [], ...}}. Only treat it
    # as an error when any member bucket is non-empty.
    if action in {"group_add_member", "group_remove_member"} and isinstance(failed, dict):
        member = failed.get("member")
        if isinstance(member, dict):
            buckets = (
                member.get("user"),
                member.get("group"),
                member.get("service"),
                member.get("idoverrideuser"),
            )
            if not any(_has_truthy_failure(b) for b in buckets):
                return

    items: list[str] = []

    def walk(prefix: list[str], value: object) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                walk([*prefix, str(k)], v)
            return
        if isinstance(value, list):
            for v in value:
                walk(prefix, v)
            return
        if value is None:
            return
        key = "/".join(prefix) if prefix else "failed"
        items.append(f"{key}: {value}")

    walk([], failed)
    details = "; ".join(items[:6])
    if len(items) > 6:
        details = f"{details}; …"
    if not details:
        details = f"failed={_compact_repr(failed)}"
    raise FreeIPAOperationFailed(f"FreeIPA {action} failed ({subject}): {details}")


def _get_freeipa_client(username: str, password: str) -> ClientMeta:
    """Create and login a FreeIPA client.

    Centralize client construction + login so we don't duplicate host/SSL/login
    wiring across user/group helpers and the auth backend.
    """

    client = ClientMeta(host=settings.FREEIPA_HOST, verify_ssl=settings.FREEIPA_VERIFY_SSL)
    client.login(username, password)
    return client


def _get_freeipa_service_client_cached() -> ClientMeta:
    """Return a cached service-account client for the current thread.

    FreeIPA operations often happen in bursts during a single request.
    Reusing the service client's logged-in session avoids repeated logins.
    The per-request middleware clears this cache at request boundaries.
    """

    client = getattr(_service_client_local, "client", None)
    if client is None:
        client = _get_freeipa_client(settings.FREEIPA_SERVICE_USER, settings.FREEIPA_SERVICE_PASSWORD)
        _service_client_local.client = client
    return client


def clear_freeipa_service_client_cache() -> None:
    """Clear any cached service client for the current thread."""

    if hasattr(_service_client_local, "client"):
        delattr(_service_client_local, "client")


def _with_freeipa_service_client_retry(get_client: Callable[[], ClientMeta], fn: Callable[[ClientMeta], _T]) -> _T:
    """Run a service-account request, retrying once if the session expired.

    python-freeipa raises Unauthorized on HTTP 401, which is what we see when
    the FreeIPA session cookie expires or a connection is reset.
    """

    client = get_client()
    try:
        return fn(client)
    except exceptions.Unauthorized:
        clear_freeipa_service_client_cache()
        client = get_client()
        return fn(client)


def _user_cache_key(username: str) -> str:
    # Keep legacy key format to avoid surprises.
    return f'freeipa_user_{username}'


def _group_cache_key(cn: str) -> str:
    return f'freeipa_group_{cn}'


def _users_list_cache_key() -> str:
    return 'freeipa_users_all'


def _groups_list_cache_key() -> str:
    return 'freeipa_groups_all'


def _invalidate_users_list_cache() -> None:
    cache.delete(_users_list_cache_key())


def _invalidate_groups_list_cache() -> None:
    cache.delete(_groups_list_cache_key())


def _invalidate_user_cache(username: str) -> None:
    cache.delete(_user_cache_key(username))


def _invalidate_group_cache(cn: str) -> None:
    cache.delete(_group_cache_key(cn))


@lru_cache(maxsize=4096)
def _session_user_id_for_username(username: str) -> int:
    """Return a stable integer id for storing in Django's session.

    We keep Django's default auth user model (integer PK). To avoid the session
    loader failing on non-integer values (e.g. 'admin'), we store a deterministic
    integer derived from the username and SECRET_KEY.

    This does not imply any DB persistence; it is only a session identifier.
    """

    digest = salted_hmac('freeipa-session', username, secret=settings.SECRET_KEY).digest()
    # Use a positive 63-bit integer.
    return int.from_bytes(digest[:8], 'big') & 0x7FFFFFFFFFFFFFFF


class _FreeIPAPK:
    attname = 'username'
    name = 'username'

    def value_to_string(self, obj):
        username = getattr(obj, 'username', None)
        if username:
            return str(_session_user_id_for_username(username))
        return str(getattr(obj, 'pk', ''))


class _FreeIPAMeta:
    pk = _FreeIPAPK()

class FreeIPAManager:
    """
    A mock manager to mimic Django's RelatedManager.
    """
    def __init__(self, iterable):
        self._iterable = iterable

    def all(self):
        return self._iterable

    def count(self):
        return len(self._iterable)

    def __iter__(self):
        return iter(self._iterable)

class FreeIPAUser:
    """
    A non-persistent user object backed by FreeIPA.
    """
    def __init__(self, username, user_data=None):
        self.username = username
        self.backend = 'core.backends.FreeIPAAuthBackend'
        self._user_data = user_data or {}
        self.is_authenticated = True
        self.is_anonymous = False
        # Django's auth/session machinery expects model-like metadata.
        self._meta = _FreeIPAMeta()

        # Django may set this via the update_last_login signal. We intentionally
        # do not persist it anywhere (no DB, no FreeIPA, no cache).
        self.last_login = None

        def _first(key, default=None):
            value = self._user_data.get(key, default)
            if isinstance(value, list):
                return value[0] if value else default
            return value

        # Map FreeIPA attributes to Django attributes
        self.first_name = _first('givenname') or ""
        self.last_name = _first('sn') or ""
        # Some upstream template tags (e.g. django-avatar gravatar provider)
        # assume the email attribute is always a string and call .encode().
        # FreeIPA users may not have a mail attribute, so normalize to "".
        self.email = _first('mail') or ""

        # Determine status based on FreeIPA data
        # nsaccountlock: True means locked (inactive)
        nsaccountlock = self._user_data.get('nsaccountlock', False)
        if isinstance(nsaccountlock, list):
            nsaccountlock = nsaccountlock[0] if nsaccountlock else False
        self.is_active = not bool(nsaccountlock)

        # Permissions/Groups logic
        self.groups_list = self._user_data.get('memberof_group', [])
        if isinstance(self.groups_list, str):
            self.groups_list = [self.groups_list]

        # Simple mapping for staff/superuser based on groups
        # Configure these group names in settings
        admin_group = settings.FREEIPA_ADMIN_GROUP
        self.is_staff = admin_group in self.groups_list
        self.is_superuser = admin_group in self.groups_list

    @property
    def groups(self):
        """
        Returns a manager-like object containing FreeIPAGroup objects.
        Note: If this user object was created lazily (without data), this list might be empty.
        """
        return FreeIPAManager([FreeIPAGroup(cn) for cn in self.groups_list])

    @property
    def user_permissions(self):
        """
        Returns an empty manager as we use groups for permissions.
        """
        return FreeIPAManager([])

    @property
    def pk(self):
        return _session_user_id_for_username(self.username)

    @property
    def id(self):
        return _session_user_id_for_username(self.username)

    def get_username(self):
        return self.username

    def get_full_name(self):
        full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return full_name or self.username

    def get_short_name(self):
        return self.first_name or self.username

    def get_session_auth_hash(self):
        # Used by Django to invalidate sessions on credential changes.
        return salted_hmac('freeipa-user', self.username, secret=settings.SECRET_KEY).hexdigest()

    @classmethod
    def get_client(cls) -> ClientMeta:
        """Return a FreeIPA client authenticated as the service account."""

        return _get_freeipa_service_client_cached()

    @classmethod
    def all(cls):
        """
        Returns a list of all users from FreeIPA.
        """
        def _fetch_users() -> list[dict[str, object]]:
            # FreeIPA server/client may default to returning only 100 entries.
            # Request an unlimited result set where supported.
            result = _with_freeipa_service_client_retry(
                cls.get_client,
                lambda client: client.user_find(o_all=True, o_no_members=False, o_sizelimit=0, o_timelimit=0),
            )
            return result.get('result', [])

        try:
            users = cache.get_or_set(_users_list_cache_key(), _fetch_users) or []
            # Cache may legitimately contain an empty list; treat that as a hit.
            return [cls(u['uid'][0], u) for u in users]
        except Exception:
            # On failure, avoid poisoning the cache with an empty list.
            logger.exception("Failed to list users")
            return []

    @classmethod
    def _fetch_full_user(cls, client: ClientMeta, username: str):
        """Return a single user's full attribute dict.

        Prefer user_show (returns full attribute set including custom schema
        like Fedora's FAS fields). Fallback to user_find if needed.
        """
        def _try(label: str, fn):
            try:
                return fn()
            except exceptions.Unauthorized:
                # Treat as an auth/session issue so callers can retry with a fresh login.
                raise
            except TypeError as e:
                # Signature mismatch across python-freeipa versions.
                logger.debug("FreeIPA call failed (TypeError) label=%s username=%s error=%s", label, username, e)
                return None
            except exceptions.FreeIPAError as e:
                # FreeIPA returned an API-level error.
                logger.debug("FreeIPA call failed label=%s username=%s error=%s", label, username, e)
                return None
            except Exception:
                logger.exception("FreeIPA call failed (unexpected) label=%s username=%s", label, username)
                return None

        # Try common call styles across python-freeipa versions.
        res = _try("user_show(username)", lambda: client.user_show(username, o_all=True, o_no_members=False))
        if res and 'result' in res:
            return res['result']

        res = _try("user_show(a_uid=...)", lambda: client.user_show(a_uid=username, o_all=True, o_no_members=False))
        if res and 'result' in res:
            return res['result']

        # Fallback to a targeted find.
        res = _try("user_find(o_uid=...)", lambda: client.user_find(o_uid=username, o_all=True, o_no_members=False))
        if res and res.get('count', 0) > 0:
            return res['result'][0]
        return None

    @classmethod
    def get(cls, username):
        """
        Fetch a single user by username.
        """
        # Check cache first
        cache_key = _user_cache_key(username)
        cached_data = cache.get(cache_key)

        if cached_data is not None:
            return cls(username, cached_data)

        try:
            user_data = _with_freeipa_service_client_retry(
                cls.get_client,
                lambda client: cls._fetch_full_user(client, username),
            )
            if user_data is not None:
                cache.set(cache_key, user_data)
                return cls(username, user_data)
        except Exception as e:
            logger.exception("Failed to get user username=%s", username)
        return None

    @classmethod
    def create(cls, username, **kwargs):
        """
        Create a new user in FreeIPA.
        kwargs should match FreeIPA user_add arguments (e.g., givenname, sn, mail, password).
        """
        try:
            givenname = kwargs.pop('givenname', None) or kwargs.pop('first_name', None)
            sn = kwargs.pop('sn', None) or kwargs.pop('last_name', None)
            if not givenname or not sn:
                raise ValueError('FreeIPA user creation requires givenname/first_name and sn/last_name')

            cn = kwargs.pop('cn', None) or kwargs.pop('displayname', None)
            if not cn:
                cn = f"{givenname} {sn}".strip() or username

            ipa_kwargs = {}

            mail = kwargs.pop('mail', None) or kwargs.pop('email', None)
            if mail:
                ipa_kwargs['o_mail'] = mail

            password = kwargs.pop('password', None) or kwargs.pop('userpassword', None)
            if password:
                ipa_kwargs['o_userpassword'] = password

            for key, value in kwargs.items():
                if key.startswith(('o_', 'a_')):
                    ipa_kwargs[key] = value
                else:
                    ipa_kwargs[f"o_{key}"] = value

            _with_freeipa_service_client_retry(
                cls.get_client,
                lambda client: client.user_add(username, givenname, sn, cn, **ipa_kwargs),
            )
            # New user should appear in lists; invalidate list cache and warm this user's cache.
            _invalidate_users_list_cache()
            return cls.get(username)
        except Exception as e:
            logger.exception("Failed to create user username=%s", username)
            raise

    def save(self, *args, **kwargs):
        """Persist changes.

        - If called by Django's update_last_login signal (update_fields includes
          only 'last_login'), do nothing (we don't persist last_login).
        - Otherwise, update selected fields in FreeIPA.
        """

        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields_set = set(update_fields)
            if update_fields_set == {'last_login'}:
                return

        updates = {}
        if self.first_name:
            updates['o_givenname'] = self.first_name
        if self.last_name:
            updates['o_sn'] = self.last_name
        if self.email:
            updates['o_mail'] = self.email

        # Persist activation state by toggling FreeIPA's nsaccountlock.
        # Locked account => nsaccountlock=True => is_active=False.
        if hasattr(self, 'is_active'):
            updates['o_nsaccountlock'] = (not bool(self.is_active))

        cn = f"{self.first_name or ''} {self.last_name or ''}".strip()
        if cn:
            updates['o_cn'] = cn

        try:
            if updates:
                try:
                    _with_freeipa_service_client_retry(
                        self.get_client,
                        lambda client: client.user_mod(self.username, **updates),
                    )
                except exceptions.BadRequest as e:
                    # FreeIPA returns BadRequest("no modifications to be performed") when
                    # user_mod is called with values identical to the current state.
                    if "no modifications to be performed" not in str(e).lower():
                        raise
                    logger.info("FreeIPA user_mod was a no-op username=%s", self.username)

            # Invalidate and refresh cache entries.
            _invalidate_user_cache(self.username)
            _invalidate_users_list_cache()
            # Warm fresh data for subsequent reads.
            FreeIPAUser.get(self.username)
        except Exception as e:
            logger.exception("Failed to update user username=%s: %s", self.username, e)
            raise

    def delete(self):
        """
        Delete the user from FreeIPA.
        """
        try:
            _with_freeipa_service_client_retry(
                self.get_client,
                lambda client: client.user_del(self.username),
            )
            _invalidate_user_cache(self.username)
            _invalidate_users_list_cache()
        except Exception as e:
            logger.exception("Failed to delete user username=%s", self.username)
            raise


    def get_all_permissions(self, obj=None):
        return self.get_group_permissions(obj)

    def has_perm(self, perm, obj=None):
        # Check if user has permission
        if self.is_active and self.is_superuser:
            return True
        return perm in self.get_all_permissions(obj)

    def has_module_perms(self, app_label):
        if self.is_active and self.is_superuser:
            return True
        return any(perm.startswith(f"{app_label}.") for perm in self.get_all_permissions())

    def get_group_permissions(self, obj=None):
        if obj is not None:
            return set()

        perms = set()
        group_permissions_map = settings.FREEIPA_GROUP_PERMISSIONS

        for group in self.groups_list:
            if group in group_permissions_map:
                perms.update(group_permissions_map[group])

        return perms

    def __str__(self):
        return self.username

    def __eq__(self, other):
        return isinstance(other, FreeIPAUser) and self.username == other.username

    def __hash__(self):
        return hash(self.username)

    # Additional methods for group management as requested
    def add_to_group(self, group_name):
        try:
            res = _with_freeipa_service_client_retry(
                self.get_client,
                lambda client: client.group_add_member(group_name, o_user=[self.username]),
            )
            _raise_if_freeipa_failed(res, action="group_add_member", subject=f"user={self.username} group={group_name}")
            # Membership affects both user and group views.
            _invalidate_user_cache(self.username)
            _invalidate_group_cache(group_name)
            _invalidate_groups_list_cache()
            # Warm both caches.
            fresh_user = FreeIPAUser.get(self.username)
            FreeIPAGroup.get(group_name)
            if not fresh_user:
                raise FreeIPAOperationFailed(
                    f"FreeIPA group_add_member reported success but user could not be re-fetched (user={self.username} group={group_name})"
                )
            if group_name not in (getattr(fresh_user, "groups_list", []) or []):
                raise FreeIPAOperationFailed(
                    "FreeIPA group_add_member reported success but membership not present after refresh "
                    f"(user={self.username} group={group_name} response={_compact_repr(res)})"
                )
        except Exception:
            logger.exception("Failed to add user to group username=%s group=%s", self.username, group_name)
            raise

    def remove_from_group(self, group_name):
        try:
            res = _with_freeipa_service_client_retry(
                self.get_client,
                lambda client: client.group_remove_member(group_name, o_user=[self.username]),
            )
            _raise_if_freeipa_failed(res, action="group_remove_member", subject=f"user={self.username} group={group_name}")
            # Membership affects both user and group views.
            _invalidate_user_cache(self.username)
            _invalidate_group_cache(group_name)
            _invalidate_groups_list_cache()
            fresh_user = FreeIPAUser.get(self.username)
            FreeIPAGroup.get(group_name)
            if not fresh_user:
                raise FreeIPAOperationFailed(
                    f"FreeIPA group_remove_member reported success but user could not be re-fetched (user={self.username} group={group_name})"
                )
            if group_name in (getattr(fresh_user, "groups_list", []) or []):
                raise FreeIPAOperationFailed(
                    "FreeIPA group_remove_member reported success but membership still present after refresh "
                    f"(user={self.username} group={group_name} response={_compact_repr(res)})"
                )
        except Exception:
            logger.exception("Failed to remove user from group username=%s group=%s", self.username, group_name)
            raise


class FreeIPAGroup:
    """
    A non-persistent group object backed by FreeIPA.
    """
    def __init__(self, cn, group_data=None):
        self.cn = cn
        self._group_data = group_data or {}

        description = self._group_data.get('description', None)
        if isinstance(description, list):
            description = description[0] if description else None
        self.description = description

        members = self._group_data.get('member_user', [])
        if isinstance(members, str):
            members = [members]
        self.members = members

        # FAS extension attributes
        fas_url = self._group_data.get('fasurl', None)
        if isinstance(fas_url, list):
            fas_url = fas_url[0] if fas_url else None
        self.fas_url = fas_url

        fas_mailing_list = self._group_data.get('fasmailinglist', None)
        if isinstance(fas_mailing_list, list):
            fas_mailing_list = fas_mailing_list[0] if fas_mailing_list else None
        self.fas_mailing_list = fas_mailing_list

        fas_irc_channels = self._group_data.get('fasircchannel', [])
        if isinstance(fas_irc_channels, str):
            fas_irc_channels = [fas_irc_channels]
        self.fas_irc_channels = fas_irc_channels

        fas_discussion_url = self._group_data.get('fasdiscussionurl', None)
        if isinstance(fas_discussion_url, list):
            fas_discussion_url = fas_discussion_url[0] if fas_discussion_url else None
        self.fas_discussion_url = fas_discussion_url

        # Check if group has fasGroup support.
        # Prefer an explicit `fasgroup` attribute if present (some FreeIPA
        # deployments expose this boolean), otherwise fall back to checking
        # objectClass membership (case-insensitive).
        fasgroup_field = self._group_data.get('fasgroup', None)
        if isinstance(fasgroup_field, list):
            fasgroup_field = fasgroup_field[0] if fasgroup_field else None
        if fasgroup_field is not None:
            # Normalize typical boolean-ish values.
            if isinstance(fasgroup_field, bool):
                self.fas_group = bool(fasgroup_field)
            else:
                s = str(fasgroup_field).strip().upper()
                self.fas_group = s in {"TRUE", "T", "YES", "Y", "1", "ON"}
        else:
            object_classes = self._group_data.get('objectclass', [])
            if isinstance(object_classes, str):
                object_classes = [object_classes]
            self.fas_group = 'fasgroup' in [oc.lower() for oc in object_classes]
    
    def __str__(self):
        return self.cn

    @classmethod
    def get_client(cls) -> ClientMeta:
        """Return a FreeIPA client authenticated as the service account."""

        return _get_freeipa_service_client_cached()

    @classmethod
    def all(cls):
        """
        Returns a list of all groups from FreeIPA.
        """
        def _fetch_groups() -> list[dict[str, object]]:
            result = _with_freeipa_service_client_retry(
                cls.get_client,
                lambda client: client.group_find(o_all=True, o_no_members=False, o_sizelimit=0, o_timelimit=0),
            )
            return result.get('result', [])

        try:
            groups = cache.get_or_set(_groups_list_cache_key(), _fetch_groups) or []
            # Cache may legitimately contain an empty list; treat that as a hit.
            return [cls(g['cn'][0], g) for g in groups]
        except Exception:
            # On failure, avoid poisoning the cache with an empty list.
            logger.exception("Failed to list groups")
            return []

    @classmethod
    def get(cls, cn):
        """
        Fetch a single group by cn.
        """
        cache_key = _group_cache_key(cn)
        cached_data = cache.get(cache_key)

        if cached_data is not None:
            return cls(cn, cached_data)

        try:
            result = _with_freeipa_service_client_retry(
                cls.get_client,
                lambda client: client.group_find(o_cn=cn, o_all=True, o_no_members=False),
            )
            if result['count'] > 0:
                group_data = result['result'][0]
                cache.set(cache_key, group_data)
                return cls(cn, group_data)
        except Exception as e:
            logger.exception("Failed to get group cn=%s", cn)
        return None

    @classmethod
    def create(cls, cn, description=None, fas_group: bool = False):
        """
        Create a new group in FreeIPA. If `fas_group` is True, attempt to
        request the fasGroup objectClass at creation time.
        """
        try:
            kwargs = {}
            if description:
                kwargs['o_description'] = description

            if fas_group:
                kwargs['fasgroup'] = True

            _with_freeipa_service_client_retry(
                cls.get_client,
                lambda client: client.group_add(cn, **kwargs),
            )
            _invalidate_groups_list_cache()
            return cls.get(cn)
        except Exception as e:
            logger.exception("Failed to create group cn=%s", cn)
            raise

    def save(self):
        """
        Updates the group data in FreeIPA.
        """
        updates = {}
        if self.description:
            updates['o_description'] = self.description
        if self.fas_url:
            updates['o_fasurl'] = self.fas_url
        if self.fas_mailing_list:
            updates['o_fasmailinglist'] = self.fas_mailing_list
        if self.fas_irc_channels:
            updates['o_fasircchannel'] = self.fas_irc_channels
        if self.fas_discussion_url:
            updates['o_fasdiscussionurl'] = self.fas_discussion_url

        try:
            if updates:
                try:
                    _with_freeipa_service_client_retry(
                        self.get_client,
                        lambda client: client.group_mod(self.cn, **updates),
                    )
                except exceptions.BadRequest as e:
                    # FreeIPA can return BadRequest("no modifications to be performed") when
                    # group_mod is called with values identical to the current state.
                    if "no modifications to be performed" not in str(e).lower():
                        raise
                    logger.info("FreeIPA group_mod was a no-op cn=%s", self.cn)
            else:
                # Avoid calling group_mod with no updates (causes BadRequest)
                return

            _invalidate_group_cache(self.cn)
            _invalidate_groups_list_cache()
            FreeIPAGroup.get(self.cn)
        except Exception as e:
            logger.exception("Failed to update group cn=%s: %s", self.cn, e)
            raise

    def delete(self):
        """
        Delete the group from FreeIPA.
        First remove all members, then delete the group.
        """
        try:
            # Remove all members first (required for group deletion in FreeIPA)
            if self.members:
                res = _with_freeipa_service_client_retry(
                    self.get_client,
                    lambda client: client.group_remove_member(self.cn, o_user=self.members),
                )
                _raise_if_freeipa_failed(res, action="group_remove_member", subject=f"group={self.cn}")
                # Invalidate caches for affected users
                for username in self.members:
                    _invalidate_user_cache(username)
            
            # Now delete the group
            _with_freeipa_service_client_retry(
                self.get_client,
                lambda client: client.group_del(self.cn),
            )
            _invalidate_group_cache(self.cn)
            _invalidate_groups_list_cache()
        except Exception as e:
            logger.exception("Failed to delete group cn=%s", self.cn)
            raise

    def add_member(self, username):
        try:
            res = _with_freeipa_service_client_retry(
                self.get_client,
                lambda client: client.group_add_member(self.cn, o_user=[username]),
            )
            _raise_if_freeipa_failed(res, action="group_add_member", subject=f"group={self.cn} user={username}")
            _invalidate_group_cache(self.cn)
            _invalidate_user_cache(username)  # user's group list changes
            _invalidate_groups_list_cache()
            # Warm both caches.
            fresh_group = FreeIPAGroup.get(self.cn)
            fresh_user = FreeIPAUser.get(username)
            if fresh_group and username not in (getattr(fresh_group, "members", []) or []):
                raise FreeIPAOperationFailed(
                    "FreeIPA group_add_member reported success but membership not present after refresh "
                    f"(group={self.cn} user={username} response={_compact_repr(res)})"
                )
            if fresh_user and self.cn not in (getattr(fresh_user, "groups_list", []) or []):
                raise FreeIPAOperationFailed(
                    "FreeIPA group_add_member reported success but user does not show membership after refresh "
                    f"(group={self.cn} user={username} response={_compact_repr(res)})"
                )
        except Exception as e:
            logger.exception("Failed to add member username=%s group=%s", username, self.cn)
            raise

    def remove_member(self, username):
        try:
            res = _with_freeipa_service_client_retry(
                self.get_client,
                lambda client: client.group_remove_member(self.cn, o_user=[username]),
            )
            _raise_if_freeipa_failed(res, action="group_remove_member", subject=f"group={self.cn} user={username}")
            _invalidate_group_cache(self.cn)
            _invalidate_user_cache(username)  # user's group list changes
            _invalidate_groups_list_cache()
            fresh_group = FreeIPAGroup.get(self.cn)
            fresh_user = FreeIPAUser.get(username)
            if fresh_group and username in (getattr(fresh_group, "members", []) or []):
                raise FreeIPAOperationFailed(
                    "FreeIPA group_remove_member reported success but membership still present after refresh "
                    f"(group={self.cn} user={username} response={_compact_repr(res)})"
                )
            if fresh_user and self.cn in (getattr(fresh_user, "groups_list", []) or []):
                raise FreeIPAOperationFailed(
                    "FreeIPA group_remove_member reported success but user still shows membership after refresh "
                    f"(group={self.cn} user={username} response={_compact_repr(res)})"
                )
        except Exception as e:
            logger.exception("Failed to remove member username=%s group=%s", username, self.cn)
            raise


class FreeIPAAuthBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        logger.debug("authenticate: username=%s", username)

        try:
            # Try to login with provided credentials
            client = _get_freeipa_client(username, password)

            # Fetch full user data (includes custom/FAS attributes)
            user_data = FreeIPAUser._fetch_full_user(client, username)
            if user_data:
                logger.debug("authenticate: success username=%s", username)
                user = FreeIPAUser(username, user_data)
                # Persist username inside the session so reloads don't depend on LocMemCache.
                if request is not None and hasattr(request, 'session'):
                    request.session['_freeipa_username'] = username
                return user
            return None
        except exceptions.PasswordExpired:
            logger.debug("authenticate: password expired username=%s", username)
            if request is not None:
                setattr(request, "_freeipa_password_expired", True)
                try:
                    request.session["_freeipa_pwexp_username"] = username
                except Exception:
                    pass
            return None
        except exceptions.UserLocked:
            logger.debug("authenticate: user locked username=%s", username)
            if request is not None:
                setattr(request, "_freeipa_auth_error", "Your account is locked. Please contact support.")
            return None
        except exceptions.KrbPrincipalExpired:
            logger.debug("authenticate: principal expired username=%s", username)
            if request is not None:
                setattr(request, "_freeipa_auth_error", "Your account credentials have expired. Please contact support.")
            return None
        except exceptions.InvalidSessionPassword:
            logger.debug("authenticate: invalid session password username=%s", username)
            if request is not None:
                setattr(request, "_freeipa_auth_error", "Invalid username or password.")
            return None
        except exceptions.Denied:
            logger.debug("authenticate: denied username=%s", username)
            if request is not None:
                setattr(request, "_freeipa_auth_error", "Login denied.")
            return None
        except exceptions.Unauthorized:
            logger.debug("authenticate: unauthorized username=%s", username)
            if request is not None:
                setattr(request, "_freeipa_auth_error", "Invalid username or password.")
            return None
        except exceptions.BadRequest as e:
            # Catch-all for FreeIPA-side errors that are still a 4xx-style response.
            logger.warning("authenticate: bad request username=%s error=%s", username, e)
            if request is not None:
                setattr(request, "_freeipa_auth_error", "Login failed due to a FreeIPA error.")
            return None
        except Exception as e:
            logger.exception("FreeIPA authentication error username=%s", username)
            if request is not None:
                setattr(request, "_freeipa_auth_error", "Login failed due to an internal error.")
            return None

    def get_user(self, user_id):
        # Intentionally return None.
        #
        # This project stores the FreeIPA username in the session at login
        # (request.session['_freeipa_username']). Our middleware restores the
        # user object from that value on every request, which works across
        # restarts and multi-process deployments without depending on a shared
        # cache backend.
        return None
