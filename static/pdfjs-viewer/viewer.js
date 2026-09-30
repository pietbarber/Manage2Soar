// Self-hosted PDF.js viewer for CMS inline PDF embeds (Issue #1069).
//
// Chrome's built-in PDF viewer refuses to activate inside a sandboxed
// <iframe> no matter which sandbox tokens are granted, which is why PDFs
// embedded via a plain `<iframe src="the.pdf" sandbox="...">` show
// "This page has been blocked by Chrome". This page renders the PDF
// ourselves (via pdf.js) so the surrounding iframe can stay genuinely
// sandboxed.
//
// Usage: viewer.html?file=<url-encoded PDF URL>
// The `file` URL must resolve to a same-origin endpoint that serves the
// bytes directly (e.g. /cms/document-pdf/<id>/ or the external PDF proxy) so
// that pdf.js's fetch() is never blocked by cross-origin CORS restrictions.

import * as pdfjsLib from "../vendor/pdfjs/build/pdf.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "../vendor/pdfjs/build/pdf.worker.min.mjs";

const statusEl = document.getElementById("status");
const pagesEl = document.getElementById("pages");
const zoomInBtn = document.getElementById("zoomIn");
const zoomOutBtn = document.getElementById("zoomOut");
const zoomLevelEl = document.getElementById("zoomLevel");

const MIN_SCALE = 0.4;
const MAX_SCALE = 3;
let scale = 1.25;
let pdfDocument = null;
let renderGeneration = 0;

function setStatus(message, isError) {
  statusEl.textContent = message || "";
  statusEl.classList.toggle("error", Boolean(isError));
}

function getRequestedFile() {
  const params = new URLSearchParams(window.location.search);
  const file = params.get("file");
  return file && file.trim() ? file.trim() : null;
}

async function renderAllPages() {
  const myGeneration = ++renderGeneration;
  pagesEl.textContent = "";

  for (let pageNumber = 1; pageNumber <= pdfDocument.numPages; pageNumber++) {
    if (myGeneration !== renderGeneration) {
      return; // A newer render (e.g. zoom change) superseded this one.
    }

    const page = await pdfDocument.getPage(pageNumber);
    const outputScale = window.devicePixelRatio || 1;
    const viewport = page.getViewport({ scale });

    const canvas = document.createElement("canvas");
    canvas.width = Math.floor(viewport.width * outputScale);
    canvas.height = Math.floor(viewport.height * outputScale);
    canvas.style.width = `${Math.floor(viewport.width)}px`;
    canvas.style.height = `${Math.floor(viewport.height)}px`;
    pagesEl.appendChild(canvas);

    const transform = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null;
    await page.render({
      canvasContext: canvas.getContext("2d"),
      transform,
      viewport,
    }).promise;
  }
}

function updateZoomLabel() {
  zoomLevelEl.textContent = `${Math.round(scale * 100)}%`;
}

async function applyZoom(nextScale) {
  scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, nextScale));
  updateZoomLabel();
  if (pdfDocument) {
    await renderAllPages();
  }
}

zoomInBtn.addEventListener("click", () => applyZoom(scale * 1.2));
zoomOutBtn.addEventListener("click", () => applyZoom(scale / 1.2));

async function loadAndRender() {
  const file = getRequestedFile();
  updateZoomLabel();

  if (!file) {
    setStatus("No PDF was specified.", true);
    return;
  }

  setStatus("Loading PDF\u2026");
  try {
    const loadingTask = pdfjsLib.getDocument({ url: file });
    pdfDocument = await loadingTask.promise;
    setStatus("");
    await renderAllPages();
  } catch (error) {
    pdfDocument = null;
    pagesEl.textContent = "";
    setStatus(
      "This PDF could not be displayed here. Use the \u201cOpen PDF in new tab\u201d link below instead.",
      true
    );
  }
}

loadAndRender();
