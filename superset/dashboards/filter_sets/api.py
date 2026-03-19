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
import logging

from flask import Response, request
from flask_appbuilder.api import expose, protect, safe

from superset.commands.dashboard.filter_sets.create import CreateFilterSetCommand
from superset.commands.dashboard.filter_sets.delete import DeleteFilterSetCommand
from superset.commands.dashboard.filter_sets.get import GetFilterSetsCommand
from superset.commands.dashboard.filter_sets.update import UpdateFilterSetCommand
from superset.extensions import event_logger
from superset.views.base_api import BaseSupersetApi

logger = logging.getLogger(__name__)


class DashboardFilterSetsRestApi(BaseSupersetApi):
    class_permission_name = "DashboardFilterSetsRestApi"
    allow_browser_login = True
    resource_name = "dashboard"
    openapi_spec_tag = "Dashboard Filter Sets"

    @expose("/<int:pk>/filter_sets", methods=("GET",))
    @protect()
    @safe
    @event_logger.log_this_with_context(
        action=lambda self, *args, **kwargs: f"{self.__class__.__name__}.get",
        log_to_statsd=False,
    )
    def get(self, pk: int) -> Response:
        """List saved filter sets for a dashboard.
        ---
        get:
          summary: List saved filter sets for a dashboard
          parameters:
          - in: path
            schema:
              type: integer
            name: pk
          responses:
            200:
              description: Returns the list of filter sets.
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      result:
                        type: array
                        items:
                          type: object
            401:
              $ref: '#/components/responses/401'
            500:
              $ref: '#/components/responses/500'
        """
        try:
            sets = GetFilterSetsCommand(pk).run()
            return self.response(200, result=sets)
        except Exception as ex:  # pylint: disable=broad-except
            logger.exception("Error getting filter sets for dashboard %s", pk)
            return self.response_500(message=str(ex))

    @expose("/<int:pk>/filter_sets", methods=("POST",))
    @protect()
    @safe
    @event_logger.log_this_with_context(
        action=lambda self, *args, **kwargs: f"{self.__class__.__name__}.post",
        log_to_statsd=False,
    )
    def post(self, pk: int) -> Response:
        """Save a new filter set for a dashboard.
        ---
        post:
          summary: Save a new filter set for a dashboard
          parameters:
          - in: path
            schema:
              type: integer
            name: pk
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    dataMask:
                      type: object
                    appliedFilters:
                      type: array
                      items:
                        type: object
                    label:
                      type: string
          responses:
            201:
              description: Filter set created.
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
            400:
              $ref: '#/components/responses/400'
            401:
              $ref: '#/components/responses/401'
            500:
              $ref: '#/components/responses/500'
        """
        body = request.json or {}
        data_mask = body.get("dataMask", {})
        applied_filters = body.get("appliedFilters", [])
        label = body.get("label")
        try:
            new_id = CreateFilterSetCommand(pk, data_mask, applied_filters, label).run()
            return self.response(201, id=new_id)
        except Exception as ex:  # pylint: disable=broad-except
            logger.exception("Error creating filter set for dashboard %s", pk)
            return self.response_500(message=str(ex))

    @expose("/<int:pk>/filter_sets/<string:set_id>", methods=("PUT",))
    @protect()
    @safe
    @event_logger.log_this_with_context(
        action=lambda self, *args, **kwargs: f"{self.__class__.__name__}.put",
        log_to_statsd=False,
    )
    def put(self, pk: int, set_id: str) -> Response:
        """Update a filter set label.
        ---
        put:
          summary: Update a filter set label
          parameters:
          - in: path
            schema:
              type: integer
            name: pk
          - in: path
            schema:
              type: string
            name: set_id
          requestBody:
            required: true
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    label:
                      type: string
          responses:
            200:
              description: Filter set updated.
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
            400:
              $ref: '#/components/responses/400'
            401:
              $ref: '#/components/responses/401'
            404:
              $ref: '#/components/responses/404'
            500:
              $ref: '#/components/responses/500'
        """
        body = request.json or {}
        label = body.get("label", "")
        try:
            UpdateFilterSetCommand(pk, set_id, label).run()
            return self.response(200, id=set_id)
        except ValueError as ex:
            return self.response_404()
        except Exception as ex:  # pylint: disable=broad-except
            logger.exception(
                "Error updating filter set %s for dashboard %s", set_id, pk
            )
            return self.response_500(message=str(ex))

    @expose("/<int:pk>/filter_sets/<string:set_id>", methods=("DELETE",))
    @protect()
    @safe
    @event_logger.log_this_with_context(
        action=lambda self, *args, **kwargs: f"{self.__class__.__name__}.delete",
        log_to_statsd=False,
    )
    def delete(self, pk: int, set_id: str) -> Response:
        """Delete a saved filter set.
        ---
        delete:
          summary: Delete a saved filter set
          parameters:
          - in: path
            schema:
              type: integer
            name: pk
          - in: path
            schema:
              type: string
            name: set_id
          responses:
            200:
              description: Filter set deleted.
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      message:
                        type: string
            401:
              $ref: '#/components/responses/401'
            404:
              $ref: '#/components/responses/404'
            500:
              $ref: '#/components/responses/500'
        """
        try:
            DeleteFilterSetCommand(pk, set_id).run()
            return self.response(200, message="Deleted successfully")
        except ValueError as ex:
            return self.response_404()
        except Exception as ex:  # pylint: disable=broad-except
            logger.exception(
                "Error deleting filter set %s for dashboard %s", set_id, pk
            )
            return self.response_500(message=str(ex))
