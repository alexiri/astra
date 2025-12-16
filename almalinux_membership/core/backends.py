import logging
from django.conf import settings
from django.contrib.auth.backends import BaseBackend
from django.core.cache import cache
from django.utils.crypto import salted_hmac
from python_freeipa import ClientMeta, exceptions

logger = logging.getLogger(__name__)


def _freeipa_cache_timeout() -> int:
    return int(getattr(settings, 'FREEIPA_CACHE_TIMEOUT', 300))


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


def _session_uid_cache_key(session_uid: int) -> str:
    return f'freeipa_session_uid_{session_uid}'


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
        self.first_name = _first('givenname')
        self.last_name = _first('sn')
        self.email = _first('mail')

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
        admin_group = getattr(settings, 'FREEIPA_ADMIN_GROUP', 'admins')
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
    def get_client(cls):
        """
        Returns a FreeIPA client authenticated as the service account.
        """
        client = ClientMeta(host=settings.FREEIPA_HOST, verify_ssl=settings.FREEIPA_VERIFY_SSL)
        client.login(settings.FREEIPA_SERVICE_USER, settings.FREEIPA_SERVICE_PASSWORD)
        return client

    @classmethod
    def all(cls):
        """
        Returns a list of all users from FreeIPA.
        """
        cached = cache.get(_users_list_cache_key())
        if cached:
            return [cls(u['uid'][0], u) for u in cached]

        client = cls.get_client()
        try:
            # FreeIPA server/client may default to returning only 100 entries.
            # Request an unlimited result set where supported.
            result = client.user_find(o_all=True, o_no_members=False, o_sizelimit=0, o_timelimit=0)
            users = result.get('result', [])
            cache.set(_users_list_cache_key(), users, timeout=_freeipa_cache_timeout())
            return [cls(u['uid'][0], u) for u in users]
        except Exception as e:
            logger.error(f"Failed to list users: {e}")
            return []

    @classmethod
    def _fetch_full_user(cls, client: ClientMeta, username: str):
        """Return a single user's full attribute dict.

        Prefer user_show (returns full attribute set including custom schema
        like Fedora's FAS fields). Fallback to user_find if needed.
        """
        # Try common call styles across python-freeipa versions.
        try:
            res = client.user_show(username, o_all=True, o_no_members=False)
            if res and 'result' in res:
                return res['result']
        except Exception:
            pass
        try:
            res = client.user_show(a_uid=username, o_all=True, o_no_members=False)
            if res and 'result' in res:
                return res['result']
        except Exception:
            pass
        # Fallback to a targeted find.
        try:
            res = client.user_find(o_uid=username, o_all=True, o_no_members=False)
            if res and res.get('count', 0) > 0:
                return res['result'][0]
        except Exception:
            pass
        return None

    @classmethod
    def get(cls, username):
        """
        Fetch a single user by username.
        """
        # Check cache first
        cache_key = _user_cache_key(username)
        cached_data = cache.get(cache_key)

        if cached_data:
            return cls(username, cached_data)

        client = cls.get_client()
        try:
            user_data = cls._fetch_full_user(client, username)
            if user_data:
                cache.set(cache_key, user_data, timeout=_freeipa_cache_timeout())
                return cls(username, user_data)
        except Exception as e:
            logger.error(f"Failed to get user {username}: {e}")
        return None

    @classmethod
    def create(cls, username, **kwargs):
        """
        Create a new user in FreeIPA.
        kwargs should match FreeIPA user_add arguments (e.g., givenname, sn, mail, password).
        """
        client = cls.get_client()
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

            client.user_add(username, givenname, sn, cn, **ipa_kwargs)
            # New user should appear in lists; invalidate list cache and warm this user's cache.
            _invalidate_users_list_cache()
            return cls.get(username)
        except Exception as e:
            logger.error(f"Failed to create user {username}: {e}")
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

        client = self.get_client()
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
                client.user_mod(self.username, **updates)
            # Invalidate and refresh cache entries.
            _invalidate_user_cache(self.username)
            _invalidate_users_list_cache()
            # Warm fresh data for subsequent reads.
            FreeIPAUser.get(self.username)
        except Exception as e:
            logger.error(f"Failed to update user {self.username}: {e}")
            raise

    def delete(self):
        """
        Delete the user from FreeIPA.
        """
        client = self.get_client()
        try:
            client.user_del(self.username)
            _invalidate_user_cache(self.username)
            _invalidate_users_list_cache()
        except Exception as e:
            logger.error(f"Failed to delete user {self.username}: {e}")
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
        group_permissions_map = getattr(settings, 'FREEIPA_GROUP_PERMISSIONS', {})

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
        client = self.get_client()
        try:
            client.group_add_member(group_name, o_user=[self.username])
            # Membership affects both user and group views.
            _invalidate_user_cache(self.username)
            _invalidate_group_cache(group_name)
            _invalidate_groups_list_cache()
            # Warm both caches.
            FreeIPAUser.get(self.username)
            FreeIPAGroup.get(group_name)
        except Exception as e:
            logger.error(f"Failed to add user {self.username} to group {group_name}: {e}")
            raise

    def remove_from_group(self, group_name):
        client = self.get_client()
        try:
            client.group_remove_member(group_name, o_user=[self.username])
            _invalidate_user_cache(self.username)
            _invalidate_group_cache(group_name)
            _invalidate_groups_list_cache()
            FreeIPAUser.get(self.username)
            FreeIPAGroup.get(group_name)
        except Exception as e:
            logger.error(f"Failed to remove user {self.username} from group {group_name}: {e}")
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
    def get_client(cls):
        client = ClientMeta(host=settings.FREEIPA_HOST, verify_ssl=settings.FREEIPA_VERIFY_SSL)
        client.login(settings.FREEIPA_SERVICE_USER, settings.FREEIPA_SERVICE_PASSWORD)
        return client

    @classmethod
    def all(cls):
        """
        Returns a list of all groups from FreeIPA.
        """
        cached = cache.get(_groups_list_cache_key())
        if cached:
            return [cls(g['cn'][0], g) for g in cached]

        client = cls.get_client()
        try:
            result = client.group_find(o_all=True, o_no_members=False, o_sizelimit=0, o_timelimit=0)
            groups = result.get('result', [])
            cache.set(_groups_list_cache_key(), groups, timeout=_freeipa_cache_timeout())
            return [cls(g['cn'][0], g) for g in groups]
        except Exception as e:
            logger.error(f"Failed to list groups: {e}")
            return []

    @classmethod
    def get(cls, cn):
        """
        Fetch a single group by cn.
        """
        cache_key = _group_cache_key(cn)
        cached_data = cache.get(cache_key)

        if cached_data:
            return cls(cn, cached_data)

        client = cls.get_client()
        try:
            result = client.group_find(o_cn=cn, o_all=True, o_no_members=False)
            if result['count'] > 0:
                group_data = result['result'][0]
                cache.set(cache_key, group_data, timeout=_freeipa_cache_timeout())
                return cls(cn, group_data)
        except Exception as e:
            logger.error(f"Failed to get group {cn}: {e}")
        return None

    @classmethod
    def create(cls, cn, description=None):
        """
        Create a new group in FreeIPA.
        """
        client = cls.get_client()
        try:
            kwargs = {}
            if description:
                kwargs['o_description'] = description
            client.group_add(cn, **kwargs)
            _invalidate_groups_list_cache()
            return cls.get(cn)
        except Exception as e:
            logger.error(f"Failed to create group {cn}: {e}")
            raise

    def save(self):
        """
        Updates the group data in FreeIPA.
        """
        client = self.get_client()
        updates = {}
        if self.description:
            updates['o_description'] = self.description

        try:
            client.group_mod(self.cn, **updates)
            _invalidate_group_cache(self.cn)
            _invalidate_groups_list_cache()
            FreeIPAGroup.get(self.cn)
        except Exception as e:
            logger.error(f"Failed to update group {self.cn}: {e}")
            raise

    def delete(self):
        """
        Delete the group from FreeIPA.
        """
        client = self.get_client()
        try:
            client.group_del(self.cn)
            _invalidate_group_cache(self.cn)
            _invalidate_groups_list_cache()
        except Exception as e:
            logger.error(f"Failed to delete group {self.cn}: {e}")
            raise

    def add_member(self, username):
        client = self.get_client()
        try:
            client.group_add_member(self.cn, o_user=[username])
            _invalidate_group_cache(self.cn)
            _invalidate_user_cache(username)  # user's group list changes
            _invalidate_groups_list_cache()
            # Warm both caches.
            FreeIPAGroup.get(self.cn)
            FreeIPAUser.get(username)
        except Exception as e:
            logger.error(f"Failed to add user {username} to group {self.cn}: {e}")
            raise

    def remove_member(self, username):
        client = self.get_client()
        try:
            client.group_remove_member(self.cn, o_user=[username])
            _invalidate_group_cache(self.cn)
            _invalidate_user_cache(username)  # user's group list changes
            _invalidate_groups_list_cache()
            FreeIPAGroup.get(self.cn)
            FreeIPAUser.get(username)
        except Exception as e:
            logger.error(f"Failed to remove user {username} from group {self.cn}: {e}")
            raise


class FreeIPAAuthBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        client = ClientMeta(host=settings.FREEIPA_HOST, verify_ssl=settings.FREEIPA_VERIFY_SSL)
        try:
            # Try to login with provided credentials
            client.login(username, password)

            # Fetch full user data (includes custom/FAS attributes)
            user_data = FreeIPAUser._fetch_full_user(client, username)
            if user_data:
                logger.error(f'authenticate: {user_data}')
                user = FreeIPAUser(username, user_data)
                # Map the numeric session uid back to username for later requests.
                cache.set(_session_uid_cache_key(_session_user_id_for_username(username)), username, timeout=None)
                # Persist username inside the session so reloads don't depend on LocMemCache.
                if request is not None and hasattr(request, 'session'):
                    request.session['_freeipa_username'] = username
                return user
            return None
        except exceptions.Unauthorized:
            return None
        except Exception as e:
            logger.error(f"FreeIPA authentication error: {e}")
            return None

    def get_user(self, user_id):
        # Django's default session loader expects an integer user_id.
        try:
            session_uid = int(user_id)
        except (TypeError, ValueError):
            return None

        username = cache.get(_session_uid_cache_key(session_uid))
        if not username:
            return None

        # Check cache first (keyed by username)
        cache_key = f'freeipa_user_{username}'
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.error(f'get_user (cached): {cached_data}')
            return FreeIPAUser(username, cached_data)

        # Fetch from FreeIPA using service account
        try:
            client = ClientMeta(host=settings.FREEIPA_HOST, verify_ssl=settings.FREEIPA_VERIFY_SSL)
            # We need a service account to fetch user details without their password
            if hasattr(settings, 'FREEIPA_SERVICE_USER') and hasattr(settings, 'FREEIPA_SERVICE_PASSWORD'):
                client.login(settings.FREEIPA_SERVICE_USER, settings.FREEIPA_SERVICE_PASSWORD)
                user_data = FreeIPAUser._fetch_full_user(client, username)
                if user_data:
                    logger.error(f'get_user: {user_data}')
                    # Cache the user data
                    cache.set(cache_key, user_data, timeout=300) # Cache for 5 minutes
                    return FreeIPAUser(username, user_data)
        except Exception as e:
            logger.error(f"Error fetching user {username} from FreeIPA: {e}")

        return None
