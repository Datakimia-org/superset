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
import {
  Button,
  RangePicker,
  Tooltip,
} from '@superset-ui/core/components';
import ControlPopover from 'src/explore/components/controls/ControlPopover/ControlPopover';
import { DateLabel } from 'src/explore/components/controls/DateFilterControl/components';
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
  let customDates: [Moment, Moment] | null = getPresetDates(tempValue);
  if (isCustom) {
    const parts = tempValue.split(' : ');
    if (parts.length === 2) {
      const startUtc = moment.utc(parts[0]);
      const untilUtc = moment.utc(parts[1]);
      if (startUtc.isValid() && untilUtc.isValid()) {
        const start = moment([
          startUtc.year(),
          startUtc.month(),
          startUtc.date(),
        ]);
        let endUtc = untilUtc;
        if (parts[1].endsWith('T00:00:00')) {
          endUtc = untilUtc.clone().subtract(1, 'day');
        } else if (parts[1].endsWith('T23:59:59')) {
          endUtc = untilUtc.clone().startOf('day');
        }
        const end = moment([endUtc.year(), endUtc.month(), endUtc.date()]);
        customDates = [start, end];
      }
    }
  }

  const handleCustomChange = (dates: [Moment, Moment] | null) => {
    if (dates && dates.length === 2) {
      const start = dates[0].clone().startOf('day').format(MOMENT_FORMAT);
      const until = dates[1]
        .clone()
        .startOf('day')
        .add(1, 'day')
        .format(MOMENT_FORMAT);
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
            value={customDates as any}
            onChange={handleCustomChange as any}
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
                : getCalendarPresetLabel(tempValue) ?? tempValue}
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
