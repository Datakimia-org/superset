/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

import { SupersetClient, DataMaskStateWithId } from '@superset-ui/core';
import { FilterInfo, FilterSetEntry } from './filterSetsStorage';

const baseEndpoint = (dashId: number) =>
  `api/v1/dashboard/${dashId}/filter_sets`;

export const getFilterSetsFromServer = (
  dashId: number,
): Promise<FilterSetEntry[]> =>
  SupersetClient.get({ endpoint: baseEndpoint(dashId) }).then(
    ({ json }) => (json.result as FilterSetEntry[]) ?? [],
  );

export const saveFilterSetToServer = (
  dashId: number,
  dataMask: DataMaskStateWithId,
  appliedFilters: FilterInfo[],
  label?: string,
): Promise<string> =>
  SupersetClient.post({
    endpoint: baseEndpoint(dashId),
    jsonPayload: { dataMask, appliedFilters, label },
  }).then(({ json }) => json.id as string);

export const updateFilterSetLabelOnServer = (
  dashId: number,
  setId: string,
  label: string,
): Promise<void> =>
  SupersetClient.put({
    endpoint: `${baseEndpoint(dashId)}/${setId}`,
    jsonPayload: { label },
  }).then(() => undefined);

export const deleteFilterSetFromServer = (
  dashId: number,
  setId: string,
): Promise<void> =>
  SupersetClient.delete({
    endpoint: `${baseEndpoint(dashId)}/${setId}`,
  }).then(() => undefined);
