/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

import { logging } from '@superset-ui/core';

// A4 dimensions in points (at 72 DPI)
export const A4_WIDTH_PT = 595.28;
export const A4_HEIGHT_PT = 841.89;

/**
 * Clone a DOM node with special handling for form elements and canvas
 */
export function cloneNode(node: Node): Node {
  const clonedNode = node.cloneNode(true);

  if (clonedNode.nodeType === Node.ELEMENT_NODE) {
    const element = clonedNode as Element;

    // Handle canvas elements - preserve their content
    const canvases = element.querySelectorAll('canvas');
    const originalCanvases = (node as Element).querySelectorAll('canvas');

    for (let i = 0; i < canvases.length; i += 1) {
      try {
        const canvas = canvases[i] as HTMLCanvasElement;
        const originalCanvas = originalCanvases[i] as HTMLCanvasElement;
        const ctx = canvas.getContext('2d');
        if (ctx && originalCanvas) {
          ctx.drawImage(originalCanvas, 0, 0);
        }
      } catch (error) {
        logging.debug('Failed to clone canvas content:', error);
      }
    }

    // Handle form elements - preserve their values
    const textareas = element.querySelectorAll('textarea');
    const originalTextareas = (node as Element).querySelectorAll('textarea');
    for (let i = 0; i < textareas.length; i += 1) {
      textareas[i].innerHTML = originalTextareas[i].value;
    }

    const selects = element.querySelectorAll('select');
    const originalSelects = (node as Element).querySelectorAll('select');
    for (let i = 0; i < selects.length; i += 1) {
      const select = selects[i] as HTMLSelectElement;
      const originalSelect = originalSelects[i] as HTMLSelectElement;
      select.selectedIndex = originalSelect.selectedIndex;
    }

    // Remove script tags for security
    const scripts = element.querySelectorAll('script');
    scripts.forEach(script => script.remove());
  }

  return clonedNode;
}

/**
 * Check if a canvas is blank (all pixels are transparent or white)
 */
export function isCanvasBlank(canvas: HTMLCanvasElement): boolean {
  try {
    const ctx = canvas.getContext('2d');
    if (!ctx) return true;

    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const { data } = imageData;

    for (let i = 0; i < data.length; i += 4) {
      // Check if pixel has any non-white/non-transparent content
      if (
        data[i] !== 255 ||
        data[i + 1] !== 255 ||
        data[i + 2] !== 255 ||
        data[i + 3] !== 0
      ) {
        return false;
      }
    }
    return true;
  } catch (error) {
    logging.debug('Could not check if canvas is blank:', error);
    return false;
  }
}

/**
 * Calculate the pixel height for one page based on A4 dimensions
 */
export function calculatePageHeight(
  containerWidth: number,
  margin: number,
): number {
  // Calculate the ratio to convert from A4 points to pixels
  const pageWidthWithMargin = containerWidth;
  const pageWidthPt = A4_WIDTH_PT - margin * 2;
  const scale = pageWidthWithMargin / pageWidthPt;

  const pageHeightPt = A4_HEIGHT_PT - margin * 2;
  return Math.floor(pageHeightPt * scale);
}

/**
 * IMPROVEMENT: Smart page break logic.
 * Finds elements that cross the page boundary and adds spacers.
 */
export function addPageBreaks(
  container: HTMLElement,
  pageHeight: number,
  topPadding = 32,
): void {
  // In Superset, main components usually have specific classes.
  // We try to select chart containers or rows.
  // If no specific classes are found, use direct children.
  let elements = Array.from(
    container.querySelectorAll('.dashboard-component, .chart-container, .row'),
  );

  // Fallback: if no superset structure is found, use direct children
  if (elements.length === 0) {
    elements = Array.from(container.children);
  }

  // Get the position of the main container for relative calculations
  const containerRect = container.getBoundingClientRect();

  elements.forEach(child => {
    const el = child as HTMLElement;

    // IMPORTANT: Call getBoundingClientRect INSIDE the loop.
    // This ensures that if we push a previous element down,
    // the coordinates of the current element are updated.
    const rect = el.getBoundingClientRect();

    // Element height
    const { height } = rect;

    // Position relative to the start of the cloned PDF document
    const relativeTop = rect.top - containerRect.top;
    const relativeBottom = relativeTop + height;

    // Calculate which "page" the start and end of the element fall on
    const startPage = Math.floor(relativeTop / pageHeight);
    const endPage = Math.floor(relativeBottom / pageHeight);

    // Decision logic:
    // 1. If the element starts on one page and ends on another (startPage !== endPage)
    // 2. And the element is NOT larger than a full page (height < pageHeight)
    //    (If it's huge, it will be cut anyway, no point in pushing it)
    if (startPage !== endPage && height < pageHeight) {
      // Calculate how much space remains on the current page
      const remainingSpaceOnPage = pageHeight - (relativeTop % pageHeight);

      // Create an invisible spacer to push content to the next page
      const pageBreak = document.createElement('div');
      pageBreak.style.display = 'block';
      pageBreak.style.height = `${remainingSpaceOnPage}px`;
      pageBreak.style.width = '100%';
      // Class for debugging if needed
      pageBreak.className = 'custom-pdf-page-break-spacer';

      // Create a spacer for the top padding of the new page
      const pagePaddingTop = document.createElement('div');
      pagePaddingTop.style.display = 'block';
      pagePaddingTop.style.height = `${topPadding}px`;
      pagePaddingTop.style.width = '100%';
      pagePaddingTop.className = 'custom-pdf-page-padding-top';

      // Insert the spacers BEFORE the element that was going to be cut
      if (el.parentNode) {
        el.parentNode.insertBefore(pageBreak, el);
        el.parentNode.insertBefore(pagePaddingTop, el);
      }
    }
  });
}
