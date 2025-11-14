#!/usr/bin/env bash
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
HYPHEN_SYMBOL='-'

# Disable Gunicorn access logs when using GCP structured logging
# Access logs will be handled by Flask middleware for JSON formatting and request_id correlation
# If ACCESS_LOG_FILE is explicitly set, use it; otherwise disable access logs
GUNICORN_ACCESS_LOG_ARGS=""
if [ -n "${ACCESS_LOG_FILE:-}" ]; then
    # ACCESS_LOG_FILE is explicitly set, use it
    GUNICORN_ACCESS_LOG_ARGS="--access-logfile ${ACCESS_LOG_FILE}"
else
    # Disable access logs by redirecting to /dev/null (Gunicorn doesn't support --no-access-log)
    GUNICORN_ACCESS_LOG_ARGS="--access-logfile /dev/null"
fi

gunicorn \
    --bind "${SUPERSET_BIND_ADDRESS:-0.0.0.0}:${SUPERSET_PORT:-8088}" \
    ${GUNICORN_ACCESS_LOG_ARGS} \
    --error-logfile "${ERROR_LOG_FILE:-$HYPHEN_SYMBOL}" \
    --workers ${SERVER_WORKER_AMOUNT:-1} \
    --worker-class ${SERVER_WORKER_CLASS:-gthread} \
    --threads ${SERVER_THREADS_AMOUNT:-20} \
    --timeout ${GUNICORN_TIMEOUT:-60} \
    --keep-alive ${GUNICORN_KEEPALIVE:-2} \
    --max-requests ${WORKER_MAX_REQUESTS:-0} \
    --max-requests-jitter ${WORKER_MAX_REQUESTS_JITTER:-0} \
    --limit-request-line ${SERVER_LIMIT_REQUEST_LINE:-0} \
    --limit-request-field_size ${SERVER_LIMIT_REQUEST_FIELD_SIZE:-0} \
    "${FLASK_APP}"
