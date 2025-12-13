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

// A4 dimensions in points (at 72 DPI)
const A4_WIDTH_PT = 595.28;
const A4_HEIGHT_PT = 841.89;

/**
 * Clone a DOM node with special handling for form elements and canvas
 */
function cloneNode(node: Node): Node {
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
function isCanvasBlank(canvas: HTMLCanvasElement): boolean {
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
function calculatePageHeight(containerWidth: number, margin: number): number {
  // Calculate the ratio to convert from A4 points to pixels
  const pageWidthWithMargin = containerWidth;
  const pageWidthPt = A4_WIDTH_PT - margin * 2;
  const scale = pageWidthWithMargin / pageWidthPt;

  const pageHeightPt = A4_HEIGHT_PT - margin * 2;
  return Math.floor(pageHeightPt * scale);
}

/**
 * MEJORA: Lógica inteligente de saltos de página.
 * Busca elementos que crucen el límite de la página y añade espaciadores.
 */
function addPageBreaks(
  container: HTMLElement,
  pageHeight: number,
  topPadding = 32,
): void {
  // En Superset, los componentes principales suelen tener clases específicas.
  // Intentamos seleccionar los contenedores de gráficos o filas.
  // Si no encuentra clases específicas, usa los hijos directos.
  let elements = Array.from(
    container.querySelectorAll('.dashboard-component, .chart-container, .row'),
  );

  // Fallback: si no encuentra estructura de superset, usa hijos directos
  if (elements.length === 0) {
    elements = Array.from(container.children);
  }

  // Obtenemos la posición del contenedor principal para cálculos relativos
  const containerRect = container.getBoundingClientRect();

  elements.forEach(child => {
    const el = child as HTMLElement;

    // IMPORTANTE: Llamar a getBoundingClientRect DENTRO del loop.
    // Esto asegura que si empujamos un elemento anterior hacia abajo,
    // las coordenadas del elemento actual se actualicen.
    const rect = el.getBoundingClientRect();

    // Altura del elemento
    const { height } = rect;

    // Posición relativa al inicio del documento PDF clonado
    const relativeTop = rect.top - containerRect.top;
    const relativeBottom = relativeTop + height;

    // Calcular en qué "página" cae el inicio y el final del elemento
    const startPage = Math.floor(relativeTop / pageHeight);
    const endPage = Math.floor(relativeBottom / pageHeight);

    // Lógica de decisión:
    // 1. Si el elemento empieza en una página y termina en otra (startPage !== endPage)
    // 2. Y el elemento NO es más grande que una página entera (height < pageHeight)
    //    (Si es gigante, se cortará de todas formas, no tiene sentido empujarlo)
    if (startPage !== endPage && height < pageHeight) {
      // Calcular cuánto espacio queda en la página actual
      const remainingSpaceOnPage = pageHeight - (relativeTop % pageHeight);

      // Crear un espaciador invisible para empujar contenido a la siguiente página
      const pageBreak = document.createElement('div');
      pageBreak.style.display = 'block';
      pageBreak.style.height = `${remainingSpaceOnPage}px`;
      pageBreak.style.width = '100%';
      // Clase para depuración si fuera necesario
      pageBreak.className = 'custom-pdf-page-break-spacer';

      // Crear un espaciador para el padding-top de la nueva página
      const pagePaddingTop = document.createElement('div');
      pagePaddingTop.style.display = 'block';
      pagePaddingTop.style.height = `${topPadding}px`;
      pagePaddingTop.style.width = '100%';
      pagePaddingTop.className = 'custom-pdf-page-padding-top';

      // Insertar los espaciadores ANTES del elemento que se iba a cortar
      if (el.parentNode) {
        el.parentNode.insertBefore(pageBreak, el);
        el.parentNode.insertBefore(pagePaddingTop, el);
      }
    }
  });
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
      // Fondo blanco explícito para evitar problemas de transparencia
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

      const scale = html2canvas.scale || 1; // 2 da mejor calidad pero es más lento

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

              // Ajuste fino para la última página
              let renderHeight = scaledPageHeight;
              if (page === numPages - 1) {
                const remainingHeight = fullHeight - yOffset;
                // Si el remanente es muy pequeño, a veces es borde blanco, opcionalmente ignorar
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
