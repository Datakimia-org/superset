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
import { NO_TIME_RANGE } from '@superset-ui/core';
import { extendedDayjs } from '@superset-ui/core/utils/dates';
import {
  render,
  screen,
  userEvent,
  waitFor,
} from 'spec/helpers/testing-library';
import CalendarDatePicker from './CalendarDatePicker';

jest.mock('@superset-ui/core', () => ({
  ...jest.requireActual('@superset-ui/core'),
  fetchTimeRange: jest.fn(() =>
    Promise.resolve({ value: '2026-10-01 ≤ col < 2026-10-08' }),
  ),
}));

function inViewDayNumbers(panel: Element): number[] {
  return [
    ...panel.querySelectorAll(
      '.ant-picker-cell-in-view .ant-picker-cell-inner',
    ),
  ].map(cell => Number(cell.textContent));
}

async function openCalendar(label: RegExp) {
  await userEvent.click(screen.getByRole('button', { name: label }));
  const input = document.querySelector<HTMLInputElement>(
    '.ant-picker-input input',
  );
  expect(input).toBeTruthy();
  await userEvent.click(input!);
  await waitFor(() => {
    expect(document.querySelector('.ant-picker-panel')).toBeInTheDocument();
  });
  return document.querySelector('.ant-picker-panel')!;
}

test('calendar days are sequential in the current year', async () => {
  render(<CalendarDatePicker value={NO_TIME_RANGE} onChange={jest.fn()} />);

  const panel = await openCalendar(/no filter/i);
  const year = String(extendedDayjs().year());
  const header = panel.querySelector('.ant-picker-header')?.textContent ?? '';

  expect(header).toContain(year);
  expect(header).not.toMatch(/2[1-9]\d\d/);

  const days = inViewDayNumbers(panel);
  expect(days[0]).toBe(1);
  expect(days).toEqual(days.map((_, index) => index + 1));
  expect(days.length).toBeGreaterThanOrEqual(28);
  expect(
    panel.querySelectorAll(
      '.ant-picker-cell-selected, .ant-picker-cell-in-range',
    ),
  ).toHaveLength(0);

  const dayFifteen = [
    ...panel.querySelectorAll('.ant-picker-cell-in-view'),
  ].find(cell => cell.textContent === '15');
  expect(dayFifteen).toBeTruthy();
  await userEvent.click(dayFifteen!);

  const headerAfterClick =
    document.querySelector('.ant-picker-header')?.textContent ?? '';
  expect(headerAfterClick).toContain(year);
  expect(headerAfterClick).not.toMatch(/2[1-9]\d\d/);
});

test('a custom range stays on the chosen month', async () => {
  render(
    <CalendarDatePicker
      value="2026-10-01T00:00:00 : 2026-10-08T00:00:00"
      onChange={jest.fn()}
    />,
  );

  const panel = await openCalendar(/2026-10-01/);
  const header = panel.querySelector('.ant-picker-header')?.textContent ?? '';
  const days = inViewDayNumbers(panel);

  expect(header).toContain('2026');
  expect(header).not.toMatch(/2[1-9]\d\d/);
  expect(days).toEqual(days.map((_, index) => index + 1));
  expect(days).toHaveLength(31);

  const ranged = panel.querySelectorAll(
    '.ant-picker-cell-in-range, .ant-picker-cell-range-start, .ant-picker-cell-range-end',
  );
  expect(ranged.length).toBeGreaterThan(0);
  expect(ranged.length).toBeLessThan(15);
});
