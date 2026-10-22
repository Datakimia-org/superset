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
import importlib.util
from pathlib import Path

from superset.security import SupersetSecurityManager

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docker"
    / "pythonpath_dev"
    / "custom_sso_security_manager.py"
)


def _load_sso_module():
    spec = importlib.util.spec_from_file_location(
        "dk_custom_sso_security_manager",
        _MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_is_item_public_skips_jwt_without_request(monkeypatch):
    module = _load_sso_module()
    calls: list[bool] = []
    monkeypatch.setattr(
        module,
        "verify_jwt_in_request",
        lambda *args, **kwargs: calls.append(True),
    )
    monkeypatch.setattr(module, "has_request_context", lambda: False)
    monkeypatch.setattr(
        SupersetSecurityManager,
        "is_item_public",
        lambda self, permission_name, view_name: False,
    )

    manager = module.CustomSsoSecurityManager.__new__(module.CustomSsoSecurityManager)
    assert manager.is_item_public("all_database_access", "all_database_access") is False
    assert calls == []


def test_is_item_public_reads_jwt_inside_request(monkeypatch):
    module = _load_sso_module()
    calls: list[bool] = []
    monkeypatch.setattr(
        module,
        "verify_jwt_in_request",
        lambda *args, **kwargs: calls.append(kwargs.get("optional") is True),
    )
    monkeypatch.setattr(module, "has_request_context", lambda: True)
    monkeypatch.setattr(
        SupersetSecurityManager,
        "is_item_public",
        lambda self, permission_name, view_name: True,
    )

    manager = module.CustomSsoSecurityManager.__new__(module.CustomSsoSecurityManager)
    assert manager.is_item_public("all_database_access", "all_database_access") is True
    assert calls == [True]
