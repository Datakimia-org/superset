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

export interface FilterHistoryEntry {
  id: string;
  timestamp: number;
  dataMask: DataMaskStateWithId;
  appliedFilters: FilterInfo[];
  customLabel?: string;
}

const STORAGE_KEY_PREFIX = 'superset_filter_history_';
const MAX_HISTORY_ENTRIES = 20; // Maximum number of history entries per dashboard

/**
 * Get the storage key for a specific dashboard
 */
const getStorageKey = (dashboardId: number): string =>
  `${STORAGE_KEY_PREFIX}${dashboardId}`;

/**
 * Get filter history for a specific dashboard
 */
export const getFilterHistory = (dashboardId: number): FilterHistoryEntry[] => {
  try {
    const key = getStorageKey(dashboardId);
    const stored = sessionStorage.getItem(key);
    if (!stored) {
      return [];
    }
    return JSON.parse(stored) as FilterHistoryEntry[];
  } catch (error) {
    console.error('Error reading filter history from storage:', error);
    return [];
  }
};

/**
 * Save a new filter history entry
 */
export const saveFilterHistory = (
  dashboardId: number,
  dataMask: DataMaskStateWithId,
  appliedFilters: FilterInfo[],
): void => {
  try {
    const history = getFilterHistory(dashboardId);
    const newEntry: FilterHistoryEntry = {
      id: `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      timestamp: Date.now(),
      dataMask,
      appliedFilters,
    };

    // Add new entry at the beginning
    const updatedHistory = [newEntry, ...history];

    // Keep only the most recent entries
    const trimmedHistory = updatedHistory.slice(0, MAX_HISTORY_ENTRIES);

    const key = getStorageKey(dashboardId);
    sessionStorage.setItem(key, JSON.stringify(trimmedHistory));
  } catch (error) {
    console.error('Error saving filter history to storage:', error);
  }
};

/**
 * Clear all filter history for a specific dashboard
 */
export const clearFilterHistory = (dashboardId: number): void => {
  try {
    const key = getStorageKey(dashboardId);
    sessionStorage.removeItem(key);
  } catch (error) {
    console.error('Error clearing filter history from storage:', error);
  }
};

/**
 * Delete a specific history entry
 */
export const deleteFilterHistoryEntry = (
  dashboardId: number,
  entryId: string,
): void => {
  try {
    const history = getFilterHistory(dashboardId);
    const updatedHistory = history.filter(entry => entry.id !== entryId);
    const key = getStorageKey(dashboardId);
    sessionStorage.setItem(key, JSON.stringify(updatedHistory));
  } catch (error) {
    console.error('Error deleting filter history entry:', error);
  }
};

/**
 * Update the custom label for a specific history entry
 */
export const updateFilterHistoryLabel = (
  dashboardId: number,
  entryId: string,
  customLabel: string,
): void => {
  try {
    const history = getFilterHistory(dashboardId);
    const updatedHistory = history.map(entry =>
      entry.id === entryId ? { ...entry, customLabel } : entry,
    );
    const key = getStorageKey(dashboardId);
    sessionStorage.setItem(key, JSON.stringify(updatedHistory));
  } catch (error) {
    console.error('Error updating filter history label:', error);
  }
};
