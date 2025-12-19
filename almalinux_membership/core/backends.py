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
                _with_freeipa_service_client_retry(
                    self.get_client,
                    lambda client: client.user_mod(self.username, **updates),
                )
            # Invalidate and refresh cache entries.
            _invalidate_user_cache(self.username)
            _invalidate_users_list_cache()
            # Warm fresh data for subsequent reads.
            FreeIPAUser.get(self.username)
        except Exception as e:
            logger.exception("Failed to update user username=%s", self.username)
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
            _with_freeipa_service_client_retry(
                self.get_client,
                lambda client: client.group_add_member(group_name, o_user=[self.username]),
            )
            # Membership affects both user and group views.
            _invalidate_user_cache(self.username)
            _invalidate_group_cache(group_name)
            _invalidate_groups_list_cache()
            # Warm both caches.
            FreeIPAUser.get(self.username)
            FreeIPAGroup.get(group_name)
        except Exception as e:
            logger.exception("Failed to add user to group username=%s group=%s", self.username, group_name)
            raise

    def remove_from_group(self, group_name):
        try:
            _with_freeipa_service_client_retry(
                self.get_client,
                lambda client: client.group_remove_member(group_name, o_user=[self.username]),
            )
            _invalidate_user_cache(self.username)
            _invalidate_group_cache(group_name)
            _invalidate_groups_list_cache()
            FreeIPAUser.get(self.username)
            FreeIPAGroup.get(group_name)
        except Exception as e:
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
    def create(cls, cn, description=None):
        """
        Create a new group in FreeIPA.
        """
        try:
            kwargs = {}
            if description:
                kwargs['o_description'] = description
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

        try:
            _with_freeipa_service_client_retry(
                self.get_client,
                lambda client: client.group_mod(self.cn, **updates),
            )
            _invalidate_group_cache(self.cn)
            _invalidate_groups_list_cache()
            FreeIPAGroup.get(self.cn)
        except Exception as e:
            logger.exception("Failed to update group cn=%s", self.cn)
            raise

    def delete(self):
        """
        Delete the group from FreeIPA.
        """
        try:
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
            _with_freeipa_service_client_retry(
                self.get_client,
                lambda client: client.group_add_member(self.cn, o_user=[username]),
            )
            _invalidate_group_cache(self.cn)
            _invalidate_user_cache(username)  # user's group list changes
            _invalidate_groups_list_cache()
            # Warm both caches.
            FreeIPAGroup.get(self.cn)
            FreeIPAUser.get(username)
        except Exception as e:
            logger.exception("Failed to add member username=%s group=%s", username, self.cn)
            raise

    def remove_member(self, username):
        try:
            _with_freeipa_service_client_retry(
                self.get_client,
                lambda client: client.group_remove_member(self.cn, o_user=[username]),
            )
            _invalidate_group_cache(self.cn)
            _invalidate_user_cache(username)  # user's group list changes
            _invalidate_groups_list_cache()
            FreeIPAGroup.get(self.cn)
            FreeIPAUser.get(username)
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
