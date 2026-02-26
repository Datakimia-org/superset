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
import { useEffect, useRef, useState } from 'react';
import { css, SupersetTheme, t } from '@superset-ui/core';
import Modal from 'src/components/Modal';
import Button from 'src/components/Button';
import { Input } from 'src/components/Input';
import { FilterInfo } from './filterSetsStorage';

interface SaveFilterModalProps {
  isOpen: boolean;
  appliedFilters: FilterInfo[];
  onConfirm: (label: string) => void;
  onClose: () => void;
}

const formatFilterValue = (value: any): string => {
  if (Array.isArray(value)) {
    return value.join(', ');
  }
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value);
  }
  return String(value);
};

const bodyStyle = (theme: SupersetTheme) => css`
  display: flex;
  flex-direction: column;
  gap: ${theme.gridUnit * 4}px;
`;

const fieldStyle = (theme: SupersetTheme) => css`
  display: flex;
  flex-direction: column;
  gap: ${theme.gridUnit}px;

  label {
    font-size: ${theme.typography.sizes.s}px;
    font-weight: ${theme.typography.weights.bold};
    color: ${theme.colors.grayscale.dark1};
  }
`;

const filtersSummaryStyle = (theme: SupersetTheme) => css`
  background: ${theme.colors.grayscale.light4};
  border-radius: ${theme.borderRadius}px;
  padding: ${theme.gridUnit * 3}px;
  display: flex;
  flex-direction: column;
  gap: ${theme.gridUnit * 2}px;

  .summary-title {
    font-size: ${theme.typography.sizes.s}px;
    font-weight: ${theme.typography.weights.bold};
    color: ${theme.colors.grayscale.dark1};
    margin-bottom: ${theme.gridUnit}px;
  }
`;

const filterRowStyle = (theme: SupersetTheme) => css`
  font-size: ${theme.typography.sizes.s}px;
  display: flex;
  gap: ${theme.gridUnit}px;
  align-items: baseline;

  .filter-name {
    font-weight: ${theme.typography.weights.bold};
    color: ${theme.colors.grayscale.dark2};
  }

  .filter-value {
    color: ${theme.colors.grayscale.base};
    font-style: italic;
  }
`;

const SaveFilterModal = ({
  isOpen,
  appliedFilters,
  onConfirm,
  onClose,
}: SaveFilterModalProps) => {
  const [label, setLabel] = useState('');
  const inputRef = useRef<any>(null);

  useEffect(() => {
    if (isOpen) {
      setLabel('');
      // Small timeout to allow the modal to render before focusing
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  const handleConfirm = () => {
    onConfirm(label.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleConfirm();
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <Modal
      show={isOpen}
      onHide={onClose}
      title={t('Save filter set')}
      footer={
        <>
          <Button onClick={onClose} buttonStyle="secondary">
            {t('Cancel')}
          </Button>
          <Button onClick={handleConfirm} buttonStyle="primary">
            {t('Save')}
          </Button>
        </>
      }
      width="480px"
    >
      <div css={bodyStyle}>
        <div css={fieldStyle}>
          <label htmlFor="save-filter-label">{t('Name (optional)')}</label>
          <Input
            ref={inputRef}
            id="save-filter-label"
            value={label}
            onChange={e => setLabel(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('e.g. Q1 filters, My region view…')}
            maxLength={50}
          />
        </div>
        {appliedFilters.length > 0 && (
          <div css={filtersSummaryStyle}>
            <div className="summary-title">{t('Filters being saved')}</div>
            {appliedFilters.map(filter => (
              <div key={filter.id} css={filterRowStyle}>
                <span className="filter-name">{filter.name}:</span>
                <span className="filter-value">
                  {formatFilterValue(filter.value)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
};

export default SaveFilterModal;
