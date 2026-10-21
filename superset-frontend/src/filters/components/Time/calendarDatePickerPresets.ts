/**
 * Calendar-based preset values for the dashboard time filter.
 *
 * Superset resolves these via `get_since_until` in `superset/utils/date_parser.py`:
 * - "Current week/month/year" → DATETRUNC calendar periods
 * - "previous calendar week/month/year" → previous full calendar period (week starts Monday)
 *
 * Legacy rolling presets ("Last week", etc.) are normalized on apply for existing dashboards.
 */
import { Dayjs } from 'dayjs';
import { NO_TIME_RANGE } from '@superset-ui/core';
import { extendedDayjs } from '@superset-ui/core/utils/dates';
import { t } from '@apache-superset/core/translation';
import {
  CurrentDay,
  CurrentMonth,
  CurrentWeek,
  CurrentYear,
  PreviousCalendarMonth,
  PreviousCalendarWeek,
  PreviousCalendarYear,
} from 'src/explore/components/controls/DateFilterControl/types';

/** Rolling preset strings saved before calendar preset migration. */
export const LEGACY_ROLLING_TO_CALENDAR: Record<string, string> = {
  'Last week': PreviousCalendarWeek,
  'Last month': PreviousCalendarMonth,
  'Last year': PreviousCalendarYear,
};

export function normalizeCalendarPresetValue(value: string): string {
  return LEGACY_ROLLING_TO_CALENDAR[value] ?? value;
}

export function isCalendarPresetActive(
  currentValue: string,
  presetValue: string,
): boolean {
  return (
    currentValue === presetValue ||
    normalizeCalendarPresetValue(currentValue) === presetValue
  );
}

export const CALENDAR_DATE_PICKER_PRESET_VALUES = {
  previousWeek: PreviousCalendarWeek,
  previousMonth: PreviousCalendarMonth,
  previousYear: PreviousCalendarYear,
  currentDay: CurrentDay,
  currentWeek: CurrentWeek,
  currentMonth: CurrentMonth,
  currentYear: CurrentYear,
} as const;

export const CALENDAR_DATE_PICKER_PRESETS = [
  { label: t('No filter'), value: NO_TIME_RANGE },
  { label: t('Today'), value: CALENDAR_DATE_PICKER_PRESET_VALUES.currentDay },
  {
    label: t('This week'),
    value: CALENDAR_DATE_PICKER_PRESET_VALUES.currentWeek,
  },
  {
    label: t('This month'),
    value: CALENDAR_DATE_PICKER_PRESET_VALUES.currentMonth,
  },
  {
    label: t('This year'),
    value: CALENDAR_DATE_PICKER_PRESET_VALUES.currentYear,
  },
  {
    label: t('Previous week'),
    value: CALENDAR_DATE_PICKER_PRESET_VALUES.previousWeek,
  },
  {
    label: t('Previous month'),
    value: CALENDAR_DATE_PICKER_PRESET_VALUES.previousMonth,
  },
  {
    label: t('Previous year'),
    value: CALENDAR_DATE_PICKER_PRESET_VALUES.previousYear,
  },
];

export function getCalendarPresetLabel(value: string): string | null {
  const normalized = normalizeCalendarPresetValue(value);
  const preset = CALENDAR_DATE_PICKER_PRESETS.find(
    ({ value: presetValue }) => presetValue === normalized,
  );
  return preset?.label ?? null;
}

/** Monday-start week, matching Superset calendar presets. */
function startOfMondayWeek(date: Dayjs): Dayjs {
  const daysFromMonday = (date.day() + 6) % 7;
  return date.subtract(daysFromMonday, 'day');
}

export function getPresetDates(presetValue: string): [Dayjs, Dayjs] | null {
  const today = extendedDayjs().startOf('day');
  const currentWeekStart = startOfMondayWeek(today);
  const currentMonthStart = today.startOf('month');
  const currentYearStart = today.startOf('year');

  switch (presetValue) {
    case CALENDAR_DATE_PICKER_PRESET_VALUES.currentDay:
      return [today, today];
    case CALENDAR_DATE_PICKER_PRESET_VALUES.currentWeek:
      return [
        currentWeekStart,
        currentWeekStart.add(1, 'week').subtract(1, 'day'),
      ];
    case CALENDAR_DATE_PICKER_PRESET_VALUES.currentMonth:
      return [
        currentMonthStart,
        currentMonthStart.add(1, 'month').subtract(1, 'day'),
      ];
    case CALENDAR_DATE_PICKER_PRESET_VALUES.currentYear:
      return [
        currentYearStart,
        currentYearStart.add(1, 'year').subtract(1, 'day'),
      ];
    case CALENDAR_DATE_PICKER_PRESET_VALUES.previousWeek:
      return [
        currentWeekStart.subtract(1, 'week'),
        currentWeekStart.subtract(1, 'day'),
      ];
    case CALENDAR_DATE_PICKER_PRESET_VALUES.previousMonth:
      return [
        currentMonthStart.subtract(1, 'month'),
        currentMonthStart.subtract(1, 'day'),
      ];
    case CALENDAR_DATE_PICKER_PRESET_VALUES.previousYear:
      return [
        currentYearStart.subtract(1, 'year'),
        currentYearStart.subtract(1, 'day'),
      ];
    default:
      return null;
  }
}
