import { useState, useEffect } from 'react';
import moment, { Moment } from 'moment';
import {
  styled,
  t,
  fetchTimeRange,
  NO_TIME_RANGE,
  useTheme,
  useCSSTextTruncation,
} from '@superset-ui/core';
import { RangePicker } from 'src/components/DatePicker';
import Button from 'src/components/Button';
import ControlPopover from 'src/explore/components/controls/ControlPopover/ControlPopover';
import { DateLabel } from 'src/explore/components/controls/DateFilterControl/components';
import { Tooltip } from 'src/components/Tooltip';
import Icons from 'src/components/Icons';

export interface CalendarDatePickerProps {
  value: string;
  name?: string;
  onChange: (value: string) => void;
  onOpenPopover?: () => void;
  onClosePopover?: () => void;
  isOverflowingFilterBar?: boolean;
}

const MOMENT_FORMAT = 'YYYY-MM-DD[T]HH:mm:ss';

const PopoverContainer = styled.div`
  display: flex;
  flex-direction: column;

  .content {
    display: flex;
    flex-direction: row;
    gap: 16px;
    margin-bottom: 16px;
  }

  .presets {
    display: flex;
    flex-direction: column;
    gap: 8px;
    border-right: 1px solid ${({ theme }) => theme.colors.grayscale.light2};
    padding-right: 16px;
    min-width: 150px;
  }

  .picker {
    display: flex;
    flex-direction: column;
    flex: 1;
    gap: 8px;
  }

  .footer {
    text-align: right;
    padding-top: 16px;
    border-top: 1px solid ${({ theme }) => theme.colors.grayscale.light2};
  }

  .preset-btn {
    text-align: left;
    background: transparent;
    border: none;
    cursor: pointer;
    padding: 6px 12px;
    border-radius: 4px;
    color: ${({ theme }) => theme.colors.grayscale.dark1};
    font-size: ${({ theme }) => theme.typography.sizes.s}px;
    transition: background 0.2s;

    &:hover {
      background: ${({ theme }) => theme.colors.grayscale.light4};
    }
    &.active {
      background: ${({ theme }) => theme.colors.primary.light4};
      color: ${({ theme }) => theme.colors.primary.dark1};
      font-weight: ${({ theme }) => theme.typography.weights.bold};
    }
  }
`;

const PRESETS = [
  { label: t('No filter'), value: NO_TIME_RANGE },
  { label: t('Today'), value: 'Current day' },
  { label: t('This week'), value: 'Current week' },
  { label: t('This month'), value: 'Current month' },
  { label: t('This year'), value: 'Current year' },
  { label: t('Last week'), value: 'Last week' },
  { label: t('Last month'), value: 'Last month' },
  { label: t('Last year'), value: 'Last year' },
];

export default function CalendarDatePicker({
  value,
  onChange,
  onOpenPopover,
  onClosePopover,
  isOverflowingFilterBar,
}: CalendarDatePickerProps) {
  const [show, setShow] = useState(false);
  const [tempValue, setTempValue] = useState(value);
  const [actualTimeRange, setActualTimeRange] = useState(value);
  const theme = useTheme();
  const [labelRef, labelIsTruncated] = useCSSTextTruncation<HTMLSpanElement>();

  useEffect(() => {
    if (value === NO_TIME_RANGE) {
      setActualTimeRange(t('No filter'));
      return;
    }
    fetchTimeRange(value).then(({ value: actualRange, error }) => {
      if (error) {
        setActualTimeRange(error);
      } else {
        setActualTimeRange(actualRange || value);
      }
    });
  }, [value]);

  const handleOpen = () => {
    setTempValue(value);
    setShow(true);
    onOpenPopover?.();
  };

  const handleClose = () => {
    setShow(false);
    onClosePopover?.();
  };

  const handleApply = () => {
    onChange(tempValue);
    handleClose();
  };

  // Determine if tempValue is a custom range
  const isCustom = tempValue.includes(' : ');
  let customDates: [Moment, Moment] | null = null;
  if (isCustom) {
    const parts = tempValue.split(' : ');
    if (parts.length === 2) {
      const start = moment(parts[0]);
      const end = moment(parts[1]);
      if (start.isValid() && end.isValid()) {
        customDates = [start, end];
      }
    }
  }

  const handleCustomChange = (dates: [Moment, Moment] | null) => {
    if (dates && dates.length === 2) {
      // Save exact dates the user picked, matching the old custom exact filter behavior
      const start = dates[0].startOf('day').format(MOMENT_FORMAT);
      const end = dates[1].endOf('day').format(MOMENT_FORMAT);
      setTempValue(`${start} : ${end}`);
    } else {
      setTempValue(NO_TIME_RANGE);
    }
  };

  const overlayContent = (
    <PopoverContainer>
      <div className="content">
        <div className="presets">
          <strong>{t('Presets')}</strong>
          {PRESETS.map(preset => (
            <button
              key={preset.value}
              type="button"
              className={`preset-btn ${
                tempValue === preset.value ? 'active' : ''
              }`}
              onClick={() => setTempValue(preset.value)}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <div className="picker">
          <strong>{t('Custom Range')}</strong>
          <RangePicker
            value={customDates as any}
            onChange={handleCustomChange as any}
            allowClear={false}
          />
          <div
            style={{
              marginTop: 16,
              fontSize: '12px',
              color: theme.colors.grayscale.base,
            }}
          >
            {t('Selected')}:{' '}
            <strong>
              {tempValue === NO_TIME_RANGE ? t('No filter') : tempValue}
            </strong>
          </div>
        </div>
      </div>
      <div className="footer">
        <Button
          buttonStyle="secondary"
          onClick={handleClose}
          data-test="date-filter-cancel"
        >
          {t('CANCEL')}
        </Button>
        <Button
          buttonStyle="primary"
          onClick={handleApply}
          style={{ marginLeft: 8 }}
          disabled={!tempValue}
          data-test="date-filter-apply"
        >
          {t('APPLY')}
        </Button>
      </div>
    </PopoverContainer>
  );

  return (
    <ControlPopover
      placement="right"
      trigger="click"
      content={overlayContent}
      title={
        <span
          style={{ fontWeight: 'bold', display: 'flex', alignItems: 'center' }}
        >
          <Icons.EditAlt
            iconColor={theme.colors.grayscale.base}
            style={{ marginRight: 8 }}
          />
          {t('Edit time range')}
        </span>
      }
      visible={show}
      onVisibleChange={visible => (visible ? handleOpen() : handleClose())}
      getPopupContainer={triggerNode =>
        isOverflowingFilterBar
          ? (triggerNode.parentNode as HTMLElement)
          : document.body
      }
    >
      <Tooltip
        placement="top"
        title={labelIsTruncated ? actualTimeRange : null}
        getPopupContainer={trigger => trigger.parentElement as HTMLElement}
      >
        <DateLabel
          label={value === NO_TIME_RANGE ? t('No filter') : actualTimeRange}
          isActive={show}
          isPlaceholder={value === NO_TIME_RANGE}
          ref={labelRef}
        />
      </Tooltip>
    </ControlPopover>
  );
}
