# CustomSecurityManager.py

from flask import redirect, g, flash, request, abort
from superset.security import SupersetSecurityManager
from flask_appbuilder.security.views import UserDBModelView,AuthOAuthView
from flask_appbuilder.security.views import expose
from flask_login import login_user, logout_user
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)

class CustomOAuthView(AuthOAuthView):
    @expose('/login/', methods=['GET', 'POST'])
    @expose("/login/<provider>", methods=['GET', 'POST'])
    @expose("/login/<provider>/<register>")
    @expose("/login/<provider>/<username>")
    def login(self, provider= None, username= None):
        if username is not None:
            user = self.appbuilder.sm.find_user(username=username)
            if user is None:
                user = self.appbuilder.sm.find_user(email=username)   
            if user is None:
                abort(404)  # Return HTTP 404 if user is not found                         
            return str(user.id)
        else :
            return super(CustomOAuthView,self).login(provider)

guest_role_pvms = [
    ("can_read", "SavedQuery"),
    ("can_read", "CSSTemplate"),
    ("can_read", "ReportSchedule"),
    ("can_read", "Chart"),
    ("can_read", "Annotation"),
    ("can_read", "Dataset"),
    ("can_read", "Log"),
    ("can_read", "Dashboard"),
    ("can_read", "Database"),
    ("can_read", "Query"),
    ("can_warm_up_cache", "Chart"),
    ("can_read", "DashboardFilterStateRestApi"),
    ("can_get_embedded", "Dashboard"),
    ("can_read", "Tag"),
    ("can_explore_json", "Superset"),
    ("can_time_range", "Api"),
    ("can_recent_activity", "Log"),        
]

client_admin_pvms = [
    ("can_this_form_get", "UserInfoEditView"),
    ("can_this_form_post", "UserInfoEditView"),
    ("can_show", "RoleModelView"),
    ("can_add", "RoleModelView"),
    ("can_edit", "RoleModelView"),
    ("can_list", "RoleModelView"),
    ("can_delete", "User"),
    ("can_delete", "Role"),
    ("can_delete", "RoleModelView"),
    ("copyrole", "RoleModelView"),
    ("can_get", "User"),
    ("can_get", "Role"),
    ("can_info", "User"),
    ("can_info", "Role"),
    ("can_add_role_permissions", "Role"),
    ("can_post", "User"),
    ("can_post", "Role"),
    ("can_put", "User"),
    ("can_put", "Role"),
    ("can_list_role_permissions", "Role"),
    ("menu_access", "List Roles"),
    ("menu_access", "List Users"),
]


class CustomSsoSecurityManager(SupersetSecurityManager):
    authoauthview = CustomOAuthView
    def __init__(self, appbuilder):
        super(CustomSsoSecurityManager, self).__init__(appbuilder)

        guest_role = self.add_role("Guest")
        for (action, model) in guest_role_pvms:
            pvm = self.find_permission_view_menu(action, model)
            self.add_permission_role(guest_role, pvm)

        client_admin_role = self.add_role("Client_Admin")
        for (action, model) in client_admin_pvms:
            pvm = self.find_permission_view_menu(action, model)
            self.add_permission_role(client_admin_role, pvm)