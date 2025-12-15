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
 * Uses iterative approach to handle position changes after inserting spacers.
 */
export function addPageBreaks(
  container: HTMLElement,
  pageHeight: number,
  topPadding = 32,
): void {
  // Get the position of the main container for relative calculations
  const containerRect = container.getBoundingClientRect();

  // CRITICAL: Find the grid-content container which is the flex column parent of rows
  const gridContent = container.querySelector('.grid-content');
  if (!gridContent) {
    // If no grid-content, can't apply page breaks properly
    return;
  }

  // Select ONLY row-level elements (direct children of grid-content)
  // These are the units that should be kept together or pushed to next page
  // DO NOT select individual chart holders - only their parent rows
  const selectors = [
    '.grid-row',
    '.dashboard-component-row',
    '.dashboard-component-header',
    '.dashboard-component-divider',
    '.dashboard-markdown',
    '.dashboard-component-tabs',
  ];

  // Find all row-level elements that are DIRECT children of grid-content
  const elements: HTMLElement[] = [];

  selectors.forEach(selector => {
    const found = Array.from(gridContent.querySelectorAll(selector));
    found.forEach(el => {
      // Only include if it's a direct child of grid-content (or one level deep)
      // This prevents processing nested rows inside columns
      const parent = el.parentElement;
      if (parent === gridContent || parent?.parentElement === gridContent) {
        if (!elements.includes(el as HTMLElement)) {
          elements.push(el as HTMLElement);
        }
      }
    });
  });

  // If no specific elements found, use direct children of grid-content
  if (elements.length === 0) {
    const directChildren = Array.from(gridContent.children) as HTMLElement[];
    directChildren.forEach(child => {
      // Skip spacers we've already added
      if (
        !child.className.includes('custom-pdf-page-break-spacer') &&
        !child.className.includes('custom-pdf-page-padding-top')
      ) {
        elements.push(child);
      }
    });
  }

  // Process elements iteratively - check positions after each insertion
  let i = 0;
  while (i < elements.length) {
    const el = elements[i];

    // Skip elements that are already page break spacers
    if (
      el.className.includes('custom-pdf-page-break-spacer') ||
      el.className.includes('custom-pdf-page-padding-top')
    ) {
      i++;
      continue;
    }

    // Skip elements with display: none or visibility: hidden
    const computedStyle = window.getComputedStyle(el);
    if (
      computedStyle.display === 'none' ||
      computedStyle.visibility === 'hidden' ||
      el.offsetHeight === 0
    ) {
      i++;
      continue;
    }

    // Get FRESH position each time (critical for handling inserted spacers)
    const rect = el.getBoundingClientRect();
    const { height } = rect;

    // Skip very small elements
    if (height < 10) {
      i++;
      continue;
    }

    // Recalculate grid-content position in case it changed
    const currentGridContentRect = gridContent.getBoundingClientRect();
    const relativeTop = rect.top - currentGridContentRect.top;
    const relativeBottom = relativeTop + height;

    // Calculate which "page" the element falls on
    const startPage = Math.floor(relativeTop / pageHeight);
    const endPage = Math.floor(relativeBottom / pageHeight);

    // Check if element crosses page boundary
    if (startPage !== endPage) {
      const remainingSpaceOnPage = pageHeight - (relativeTop % pageHeight);

      // For dashboard rows/components, ALWAYS push to next page if they cross boundaries
      // Exception: if element is taller than 90% of a page, let it be cut (it's too big anyway)
      const isTooLargeToFit = height > pageHeight * 0.9;

      // Also check if there's enough content being cut to warrant pushing
      // If less than 50px would be cut, it might be just a border/shadow, let it be
      const amountOnNextPage = height - remainingSpaceOnPage;
      const isSignificantlyCut = amountOnNextPage > 50;

      if (!isTooLargeToFit && isSignificantlyCut) {
        // Create spacer to push to next page
        const pageBreak = document.createElement('div');
        pageBreak.style.display = 'block';
        pageBreak.style.height = `${remainingSpaceOnPage}px`;
        pageBreak.style.width = '100%';
        pageBreak.style.flexShrink = '0';
        pageBreak.className = 'custom-pdf-page-break-spacer';

        // Create top padding for new page
        const pagePaddingTop = document.createElement('div');
        pagePaddingTop.style.display = 'block';
        pagePaddingTop.style.height = `${topPadding}px`;
        pagePaddingTop.style.width = '100%';
        pagePaddingTop.style.flexShrink = '0';
        pagePaddingTop.className = 'custom-pdf-page-padding-top';

        // Insert spacers
        if (el.parentNode) {
          el.parentNode.insertBefore(pageBreak, el);
          el.parentNode.insertBefore(pagePaddingTop, el);

          // After inserting, we need to recheck subsequent elements
          // because their positions have changed
          // So we don't increment i, we re-process this element
          // to verify its new position is correct
          continue;
        }
      }
    }

    i++;
  }
}
