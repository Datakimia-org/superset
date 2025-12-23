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
import { useState, useEffect, useRef } from 'react';
import { css, SupersetTheme, t, DataMaskStateWithId } from '@superset-ui/core';
import Modal from 'src/components/Modal';
import Button from 'src/components/Button';
import { Empty } from 'antd';
import Icons from 'src/components/Icons';
import {
  getFilterHistory,
  deleteFilterHistoryEntry,
  updateFilterHistoryLabel,
  FilterHistoryEntry,
} from './filterHistoryStorage';

interface FilterHistoryProps {
  isOpen: boolean;
  onClose: () => void;
  dashboardId: number;
  onApplyHistory: (dataMask: DataMaskStateWithId) => void;
}

const historyContainerStyle = (theme: SupersetTheme) => css`
  max-height: 500px;
  overflow-y: auto;
  padding: ${theme.gridUnit * 2}px 0;
`;

const historyItemStyle = (theme: SupersetTheme) => css`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: ${theme.gridUnit * 3}px ${theme.gridUnit * 4}px;
  border-bottom: 1px solid ${theme.colors.grayscale.light2};
  cursor: pointer;
  transition: background-color 0.2s;

  &:hover {
    background-color: ${theme.colors.grayscale.light4};
  }

  &:last-child {
    border-bottom: none;
  }
`;

const historyItemInfoStyle = (theme: SupersetTheme) => css`
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: ${theme.gridUnit}px;
`;

const timestampStyle = (theme: SupersetTheme) => css`
  font-size: ${theme.typography.sizes.s}px;
  color: ${theme.colors.grayscale.base};
  font-weight: ${theme.typography.weights.bold};
`;

const filtersListStyle = (theme: SupersetTheme) => css`
  font-size: ${theme.typography.sizes.xs}px;
  color: ${theme.colors.grayscale.light1};
  display: flex;
  flex-direction: column;
  gap: ${theme.gridUnit}px;
`;

const filterItemStyle = (theme: SupersetTheme) => css`
  display: flex;
  gap: ${theme.gridUnit}px;
  align-items: baseline;
`;

const filterNameStyle = (theme: SupersetTheme) => css`
  font-weight: ${theme.typography.weights.bold};
  color: ${theme.colors.grayscale.dark1};
`;

const filterValueStyle = (theme: SupersetTheme) => css`
  color: ${theme.colors.grayscale.base};
  font-style: italic;
`;

const deleteButtonStyle = css`
  margin-left: auto;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
`;

const emptyStateStyle = (theme: SupersetTheme) => css`
  padding: ${theme.gridUnit * 10}px;
  text-align: center;
`;

const timestampContainerStyle = (theme: SupersetTheme) => css`
  display: flex;
  align-items: center;
  gap: ${theme.gridUnit}px;

  .edit-icon {
    opacity: 0;
    transition: opacity 0.2s;
  }

  &:hover .edit-icon {
    opacity: 1;
  }
`;

const editIconStyle = (theme: SupersetTheme) => css`
  cursor: pointer;
  color: ${theme.colors.grayscale.base};
  display: flex;
  align-items: center;
  background: ${theme.colors.grayscale.light5};
  border: 1px solid ${theme.colors.grayscale.light2};
  border-radius: ${theme.borderRadius}px;
  padding: ${theme.gridUnit}px;
  transition: all 0.2s;

  &:hover {
    color: ${theme.colors.primary.base};
    border-color: ${theme.colors.primary.light1};
    background: ${theme.colors.primary.light5};
  }
`;

const labelInputStyle = (theme: SupersetTheme) => css`
  font-size: ${theme.typography.sizes.s}px;
  font-weight: ${theme.typography.weights.bold};
  padding: ${theme.gridUnit}px;
  border: 1px solid ${theme.colors.primary.base};
  border-radius: ${theme.borderRadius}px;
  outline: none;
  min-width: 200px;
`;

const formatTimestamp = (timestamp: number): string => {
  const date = new Date(timestamp);

  // Use browser's locale settings to format date and time
  const dateOptions: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  };

  const timeOptions: Intl.DateTimeFormatOptions = {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  };

  const formattedDate = date.toLocaleDateString(undefined, dateOptions);
  const formattedTime = date.toLocaleTimeString(undefined, timeOptions);

  return `${formattedDate}, ${formattedTime}`;
};

const formatFilterValue = (value: any): string => {
  if (Array.isArray(value)) {
    return value.join(', ');
  }
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value);
  }
  return String(value);
};

const FilterHistory = ({
  isOpen,
  onClose,
  dashboardId,
  onApplyHistory,
}: FilterHistoryProps) => {
  const [history, setHistory] = useState<FilterHistoryEntry[]>([]);
  const [editingEntryId, setEditingEntryId] = useState<string | null>(null);
  const [editingLabel, setEditingLabel] = useState<string>('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      const loadedHistory = getFilterHistory(dashboardId);
      setHistory(loadedHistory);
    }
  }, [isOpen, dashboardId]);

  useEffect(() => {
    if (editingEntryId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingEntryId]);

  const handleApply = (entry: FilterHistoryEntry) => {
    onApplyHistory(entry.dataMask);
    onClose();
  };

  const handleDelete = (e: React.MouseEvent, entryId: string) => {
    e.stopPropagation();
    deleteFilterHistoryEntry(dashboardId, entryId);
    const updatedHistory = history.filter(entry => entry.id !== entryId);
    setHistory(updatedHistory);
  };

  const handleStartEdit = (e: React.MouseEvent, entry: FilterHistoryEntry) => {
    e.stopPropagation();
    setEditingEntryId(entry.id);
    setEditingLabel(entry.customLabel || formatTimestamp(entry.timestamp));
  };

  const handleSaveLabel = (entryId: string) => {
    const trimmedLabel = editingLabel.trim();
    if (trimmedLabel) {
      updateFilterHistoryLabel(dashboardId, entryId, trimmedLabel);
      const updatedHistory = history.map(entry =>
        entry.id === entryId ? { ...entry, customLabel: trimmedLabel } : entry,
      );
      setHistory(updatedHistory);
    }
    setEditingEntryId(null);
    setEditingLabel('');
  };

  const handleCancelEdit = () => {
    setEditingEntryId(null);
    setEditingLabel('');
  };

  const handleKeyDown = (e: React.KeyboardEvent, entryId: string) => {
    e.stopPropagation();
    if (e.key === 'Enter') {
      handleSaveLabel(entryId);
    } else if (e.key === 'Escape') {
      handleCancelEdit();
    }
  };

  return (
    <Modal
      show={isOpen}
      onHide={onClose}
      title={t('Filter History')}
      footer={
        <Button onClick={onClose} buttonStyle="primary">
          {t('Close')}
        </Button>
      }
      width="600px"
    >
      <div css={historyContainerStyle}>
        {history.length === 0 ? (
          <div css={emptyStateStyle}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('No filter history available')}
            />
          </div>
        ) : (
          history.map(entry => (
            <div
              key={entry.id}
              css={historyItemStyle}
              onClick={() => handleApply(entry)}
              role="button"
              tabIndex={0}
              onKeyDown={e => {
                if (e.key === 'Enter' || e.key === ' ') {
                  handleApply(entry);
                }
              }}
            >
              <div css={historyItemInfoStyle}>
                {editingEntryId === entry.id ? (
                  <input
                    ref={inputRef}
                    type="text"
                    css={labelInputStyle}
                    value={editingLabel}
                    onChange={e => setEditingLabel(e.target.value)}
                    onBlur={() => handleSaveLabel(entry.id)}
                    onKeyDown={e => handleKeyDown(e, entry.id)}
                    maxLength={50}
                    onClick={e => e.stopPropagation()}
                  />
                ) : (
                  <div css={timestampContainerStyle}>
                    <div css={timestampStyle}>
                      {entry.customLabel || formatTimestamp(entry.timestamp)}
                    </div>
                    <button
                      type="button"
                      className="edit-icon"
                      css={editIconStyle}
                      onClick={e => handleStartEdit(e, entry)}
                      aria-label={t('Edit label')}
                    >
                      <Icons.EditAlt iconSize="m" />
                    </button>
                  </div>
                )}
                <div css={filtersListStyle}>
                  {entry.appliedFilters && entry.appliedFilters.length > 0 ? (
                    entry.appliedFilters.map(filter => (
                      <div key={filter.id} css={filterItemStyle}>
                        <span css={filterNameStyle}>{filter.name}:</span>
                        <span css={filterValueStyle}>
                          {formatFilterValue(filter.value)}
                        </span>
                      </div>
                    ))
                  ) : (
                    <span>{t('No filters applied')}</span>
                  )}
                </div>
              </div>
              <button
                type="button"
                css={deleteButtonStyle}
                onClick={e => handleDelete(e, entry.id)}
                aria-label={t('Delete')}
              >
                <Icons.Trash iconSize="l" />
              </button>
            </div>
          ))
        )}
      </div>
    </Modal>
  );
};

export default FilterHistory;
