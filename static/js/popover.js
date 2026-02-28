document.addEventListener('DOMContentLoaded', function () {
    const overlay = document.getElementById('info-overlay');
    const content = document.getElementById('info-content');
    const infoImage = document.getElementById('info-image');
    const title = document.getElementById('info-title');
    const closeBtn = document.getElementById('info-close');

    function showModal(headerText, rowsHtml, imgSrc, imgAlt) {
        title.textContent = headerText || 'Detalle';
        content.innerHTML = rowsHtml || '<p>No hay información disponible.</p>';
        // populate right-side image preview if provided
        if(infoImage){
            if(imgSrc){
                // Clear previous
                infoImage.innerHTML = '';
                infoImage.setAttribute('aria-hidden','false');
                // Create an Image object so we can measure natural size and
                // choose an appropriate display width constrained to viewport.
                var imgEl = new Image();
                imgEl.alt = imgAlt || 'Imagen';
                imgEl.src = imgSrc;
                imgEl.style.display = 'block';
                imgEl.style.maxWidth = '100%';
                imgEl.style.height = 'auto';
                imgEl.style.borderRadius = '8px';
                // apply a conservative max-height to avoid overflowing the viewport
                var maxH = Math.round(window.innerHeight * 0.78);
                imgEl.style.maxHeight = maxH + 'px';
                imgEl.onload = function(){
                    try{
                        var w = imgEl.naturalWidth || imgEl.width || 300;
                        var h = imgEl.naturalHeight || imgEl.height || 200;
                        // Measure the modal content table height (tbody) if present
                        var table = content.querySelector('.modal-table');
                        var tableH = table ? table.clientHeight : content.scrollHeight;
                        // constrain desired height to viewport (80%) and to content table height
                        var viewportMaxH = Math.round(window.innerHeight * 0.8);
                        var desiredH = Math.min(viewportMaxH, Math.max(120, tableH));
                        // Set the image container height to desiredH (so it behaves like a table column)
                        infoImage.style.height = desiredH + 'px';
                        // Set image to fill container height while preserving aspect ratio
                        imgEl.style.height = '100%';
                        imgEl.style.width = 'auto';
                        imgEl.style.maxWidth = '100%';
                        imgEl.style.objectFit = 'contain';
                        // If the natural width is very large and would exceed a sensible column width,
                        // cap container width to a percentage of viewport but prefer the table-driven height.
                        var maxW = Math.round(window.innerWidth * 0.6); // allow up to 60% if needed
                        // compute expected rendered width based on height and aspect ratio
                        var expectedW = Math.round((w/h) * desiredH);
                        var finalW = Math.min(maxW, Math.max(140, expectedW));
                        infoImage.style.width = finalW + 'px';
                    }catch(e){
                        infoImage.style.width = '220px';
                        infoImage.style.height = '';
                        imgEl.style.maxHeight = maxH + 'px';
                    }
                };
                // Fallback: if image fails to load, clear the preview
                imgEl.onerror = function(){ infoImage.innerHTML = ''; infoImage.setAttribute('aria-hidden','true'); };
                infoImage.appendChild(imgEl);
            } else {
                infoImage.innerHTML = '';
                infoImage.setAttribute('aria-hidden','true');
                infoImage.style.width = '';
            }
        }
        overlay.classList.add('visible');
        overlay.setAttribute('aria-hidden', 'false');
    }

    function hideModal() {
        overlay.classList.remove('visible');
        overlay.setAttribute('aria-hidden', 'true');
        content.innerHTML = '';
    }

    // Close handlers
    closeBtn.addEventListener('click', hideModal);
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) hideModal();
    });

    // Find placeholder images inside proposals and attach click handlers
    document.querySelectorAll('.proposal-card .tabla-container img').forEach(function (img) {
        img.style.cursor = 'pointer';
        img.addEventListener('click', function (e) {
            // Determine header text: use the specific column header corresponding to the clicked image
            let headerText = null;
            try {
                const cell = img.closest('td, th');
                if (cell) {
                    const table = cell.closest('table');
                    if (table) {
                        const ths = table.querySelectorAll('thead th');
                        if (ths && ths.length > 0) {
                            const colIndex = cell.cellIndex; // index of the cell in the row
                            if (colIndex >= 0 && colIndex < ths.length) {
                                headerText = ths[colIndex].textContent.trim();
                            }
                        }
                    }
                }
            } catch (e) { /* ignore */ }
            // fallback to proposal card title
            if (!headerText) {
                const card = img.closest('.proposal-card');
                if (card) headerText = card.querySelector('h3') ? card.querySelector('h3').textContent : 'Detalle';
            }

            // Standardize: always use data-info parsed content for modal rows (Documento, Min.PCB, Max.PCB)

            // Default behavior: prefer data-info if present, otherwise use title; parse 'key: value' pairs
            const raw = img.getAttribute('data-info') || img.getAttribute('title') || '';
            const parts = raw.split(/;\s*/).filter(Boolean);
            let rowsHtml = '<table class="modal-table">';
            parts.forEach(function (p) {
                const kv = p.split(/:\s*/);
                if (kv.length >= 2) {
                    rowsHtml += '<tr><th>' + escapeHtml(kv[0]) + '</th><td>' + escapeHtml(kv.slice(1).join(': ')) + '</td></tr>';
                } else {
                    rowsHtml += '<tr><td colspan="2">' + escapeHtml(p) + '</td></tr>';
                }
            });
            rowsHtml += '</table>';
            // determine image source to show on the right (prefer data-img if present)
            var imgSrc = img.getAttribute('data-img') || img.getAttribute('src') || null;
            showModal(headerText, rowsHtml, imgSrc, headerText);
        });
    });

    // simple HTML escape
    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
});
