import { useState, useEffect } from 'react';
import { Dayjs } from 'dayjs';
import {
  fetchTimeRange,
  NO_TIME_RANGE,
  useCSSTextTruncation,
} from '@superset-ui/core';
import { extendedDayjs } from '@superset-ui/core/utils/dates';
import { styled, useTheme } from '@apache-superset/core/theme';
import { t } from '@apache-superset/core/translation';
import {
  Button,
  RangePicker,
  Tooltip,
  type RangePickerProps,
} from '@superset-ui/core/components';
import ControlPopover from 'src/explore/components/controls/ControlPopover/ControlPopover';
import { DateLabel } from 'src/explore/components/controls/DateFilterControl/components';
import { DAYJS_FORMAT } from 'src/explore/components/controls/DateFilterControl/utils';
import { Icons } from '@superset-ui/core/components/Icons';
import {
  CALENDAR_DATE_PICKER_PRESETS,
  getCalendarPresetLabel,
  getPresetDates,
  isCalendarPresetActive,
  normalizeCalendarPresetValue,
} from './calendarDatePickerPresets';

export interface CalendarDatePickerProps {
  value: string;
  name?: string;
  onChange: (value: string) => void;
  onOpenPopover?: () => void;
  onClosePopover?: () => void;
  isOverflowingFilterBar?: boolean;
}

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
    border-right: 1px solid ${({ theme }) => theme.colorBorderSecondary};
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
    border-top: 1px solid ${({ theme }) => theme.colorBorderSecondary};
  }

  .preset-btn {
    text-align: left;
    background: transparent;
    border: none;
    cursor: pointer;
    padding: 6px 12px;
    border-radius: ${({ theme }) => theme.borderRadius}px;
    color: ${({ theme }) => theme.colorText};
    font-size: ${({ theme }) => theme.fontSizeSM}px;
    transition: background 0.2s;

    &:hover {
      background: ${({ theme }) => theme.colorFillSecondary};
    }
    &.active {
      background: ${({ theme }) => theme.colorPrimaryBg};
      color: ${({ theme }) => theme.colorPrimary};
      font-weight: ${({ theme }) => theme.fontWeightStrong};
    }
  }
`;

/** Calendar day from UTC date parts, so the picker does not shift across timezones. */
function utcPartsToLocalDay(utcDate: Dayjs): Dayjs {
  return extendedDayjs(
    new Date(utcDate.year(), utcDate.month(), utcDate.date()),
  );
}

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
    setTempValue(normalizeCalendarPresetValue(value));
    setShow(true);
    onOpenPopover?.();
  };

  const handleClose = () => {
    setShow(false);
    onClosePopover?.();
  };

  const handleApply = () => {
    onChange(normalizeCalendarPresetValue(tempValue));
    handleClose();
  };

  // Determine if tempValue is a custom range
  const isCustom = tempValue.includes(' : ');
  let customDates: [Dayjs, Dayjs] | null = getPresetDates(tempValue);
  if (isCustom) {
    const parts = tempValue.split(' : ');
    if (parts.length === 2) {
      const startUtc = extendedDayjs.utc(parts[0]);
      const untilUtc = extendedDayjs.utc(parts[1]);
      if (startUtc.isValid() && untilUtc.isValid()) {
        const start = utcPartsToLocalDay(startUtc);
        let endUtc = untilUtc;
        if (parts[1].endsWith('T00:00:00')) {
          endUtc = untilUtc.subtract(1, 'day');
        } else if (parts[1].endsWith('T23:59:59')) {
          endUtc = untilUtc.startOf('day');
        }
        const end = utcPartsToLocalDay(endUtc);
        customDates = [start, end];
      }
    }
  }

  const handleCustomChange: RangePickerProps['onChange'] = dates => {
    const [startDate, endDate] = dates ?? [];
    if (startDate && endDate) {
      const start = startDate.startOf('day').format(DAYJS_FORMAT);
      const until = endDate.startOf('day').add(1, 'day').format(DAYJS_FORMAT);
      setTempValue(`${start} : ${until}`);
    } else {
      setTempValue(NO_TIME_RANGE);
    }
  };

  const overlayContent = (
    <PopoverContainer>
      <div className="content">
        <div className="presets">
          <strong>{t('Presets')}</strong>
          {CALENDAR_DATE_PICKER_PRESETS.map(preset => (
            <button
              key={preset.value}
              type="button"
              className={`preset-btn ${
                isCalendarPresetActive(tempValue, preset.value) ? 'active' : ''
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
            // dayjs only. Moment `.add()` mutates, so each cell walks years ahead.
            value={customDates}
            onChange={handleCustomChange}
            allowClear={false}
          />
          <div
            style={{
              marginTop: 16,
              fontSize: '12px',
              color: theme.colorTextSecondary,
            }}
          >
            {t('Selected')}:{' '}
            <strong>
              {tempValue === NO_TIME_RANGE
                ? t('No filter')
                : (getCalendarPresetLabel(tempValue) ?? tempValue)}
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
          <Icons.EditOutlined
            iconColor={theme.colorTextSecondary}
            style={{ marginRight: 8 }}
          />
          {t('Edit time range')}
        </span>
      }
      open={show}
      onOpenChange={open => (open ? handleOpen() : handleClose())}
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
