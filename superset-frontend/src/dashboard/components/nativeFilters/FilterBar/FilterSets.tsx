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
import { DataMaskStateWithId } from '@superset-ui/core';
import { css, SupersetTheme } from '@apache-superset/core/theme';
import { t } from '@apache-superset/core/translation';
import { Button, Modal } from '@superset-ui/core/components';
import { Icons } from '@superset-ui/core/components/Icons';
import { Empty, Spin } from 'antd';
import {
  getFilterSets,
  deleteFilterSetEntry,
  updateFilterSetLabel,
  FilterSetEntry,
} from './filterSetsStorage';

interface FilterSetsProps {
  isOpen: boolean;
  onClose: () => void;
  dashboardId: number;
  onApplyFilterSet: (dataMask: DataMaskStateWithId) => void;
}

const containerStyle = (theme: SupersetTheme) => css`
  max-height: 500px;
  overflow-y: auto;
  padding: ${theme.sizeUnit * 2}px 0;
`;

const itemStyle = (theme: SupersetTheme) => css`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: ${theme.sizeUnit * 3}px ${theme.sizeUnit * 4}px;
  border-bottom: 1px solid ${theme.colorBorderSecondary};
  cursor: pointer;
  transition: background-color 0.2s;

  &:hover {
    background-color: ${theme.colorFillSecondary};
  }

  &:last-child {
    border-bottom: none;
  }
`;

const itemInfoStyle = (theme: SupersetTheme) => css`
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: ${theme.sizeUnit}px;
`;

const labelStyle = (theme: SupersetTheme) => css`
  font-size: ${theme.fontSizeSM}px;
  color: ${theme.colorTextSecondary};
  font-weight: ${theme.fontWeightStrong};
`;

const filtersListStyle = (theme: SupersetTheme) => css`
  font-size: ${theme.fontSizeXS}px;
  color: ${theme.colorTextTertiary};
  display: flex;
  flex-direction: column;
  gap: ${theme.sizeUnit}px;
`;

const filterItemStyle = (theme: SupersetTheme) => css`
  display: flex;
  gap: ${theme.sizeUnit}px;
  align-items: baseline;
`;

const filterNameStyle = (theme: SupersetTheme) => css`
  font-weight: ${theme.fontWeightStrong};
  color: ${theme.colorText};
`;

const filterValueStyle = (theme: SupersetTheme) => css`
  color: ${theme.colorTextSecondary};
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
  padding: ${theme.sizeUnit * 10}px;
  text-align: center;
`;

const labelContainerStyle = (theme: SupersetTheme) => css`
  display: flex;
  align-items: center;
  gap: ${theme.sizeUnit}px;

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
  color: ${theme.colorTextSecondary};
  display: flex;
  align-items: center;
  background: ${theme.colorFillTertiary};
  border: 1px solid ${theme.colorBorderSecondary};
  border-radius: ${theme.borderRadius}px;
  padding: ${theme.sizeUnit}px;
  transition: all 0.2s;

  &:hover {
    color: ${theme.colorPrimary};
    border-color: ${theme.colorPrimaryBorder};
    background: ${theme.colorPrimaryBg};
  }
`;

const labelInputStyle = (theme: SupersetTheme) => css`
  font-size: ${theme.fontSizeSM}px;
  font-weight: ${theme.fontWeightStrong};
  padding: ${theme.sizeUnit}px;
  border: 1px solid ${theme.colorPrimary};
  border-radius: ${theme.borderRadius}px;
  outline: none;
  min-width: 200px;
`;

const formatTimestamp = (timestamp: number): string => {
  const date = new Date(timestamp);
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
  return `${date.toLocaleDateString(
    undefined,
    dateOptions,
  )}, ${date.toLocaleTimeString(undefined, timeOptions)}`;
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

const FilterSets = ({
  isOpen,
  onClose,
  dashboardId,
  onApplyFilterSet,
}: FilterSetsProps) => {
  const [filterSets, setFilterSets] = useState<FilterSetEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editingEntryId, setEditingEntryId] = useState<string | null>(null);
  const [editingLabel, setEditingLabel] = useState<string>('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setIsLoading(true);
      setLoadError(null);
      getFilterSets(dashboardId)
        .then(sets => {
          setFilterSets(sets);
        })
        .catch(err => {
          setLoadError(t('Failed to load saved filters'));
          console.error('Error loading filter sets:', err);
        })
        .finally(() => {
          setIsLoading(false);
        });
    }
  }, [isOpen, dashboardId]);

  useEffect(() => {
    if (editingEntryId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingEntryId]);

  const handleApply = (entry: FilterSetEntry) => {
    onApplyFilterSet(entry.dataMask);
    onClose();
  };

  const handleDelete = (e: React.MouseEvent, entryId: string) => {
    e.stopPropagation();
    deleteFilterSetEntry(dashboardId, entryId)
      .then(() => {
        setFilterSets(prev => prev.filter(e => e.id !== entryId));
      })
      .catch(err => {
        console.error('Error deleting filter set:', err);
      });
  };

  const handleStartEdit = (e: React.MouseEvent, entry: FilterSetEntry) => {
    e.stopPropagation();
    setEditingEntryId(entry.id);
    setEditingLabel(entry.customLabel || formatTimestamp(entry.timestamp));
  };

  const handleSaveLabel = (entryId: string) => {
    const trimmedLabel = editingLabel.trim();
    if (trimmedLabel) {
      updateFilterSetLabel(dashboardId, entryId, trimmedLabel)
        .then(() => {
          setFilterSets(prev =>
            prev.map(e =>
              e.id === entryId ? { ...e, customLabel: trimmedLabel } : e,
            ),
          );
        })
        .catch(err => {
          console.error('Error updating filter set label:', err);
        });
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

  const renderContent = () => {
    if (isLoading) {
      return (
        <div css={emptyStateStyle}>
          <Spin size="large" />
        </div>
      );
    }
    if (loadError) {
      return (
        <div css={emptyStateStyle}>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={loadError} />
        </div>
      );
    }
    if (filterSets.length === 0) {
      return (
        <div css={emptyStateStyle}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t('No saved filters yet')}
          />
        </div>
      );
    }
    return filterSets.map(entry => (
      <div
        key={entry.id}
        css={itemStyle}
        onClick={() => handleApply(entry)}
        role="button"
        tabIndex={0}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            handleApply(entry);
          }
        }}
      >
        <div css={itemInfoStyle}>
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
            <div css={labelContainerStyle}>
              <div css={labelStyle}>
                {entry.customLabel || formatTimestamp(entry.timestamp)}
              </div>
              <button
                type="button"
                className="edit-icon"
                css={editIconStyle}
                onClick={e => handleStartEdit(e, entry)}
                aria-label={t('Edit label')}
              >
                <Icons.EditOutlined iconSize="m" />
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
          <Icons.DeleteOutlined iconSize="l" />
        </button>
      </div>
    ));
  };

  return (
    <Modal
      show={isOpen}
      onHide={onClose}
      title={t('Saved filters')}
      footer={
        <Button onClick={onClose} buttonStyle="primary">
          {t('Close')}
        </Button>
      }
      width="600px"
    >
      <div css={containerStyle}>{renderContent()}</div>
    </Modal>
  );
};

export default FilterSets;
