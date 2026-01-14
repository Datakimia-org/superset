# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from typing import Optional, TypedDict, Union

from flask_appbuilder.security.sqla.models import Role, User
from flask_login import AnonymousUserMixin

from superset.utils.backports import StrEnum


class GuestTokenUser(TypedDict, total=False):
    username: str
    first_name: str
    last_name: str


class GuestTokenResourceType(StrEnum):
    DASHBOARD = "dashboard"


class GuestTokenResource(TypedDict):
    type: GuestTokenResourceType
    id: Union[str, int]


GuestTokenResources = list[GuestTokenResource]


class GuestTokenRlsRule(TypedDict):
    dataset: Optional[str]
    clause: str


class GuestToken(TypedDict):
    iat: float
    exp: float
    user: GuestTokenUser
    resources: GuestTokenResources
    rls_rules: list[GuestTokenRlsRule]


class GuestUser(AnonymousUserMixin):
    """
    Used as the "anonymous" user in case of guest authentication (embedded)
    """

    is_guest_user = True

    @property
    def is_authenticated(self) -> bool:
        """
        This is set to true because guest users should be considered authenticated,
        at least in most places. The treatment of this flag is kind of inconsistent.
        """
        return True

    @property
    def is_anonymous(self) -> bool:
        """
        This is set to false because lots of code assumes that
        if user.is_anonymous, then role = Public
        But guest users need to have their own role independent of Public.
        """
        return False

    def __init__(self, token: GuestToken, roles: list[Role]):
        user = token["user"]
        self.guest_token = token
        self.username = user.get("username", "guest_user")
        self.first_name = user.get("first_name", "Guest")
        self.last_name = user.get("last_name", "User")
        self.roles = roles
        self.resources = token["resources"]
        self.rls = token.get("rls_rules", [])

        # Get the real user id from the database for logging purposes
        self.id = self._get_user_id_from_db()

    def _get_user_id_from_db(self) -> Optional[int]:
        """
        Retrieve the user ID from the database by matching username.
        This allows guest users to be properly logged with their real user ID.

        Username is unique in Superset's User model (enforced by Flask-AppBuilder).
        """
        try:
            # Import here to avoid circular import
            from superset.extensions import db

            # Find user by username (unique field)
            if self.username and self.username != "guest_user":
                user = db.session.query(User).filter(
                    User.username == self.username
                ).first()
                if user:
                    return user.id
        except Exception:  # pylint: disable=broad-except
            # Silently fail and return None if database query fails
            # This prevents guest token authentication from breaking
            pass

        return None
