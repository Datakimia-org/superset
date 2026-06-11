/**
 * Calendar-based preset values for the dashboard time filter.
 *
 * Superset resolves these via `get_since_until` in `superset/utils/date_parser.py`:
 * - "Current week/month/year" → DATETRUNC calendar periods
 * - "previous calendar week/month/year" → previous full calendar period (week starts Monday)
 *
 * Legacy rolling presets ("Last week", etc.) are normalized on apply for existing dashboards.
 */
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
