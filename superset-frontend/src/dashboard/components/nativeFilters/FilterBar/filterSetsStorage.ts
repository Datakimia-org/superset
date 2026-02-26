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

const STORAGE_KEY_PREFIX = 'superset_filter_sets_';
const MAX_FILTER_SETS = 20;

const getStorageKey = (dashboardId: number): string =>
  `${STORAGE_KEY_PREFIX}${dashboardId}`;

export const getFilterSets = (dashboardId: number): FilterSetEntry[] => {
  try {
    const key = getStorageKey(dashboardId);
    const stored = sessionStorage.getItem(key);
    if (!stored) {
      return [];
    }
    return JSON.parse(stored) as FilterSetEntry[];
  } catch (error) {
    console.error('Error reading filter sets from storage:', error);
    return [];
  }
};

export const saveFilterSet = (
  dashboardId: number,
  dataMask: DataMaskStateWithId,
  appliedFilters: FilterInfo[],
  customLabel?: string,
): void => {
  try {
    const filterSets = getFilterSets(dashboardId);
    const newEntry: FilterSetEntry = {
      id: `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      timestamp: Date.now(),
      dataMask,
      appliedFilters,
      ...(customLabel ? { customLabel } : {}),
    };

    const updated = [newEntry, ...filterSets].slice(0, MAX_FILTER_SETS);
    sessionStorage.setItem(getStorageKey(dashboardId), JSON.stringify(updated));
  } catch (error) {
    console.error('Error saving filter set to storage:', error);
  }
};

export const clearFilterSets = (dashboardId: number): void => {
  try {
    sessionStorage.removeItem(getStorageKey(dashboardId));
  } catch (error) {
    console.error('Error clearing filter sets from storage:', error);
  }
};

export const deleteFilterSetEntry = (
  dashboardId: number,
  entryId: string,
): void => {
  try {
    const updated = getFilterSets(dashboardId).filter(e => e.id !== entryId);
    sessionStorage.setItem(getStorageKey(dashboardId), JSON.stringify(updated));
  } catch (error) {
    console.error('Error deleting filter set entry from storage:', error);
  }
};

export const updateFilterSetLabel = (
  dashboardId: number,
  entryId: string,
  customLabel: string,
): void => {
  try {
    const updated = getFilterSets(dashboardId).map(e =>
      e.id === entryId ? { ...e, customLabel } : e,
    );
    sessionStorage.setItem(getStorageKey(dashboardId), JSON.stringify(updated));
  } catch (error) {
    console.error('Error updating filter set label in storage:', error);
  }
};
