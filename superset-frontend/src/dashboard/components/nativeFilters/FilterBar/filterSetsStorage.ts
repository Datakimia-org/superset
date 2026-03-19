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

import { DataMaskStateWithId } from '@superset-ui/core';
import {
  getFilterSetsFromServer,
  saveFilterSetToServer,
  updateFilterSetLabelOnServer,
  deleteFilterSetFromServer,
} from './filterSetsApi';

export interface FilterInfo {
  id: string;
  name: string;
  value: any;
}

export interface FilterSetEntry {
  id: string;
  timestamp: number;
  dataMask: DataMaskStateWithId;
  appliedFilters: FilterInfo[];
  customLabel?: string;
}

export const getFilterSets = (dashboardId: number): Promise<FilterSetEntry[]> =>
  getFilterSetsFromServer(dashboardId);

export const saveFilterSet = (
  dashboardId: number,
  dataMask: DataMaskStateWithId,
  appliedFilters: FilterInfo[],
  customLabel?: string,
): Promise<string> =>
  saveFilterSetToServer(dashboardId, dataMask, appliedFilters, customLabel);

export const deleteFilterSetEntry = (
  dashboardId: number,
  entryId: string,
): Promise<void> => deleteFilterSetFromServer(dashboardId, entryId);

export const updateFilterSetLabel = (
  dashboardId: number,
  entryId: string,
  customLabel: string,
): Promise<void> =>
  updateFilterSetLabelOnServer(dashboardId, entryId, customLabel);
