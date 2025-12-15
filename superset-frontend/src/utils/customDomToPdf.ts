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

import domToImage from 'dom-to-image-more';
import { jsPDF } from 'jspdf';
import { logging } from '@superset-ui/core';
import {
  A4_WIDTH_PT,
  A4_HEIGHT_PT,
  cloneNode,
  isCanvasBlank,
  calculatePageHeight,
  addPageBreaks,
} from './pdfUtils';

interface Image {
  type: string;
  quality: number;
}

interface Html2CanvasOptions {
  scale?: number;
  backgroundColor?: string;
  useCORS?: boolean;
  allowTaint?: boolean;
  logging?: boolean;
  [key: string]: any;
}

interface CustomDomToPdfOptions {
  margin?: number;
  filename: string;
  image?: Image;
  html2canvas?: Html2CanvasOptions;
  excludeClassNames?: string[];
  excludeTagNames?: string[];
}

/**
 * Custom implementation of dom-to-pdf with multi-page support using dom-to-image-more and jsPDF
 */
export default function customDomToPdf(
  elementToPrint: Element,
  options: CustomDomToPdfOptions,
): Promise<void> {
  return new Promise((resolve, reject) => {
    let overlay: HTMLElement | null = null;

    try {
      const {
        margin = 10,
        filename,
        image = { type: 'jpeg', quality: 1 },
        html2canvas = {},
        excludeClassNames = [],
        excludeTagNames = ['script', 'style', 'button', 'input', 'select'],
      } = options;

      // Create temporary overlay for processing
      overlay = document.createElement('div');
      overlay.style.position = 'fixed';
      overlay.style.top = '0';
      overlay.style.left = '0';
      overlay.style.width = '100vw';
      overlay.style.height = '100vh';
      overlay.style.zIndex = '1000';
      overlay.style.opacity = '0'; // Keep hidden but rendered
      overlay.style.pointerEvents = 'none';
      overlay.style.overflow = 'hidden';
      // Explicit white background to avoid transparency issues
      overlay.style.backgroundColor = '#ffffff';

      // Clone the element
      const clonedElement = cloneNode(elementToPrint) as Element;
      const clonedElementStyled = clonedElement as HTMLElement;

      // Apply styling to match original but allow full expansion
      clonedElementStyled.style.width = `${elementToPrint.scrollWidth}px`;
      clonedElementStyled.style.height = 'auto';
      clonedElementStyled.style.maxWidth = 'none';
      clonedElementStyled.style.maxHeight = 'none';
      clonedElementStyled.style.overflow = 'visible';
      // Reset margin and padding from original element
      clonedElementStyled.style.margin = '0';
      clonedElementStyled.style.padding = '0';
      // Use box-sizing to include padding in width calculation
      clonedElementStyled.style.boxSizing = 'border-box';

      // Define background color
      const bgcolor = html2canvas.backgroundColor || '#ffffff';

      // Create wrapper with only horizontal padding (left/right)
      // Vertical padding is added via spacer divs to avoid issues with page breaks
      const wrapper = document.createElement('div');
      wrapper.style.paddingLeft = '32px';
      wrapper.style.paddingRight = '32px';
      wrapper.style.backgroundColor = bgcolor;
      wrapper.style.boxSizing = 'border-box';

      // Add top spacer
      const topSpacer = document.createElement('div');
      topSpacer.style.height = '32px';
      topSpacer.style.backgroundColor = bgcolor;
      wrapper.appendChild(topSpacer);

      // Add content
      wrapper.appendChild(clonedElementStyled);

      // Add bottom spacer
      const bottomSpacer = document.createElement('div');
      bottomSpacer.style.height = '32px';
      bottomSpacer.style.backgroundColor = bgcolor;
      wrapper.appendChild(bottomSpacer);

      overlay.appendChild(wrapper);
      document.body.appendChild(overlay);

      // Calculate page dimensions based on the ACTUAL width of the cloned content
      const containerWidth = wrapper.getBoundingClientRect().width;
      const pageHeight = calculatePageHeight(containerWidth, margin);

      // Add page breaks using the smart logic (with 32px top padding for each new page)
      addPageBreaks(wrapper, pageHeight, 32);

      // Create filter function
      const filter = (node: Element) => {
        if (typeof node.className === 'string') {
          // Check excluded class names
          const hasExcludedClass = excludeClassNames.some(className =>
            node.className.includes(className),
          );
          if (hasExcludedClass) return false;
        }

        // Check excluded tag names
        if (excludeTagNames.includes(node.tagName?.toLowerCase())) {
          return false;
        }

        return true;
      };

      const scale = html2canvas.scale || 1; // 2 gives better quality but is slower

      // Generate the full canvas first
      domToImage
        .toCanvas(wrapper, {
          bgcolor,
          filter,
          quality: image.quality,
          width: containerWidth * scale,
          height: wrapper.scrollHeight * scale,
          style: {
            transform: `scale(${scale})`,
            transformOrigin: 'top left',
            width: `${containerWidth}px`,
            height: `${wrapper.scrollHeight}px`,
          },
        })
        .then((canvas: HTMLCanvasElement) => {
          try {
            // Create PDF
            const pdf = new jsPDF('p', 'pt', 'a4'); // Portrait, points, A4

            const fullHeight = canvas.height;
            const scaledPageHeight = pageHeight * scale;
            const numPages = Math.ceil(fullHeight / scaledPageHeight);

            let pageAdded = false;

            for (let page = 0; page < numPages; page += 1) {
              const yOffset = page * scaledPageHeight;

              // Fine adjustment for the last page
              let renderHeight = scaledPageHeight;
              if (page === numPages - 1) {
                const remainingHeight = fullHeight - yOffset;
                // If the remainder is very small, sometimes it's a white border, optionally ignore
                renderHeight = remainingHeight;
              }

              // Create canvas for this page
              const pageCanvas = document.createElement('canvas');
              pageCanvas.width = canvas.width;
              pageCanvas.height = renderHeight;

              const pageCtx = pageCanvas.getContext('2d');
              if (!pageCtx) continue;

              // Copy the relevant portion of the full canvas
              pageCtx.fillStyle = '#ffffff';
              pageCtx.fillRect(0, 0, pageCanvas.width, pageCanvas.height);

              pageCtx.drawImage(
                canvas,
                0,
                yOffset,
                canvas.width,
                renderHeight,
                0,
                0,
                canvas.width,
                renderHeight,
              );

              // Skip blank pages logic
              if (!isCanvasBlank(pageCanvas)) {
                // Add new page if not the first
                if (pageAdded) {
                  pdf.addPage();
                }

                // Calculate dimensions to fit A4 with margins
                const pdfWidth = A4_WIDTH_PT - margin * 2;
                const pdfHeight = A4_HEIGHT_PT - margin * 2;

                const imgAspectRatio = pageCanvas.width / pageCanvas.height;
                const pdfAspectRatio = pdfWidth / pdfHeight;

                let finalWidth;
                let finalHeight;
                let xOffset;
                let yOffset;

                // Fit logic
                if (imgAspectRatio > pdfAspectRatio) {
                  // Wider than tall - use full width
                  finalWidth = pdfWidth;
                  finalHeight = pdfWidth / imgAspectRatio;
                  xOffset = margin;
                  yOffset = margin;
                } else {
                  // Taller than wide - use full height or fit width if it's just a segment
                  finalWidth = pdfWidth;
                  finalHeight = pdfWidth / imgAspectRatio;
                  xOffset = margin;
                  yOffset = margin;
                }

                // Convert page canvas to image and add to PDF
                const pageDataUrl = pageCanvas.toDataURL(
                  `image/${image.type}`,
                  image.quality,
                );
                const imageFormat = image.type === 'png' ? 'PNG' : 'JPEG';
                pdf.addImage(
                  pageDataUrl,
                  imageFormat,
                  xOffset,
                  yOffset,
                  finalWidth,
                  finalHeight,
                );

                pageAdded = true;
              }
            }

            // Save PDF if at least one page was added
            if (pageAdded) {
              pdf.save(filename);
              resolve();
            } else {
              reject(new Error('No content to generate PDF'));
            }
          } catch (pdfError) {
            logging.error('PDF generation failed:', pdfError);
            reject(pdfError);
          }
        })
        .catch((error: Error) => {
          logging.error('Canvas generation failed:', error);
          reject(error);
        })
        .finally(() => {
          // Cleanup overlay
          if (overlay?.parentNode) {
            overlay.parentNode.removeChild(overlay);
          }
        });
    } catch (error) {
      logging.error('Custom dom-to-pdf failed:', error);
      // Cleanup overlay in case of early error
      if (overlay?.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
      reject(error);
    }
  });
}
