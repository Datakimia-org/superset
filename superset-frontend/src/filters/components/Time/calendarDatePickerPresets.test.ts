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
import { extendedDayjs } from '@superset-ui/core/utils/dates';
import {
  CurrentDay,
  CurrentMonth,
  CurrentWeek,
  CurrentYear,
  PreviousCalendarMonth,
  PreviousCalendarWeek,
  PreviousCalendarYear,
} from 'src/explore/components/controls/DateFilterControl/types';
import { getPresetDates } from './calendarDatePickerPresets';

test('preset dates stay immutable so the calendar can add days safely', () => {
  const dates = getPresetDates(CurrentWeek);
  expect(dates).not.toBeNull();
  const [start, end] = dates!;
  const startIso = start.format('YYYY-MM-DD');
  const endIso = end.format('YYYY-MM-DD');

  start.add(400, 'year');
  end.add(3, 'month');

  expect(start.format('YYYY-MM-DD')).toBe(startIso);
  expect(end.format('YYYY-MM-DD')).toBe(endIso);
  expect(start.day()).toBe(1);
  expect(end.day()).toBe(0);
  expect(end.diff(start, 'day')).toBe(6);
  expect(Math.abs(start.diff(extendedDayjs(), 'day'))).toBeLessThan(8);
});

test('calendar presets cover the current and previous periods', () => {
  const today = extendedDayjs().startOf('day');
  const [dayStart, dayEnd] = getPresetDates(CurrentDay)!;
  expect(dayStart.isSame(today, 'day')).toBe(true);
  expect(dayEnd.isSame(today, 'day')).toBe(true);

  const [monthStart, monthEnd] = getPresetDates(CurrentMonth)!;
  expect(monthStart.isSame(today.startOf('month'), 'day')).toBe(true);
  expect(monthEnd.isSame(today.endOf('month').startOf('day'), 'day')).toBe(
    true,
  );

  const [prevMonthStart, prevMonthEnd] = getPresetDates(PreviousCalendarMonth)!;
  expect(prevMonthEnd.add(1, 'day').isSame(monthStart, 'day')).toBe(true);
  expect(prevMonthStart.isSame(monthStart.subtract(1, 'month'), 'day')).toBe(
    true,
  );

  const [weekStart] = getPresetDates(CurrentWeek)!;
  const [prevWeekStart, prevWeekEnd] = getPresetDates(PreviousCalendarWeek)!;
  expect(prevWeekEnd.add(1, 'day').isSame(weekStart, 'day')).toBe(true);
  expect(prevWeekEnd.diff(prevWeekStart, 'day')).toBe(6);

  const [yearStart, yearEnd] = getPresetDates(CurrentYear)!;
  expect(yearStart.isSame(today.startOf('year'), 'day')).toBe(true);
  expect(yearEnd.isSame(today.endOf('year').startOf('day'), 'day')).toBe(true);

  const [prevYearStart, prevYearEnd] = getPresetDates(PreviousCalendarYear)!;
  expect(prevYearEnd.add(1, 'day').isSame(yearStart, 'day')).toBe(true);
  expect(prevYearStart.isSame(yearStart.subtract(1, 'year'), 'day')).toBe(true);
});
