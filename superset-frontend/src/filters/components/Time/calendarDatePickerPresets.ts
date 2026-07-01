/**
 * Calendar-based preset values for the dashboard time filter.
 *
 * Superset resolves these via `get_since_until` in `superset/utils/date_parser.py`:
 * - "Current week/month/year" → DATETRUNC calendar periods
 * - "previous calendar week/month/year" → previous full calendar period (week starts Monday)
 *
 * Legacy rolling presets ("Last week", etc.) are normalized on apply for existing dashboards.
 */
import moment, { Moment } from 'moment';
import { NO_TIME_RANGE, t } from '@superset-ui/core';
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
    label: t('Last week'),
    value: CALENDAR_DATE_PICKER_PRESET_VALUES.previousWeek,
  },
  {
    label: t('Last month'),
    value: CALENDAR_DATE_PICKER_PRESET_VALUES.previousMonth,
  },
  {
    label: t('Last year'),
    value: CALENDAR_DATE_PICKER_PRESET_VALUES.previousYear,
  },
];

export function getPresetDates(presetValue: string): [Moment, Moment] | null {
  const today = moment().startOf('day');
  const currentWeekStart = today.clone().startOf('isoWeek');
  const currentMonthStart = today.clone().startOf('month');
  const currentYearStart = today.clone().startOf('year');

  switch (presetValue) {
    case CALENDAR_DATE_PICKER_PRESET_VALUES.currentDay:
      return [today.clone(), today.clone()];
    case CALENDAR_DATE_PICKER_PRESET_VALUES.currentWeek:
      return [
        currentWeekStart.clone(),
        currentWeekStart.clone().add(1, 'week').subtract(1, 'day'),
      ];
    case CALENDAR_DATE_PICKER_PRESET_VALUES.currentMonth:
      return [
        currentMonthStart.clone(),
        currentMonthStart.clone().add(1, 'month').subtract(1, 'day'),
      ];
    case CALENDAR_DATE_PICKER_PRESET_VALUES.currentYear:
      return [
        currentYearStart.clone(),
        currentYearStart.clone().add(1, 'year').subtract(1, 'day'),
      ];
    case CALENDAR_DATE_PICKER_PRESET_VALUES.previousWeek:
      return [
        currentWeekStart.clone().subtract(1, 'week'),
        currentWeekStart.clone().subtract(1, 'day'),
      ];
    case CALENDAR_DATE_PICKER_PRESET_VALUES.previousMonth:
      return [
        currentMonthStart.clone().subtract(1, 'month'),
        currentMonthStart.clone().subtract(1, 'day'),
      ];
    case CALENDAR_DATE_PICKER_PRESET_VALUES.previousYear:
      return [
        currentYearStart.clone().subtract(1, 'year'),
        currentYearStart.clone().subtract(1, 'day'),
      ];
    default:
      return null;
  }
}
