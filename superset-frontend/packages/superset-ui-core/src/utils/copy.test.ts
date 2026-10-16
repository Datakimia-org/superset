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
import copyTextToClipboard from './copy';

const permalink = 'https://superset.example/superset/dashboard/p/abc/';

function readBlob(blob: Blob): Promise<string> {
  if (typeof blob.text === 'function') {
    return blob.text();
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

class FakeClipboardItem {
  private readonly items: Record<
    string,
    Blob | Promise<Blob | string> | string
  >;

  constructor(items: Record<string, Blob | Promise<Blob | string> | string>) {
    this.items = items;
  }

  get types(): string[] {
    return Object.keys(this.items);
  }

  async getType(type: string): Promise<Blob> {
    const value = await this.items[type];
    if (value instanceof Blob) {
      return value;
    }
    return new Blob([value], { type });
  }
}

function deferredText(): {
  getText: () => Promise<string>;
  resolveText: (value: string) => void;
} {
  let resolveText: (value: string) => void = () => undefined;
  const getText = () =>
    new Promise<string>(resolve => {
      resolveText = resolve;
    });
  return { getText, resolveText: value => resolveText(value) };
}

function mockClipboard(write: jest.Mock, writeText: jest.Mock) {
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { write, writeText },
  });
  global.ClipboardItem = FakeClipboardItem as unknown as typeof ClipboardItem;
}

test('registers the clipboard write before the text promise resolves', async () => {
  const write = jest.fn().mockResolvedValue(undefined);
  const writeText = jest.fn().mockResolvedValue(undefined);
  mockClipboard(write, writeText);
  const { getText, resolveText } = deferredText();

  const pending = copyTextToClipboard(getText);

  expect(write).toHaveBeenCalledTimes(1);
  expect(writeText).not.toHaveBeenCalled();
  const [items] = write.mock.calls[0] as [ClipboardItem[]];
  const pendingBlob = items[0].getType('text/plain');
  resolveText(permalink);
  const blob = await pendingBlob;
  await expect(readBlob(blob)).resolves.toBe(permalink);
  await pending;
  expect(writeText).not.toHaveBeenCalled();
});

test('falls back to writeText when ClipboardItem write is rejected', async () => {
  const write = jest.fn().mockRejectedValue(new Error('NotAllowedError'));
  const writeText = jest.fn().mockResolvedValue(undefined);
  mockClipboard(write, writeText);

  await copyTextToClipboard(() => Promise.resolve(permalink));

  expect(write).toHaveBeenCalledTimes(1);
  expect(writeText).toHaveBeenCalledWith(permalink);
});
