PDF.js 3.11.174 (Mozilla, Apache-2.0), the `build/pdf.min.js` and
`build/pdf.worker.min.js` files of the npm package `pdfjs-dist@3.11.174`
(the same files cdnjs serves as pdf.js/3.11.174), unmodified.

Served from the CRM itself rather than a CDN: the Virtual Catalogue's PDF
viewer ("Tag from the PDF") loads them on first use; a third-party script
would run next to the signed-in user's token, and some office networks block
CDNs. To upgrade, copy the two files from a newer pdfjs-dist into a folder
named after its version and change PDFJS_BASE in
src/components/products/PdfTagger.jsx.
