(function(){
    'use strict';

    function qs(s){ return document.querySelector(s); }
    function qsa(s){ return Array.from(document.querySelectorAll(s)); }

    var buildBtn = qs('#build-proposal-btn');
    if(!buildBtn) return;

    var selectionMode = false;
    // Map from tr -> {table, tr, cells, count, badgeNum}
    var selectedMap = new Map();
    // preserve exact selection order (one entry per click) so preview can show each machine separately
    var selectionSequence = [];
    var floatingBtn = null;
    var restoring = false;
    var STORAGE_KEY = 'proposal_builder_state';

    function computeRowSignature(entry){
        var meta = entry.meta || {};
        return (meta.tech || 'Tecnologia') + '||' + entry.cells.join('|');
    }

    function persistState(){
        if(!selectionMode || restoring) return;
        var seqSigs = [];
        var counts = {};
        selectionSequence.forEach(function(tr){
            var entry = selectedMap.get(tr);
            if(!entry) return;
            seqSigs.push(computeRowSignature(entry));
        });
        selectedMap.forEach(function(entry){
            counts[computeRowSignature(entry)] = entry.count;
        });
        var payload = { active: selectionMode, sequence: seqSigs, counts: counts };
        try{ localStorage.setItem(STORAGE_KEY, JSON.stringify(payload)); }catch(e){}
    }

    function loadState(){
        try{ var raw = localStorage.getItem(STORAGE_KEY); if(!raw) return null; return JSON.parse(raw); }catch(e){ return null; }
    }

    function clearState(){
        try{ localStorage.removeItem(STORAGE_KEY); }catch(e){}
    }

    buildBtn.addEventListener('click', function(){
        if(selectionMode){ stopSelectionMode(); return; }
        startSelectionMode();
    });

    function startSelectionMode(){
        selectionMode = true;
        if(buildBtn){
            // change label to cancel-proposal while selecting; use i18n where available
            try{ buildBtn.setAttribute('data-i18n', 'cancel_proposal'); if(window.i18nApplyLanguage) window.i18nApplyLanguage(window.i18nGetLang ? window.i18nGetLang() : 'es'); }catch(e){ buildBtn.textContent = 'Cancelar propuesta'; }
        }
        showBanner('Seleccione las máquinas (haga clic en las filas)');
        // reset sequence
        selectionSequence = [];
        qsa('.tabla-container table.data-table').forEach(function(table){
            // ensure header has a control TH to keep columns aligned
            try{
                var thead = table.querySelector('thead');
                if(thead){
                    var headRow = thead.querySelector('tr');
                    if(headRow && !headRow.querySelector('.proposal-control-header')){
                        var ctlTh = document.createElement('th'); ctlTh.className='proposal-control-header'; ctlTh.textContent='Cantidad'; headRow.insertBefore(ctlTh, headRow.firstChild);
                    }
                }
            }catch(e){}
            // add an (initially empty) badge cell to every row so columns don't shift when selecting
            table.querySelectorAll('tbody tr').forEach(function(tr){
                tr.classList.add('selectable-row');
                // if a badge cell doesn't exist, create an empty one (hidden state)
                if(!tr.querySelector('.proposal-count-badge')){
                    var badgeTd = document.createElement('td'); badgeTd.className = 'proposal-count-badge'; badgeTd.style.width = '48px'; badgeTd.style.textAlign='center';
                    var badge = document.createElement('div'); badge.style.display='inline-flex'; badge.style.alignItems='center'; badge.style.justifyContent='center'; badge.style.gap='6px';
                    var minus = document.createElement('button'); minus.className='btn proposal-minus'; minus.textContent='-'; minus.style.padding='2px 6px'; minus.title='Quitar una unidad'; minus.style.visibility = 'hidden';
                    var num = document.createElement('span'); num.textContent = ''; num.style.minWidth='18px';
                    badge.appendChild(minus); badge.appendChild(num); badgeTd.appendChild(badge);
                    tr.insertBefore(badgeTd, tr.firstChild);
                }
                tr.addEventListener('click', onRowClick);
            });
        });
        createFloatingPreview();
        persistState();
    }

    function stopSelectionMode(){
        selectionMode = false;
        if(buildBtn){ try{ buildBtn.setAttribute('data-i18n', 'build_proposal'); if(window.i18nApplyLanguage) window.i18nApplyLanguage(window.i18nGetLang ? window.i18nGetLang() : 'es'); }catch(e){ buildBtn.textContent = 'Armar propuesta'; } }
        hideBanner();
        qsa('.tabla-container table.data-table').forEach(function(table){
            // remove control header if present
            try{ var thead = table.querySelector('thead'); if(thead){ var headRow = thead.querySelector('tr'); var ch = headRow && headRow.querySelector('.proposal-control-header'); if(ch) ch.remove(); } }catch(e){}
            table.querySelectorAll('tbody tr').forEach(function(tr){ tr.classList.remove('selected-row'); tr.classList.remove('selectable-row'); tr.removeEventListener('click', onRowClick); var b = tr.querySelector('.proposal-count-badge'); if(b) b.remove(); });
        });
        selectedMap.clear();
        selectionSequence = [];
        removeFloatingPreview();
        clearState();
    }

    function getTechLabelForTable(table){
        try{
            // index inline: inside .result-section with an h3 title
            var section = table.closest('.result-section');
            if(section){
                var h3 = section.querySelector('h3');
                if(h3) return h3.textContent.trim();
            }
            // tecnologia page: table inside .tabla-container preceded by an h2
            var cont = table.closest('.tabla-container');
            if(cont && cont.previousElementSibling){
                var el = cont.previousElementSibling;
                if(el && (el.tagName === 'H2' || el.tagName === 'H3')){
                    return el.textContent.trim();
                }
            }
        }catch(err){}
        return 'Tecnología';
    }

    function onRowClick(e){
        var tr = e.currentTarget;
        var entry = selectedMap.get(tr);
        // find existing badge (we created one for every row on start)
        var badgeTd = tr.querySelector('.proposal-count-badge');
        var minusBtn = badgeTd && badgeTd.querySelector('.proposal-minus');
        var numSpan = badgeTd && badgeTd.querySelector('span');
        if(!entry){
            // first selection (or re-selection after 0)
            tr.dataset._selected = '1'; tr.classList.add('selected-row');
            var table = tr.closest('table');
            var cells = Array.from(tr.querySelectorAll('td')).map(function(td){ return td.textContent.trim(); });
            // detect inline <img> if the server rendered one inside the cell and preserve its src
            var _imgEl = tr.querySelector('img');
            var _imgSrc = null;
            try{ if(_imgEl){ _imgSrc = _imgEl.getAttribute('data-src') || _imgEl.getAttribute('src') || null; } }catch(e){}
            // extract metadata: tecnologia, documento, min/max PCB
            var ths = Array.from((table.querySelectorAll('thead th')||[])).map(function(th){ return (th.textContent||'').trim(); });
            function findIdxBy(fn){ for(var i=0;i<ths.length;i++){ if(fn(ths[i])) return i; } return -1; }
            function low(s){ return String(s||'').toLowerCase(); }
            var docIdx = findIdxBy(function(h){ var l = low(h); return l.indexOf('documento')!==-1 || l.indexOf('document')!==-1; });
            var minIdx = findIdxBy(function(h){ var l = low(h); return l.indexOf('pcb')!==-1 && l.indexOf('min')!==-1; });
            var maxIdx = findIdxBy(function(h){ var l = low(h); return l.indexOf('pcb')!==-1 && l.indexOf('max')!==-1; });
            if(minIdx === -1){ minIdx = findIdxBy(function(h){ var l = low(h); return l.indexOf('min.pcb')!==-1; }); }
            if(maxIdx === -1){ maxIdx = findIdxBy(function(h){ var l = low(h); return l.indexOf('max.pcb')!==-1; }); }
            var docVal = (docIdx >= 0 && docIdx < cells.length) ? cells[docIdx] : (cells[1] || '');
            var minVal = (minIdx >= 0 && minIdx < cells.length) ? cells[minIdx] : '';
            var maxVal = (maxIdx >= 0 && maxIdx < cells.length) ? cells[maxIdx] : '';
            var techLabel = getTechLabelForTable(table);
            // populate existing badge cell
            if(minusBtn) { minusBtn.style.visibility = 'visible'; }
            if(numSpan) { numSpan.textContent = '1'; }
            // attach decrement handler if not already attached
            if(minusBtn && !minusBtn._handlerAttached){
                minusBtn._handlerAttached = true;
                minusBtn.addEventListener('click', function(ev){
                    ev.stopPropagation();
                    var e = selectedMap.get(tr); if(!e) return;
                    // remove one occurrence of this tr from the selectionSequence (last occurrence)
                    for(var i = selectionSequence.length - 1; i >= 0; --i){ if(selectionSequence[i] === tr){ selectionSequence.splice(i,1); break; } }
                    e.count = Math.max(0, e.count - 1);
                    if(e.count === 0){
                        tr.dataset._selected='0'; tr.classList.remove('selected-row'); if(minusBtn) minusBtn.style.visibility = 'hidden'; if(numSpan) numSpan.textContent = ''; selectedMap.delete(tr);
                    } else { if(numSpan) numSpan.textContent = String(e.count); }
                    updateFloatingState();
                    persistState();
                });
            }
            entry = { table: table, tr: tr, cells: cells, count: 1, badgeNum: numSpan, meta: { tech: techLabel, doc: docVal, min: minVal, max: maxVal }, image: _imgSrc };
            selectedMap.set(tr, entry);
            // record selection order (one entry per click)
            selectionSequence.push(tr);
        } else {
            // increment count
            entry.count += 1; if(entry.badgeNum) entry.badgeNum.textContent = String(entry.count);
            selectionSequence.push(tr);
        }
        updateFloatingState();
        persistState();
    }

    function showBanner(msg){ hideBanner(); var b = document.createElement('div'); b.id='proposal-banner'; b.style.position='fixed'; b.style.top='20px'; b.style.left='50%'; b.style.transform='translateX(-50%)'; b.style.background='#fde68a'; b.style.padding='8px 12px'; b.style.border='1px solid #f59e0b'; b.style.borderRadius='6px'; b.style.zIndex=1200; b.textContent = msg; document.body.appendChild(b); }
    function hideBanner(){ var e = qs('#proposal-banner'); if(e) e.remove(); }

    function createFloatingPreview(){
        if(floatingBtn) return;
        var btn = document.createElement('button');
        btn.id = 'proposal-preview-float';
        btn.setAttribute('data-i18n','preview_proposal_float');
        btn.style.position = 'fixed';
        btn.style.right = '20px';
        btn.style.bottom = '20px';
        btn.style.zIndex = 1200;
        btn.style.padding = '10px 14px';
        btn.style.background = '#059669'; /* verde para destacar durante creación */
        btn.style.color = '#fff';
        btn.style.border = 'none';
        btn.style.borderRadius = '6px';
        btn.style.boxShadow = '0 4px 8px rgba(0,0,0,0.15)';
        btn.disabled = true;
        btn.addEventListener('click', openPreviewModal);
        document.body.appendChild(btn);
        floatingBtn = btn;
        // initialize text using translations map if available
        try{
            var lang = (window.i18nGetLang && window.i18nGetLang()) || 'es';
            var tpl = (window.i18nTranslations && window.i18nTranslations.preview_proposal_float) ? window.i18nTranslations.preview_proposal_float[lang === 'en' ? 'en' : 'es'] : 'Preview propuesta ({n})';
            btn.textContent = tpl.replace('{n}', '0');
            if(window.i18nApplyLanguage) window.i18nApplyLanguage(lang);
        }catch(e){}
    }
    function removeFloatingPreview(){ if(floatingBtn){ floatingBtn.remove(); floatingBtn = null; } }
    function updateFloatingState(){
        if(!floatingBtn) return;
        var total = 0; selectedMap.forEach(function(v){ total += v.count; });
        try{
            var lang = (window.i18nGetLang && window.i18nGetLang()) || 'es';
            var tpl = (window.i18nTranslations && window.i18nTranslations.preview_proposal_float) ? window.i18nTranslations.preview_proposal_float[lang === 'en' ? 'en' : 'es'] : 'Preview propuesta ({n})';
            floatingBtn.textContent = tpl.replace('{n}', String(total));
        }catch(e){ floatingBtn.textContent = 'Preview propuesta ('+total+')'; }
        floatingBtn.disabled = (total === 0);
    }

    async function openPreviewModal(){
        // total count must be > 0
        var total = 0; selectedMap.forEach(function(v){ total += v.count; }); if(total === 0) return;
        // Build headers and info rows in exact selection order (one column per click).
        var headers = [];
        var infos = [];
        var searchKeys = []; // what we send to server to resolve images (neighbor/tech hints)
        selectionSequence.forEach(function(tr){
            try{
                var entry = selectedMap.get(tr) || {};
                var meta = entry.meta || {};
                var cells = Array.from(tr.querySelectorAll('td')).map(function(td){ return td.textContent.trim(); });
                var table = tr.closest('table');
                // neighbor to help distinguish columns of same tech
                var neighbor = '';
                for(var i=2;i<cells.length;i++){ if(cells[i]){ neighbor = cells[i]; break; } }
                if(!neighbor){ try{ var ths = table && table.querySelectorAll('thead tr th'); if(ths && ths.length > 1){ neighbor = ths[1].textContent.trim(); } }catch(e){} }
                if(!neighbor) neighbor = 'col';
                var base = (meta.tech || 'Tecnología') + '_' + neighbor;
                if(!openPreviewModal._occurrenceCounts) openPreviewModal._occurrenceCounts = {};
                var occ = (openPreviewModal._occurrenceCounts[base] || 0) + 1; openPreviewModal._occurrenceCounts[base] = occ;
                var label = base + '_' + occ;
                headers.push(label);
                searchKeys.push(neighbor || meta.tech || label);
                // build tooltip info: Documento + Min/Max PCB
                var parts = [];
                if(meta.doc) parts.push('Documento: ' + meta.doc);
                if(meta.min) parts.push('Min.PCB (L X W) (mm): ' + meta.min);
                if(meta.max) parts.push('Max.PCB (L X W) (mm): ' + meta.max);
                infos.push(parts.join('; '));
            }catch(e){ /* ignore problematic rows */ }
        });
        // reset temporary occurrence counts for next preview
        openPreviewModal._occurrenceCounts = {};
        // Request image srcs for these selection keys from server (batch)
        var headerNames = searchKeys.slice();
        var imagesMap = {};
        try{
            var resp = await fetch('/image_for_headers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ headers: headerNames }) });
            if(resp && resp.ok){
                var j = await resp.json().catch(function(){ return null; });
                if(j && j.images) imagesMap = j.images;
            }
        }catch(e){ imagesMap = {}; }

        var ov = document.createElement('div'); ov.className='info-overlay visible'; ov.style.zIndex=1300;
        var modal = document.createElement('div'); modal.className='info-modal';
        var title = document.createElement('h3'); title.setAttribute('data-i18n','preview_modal_title'); title.textContent = 'Previsualizar propuesta'; modal.appendChild(title);
        var desc = document.createElement('div'); desc.style.marginBottom='8px'; desc.setAttribute('data-i18n','preview_modal_desc'); desc.textContent = 'Vista previa (sin costos). Asigne un nombre para guardar.'; modal.appendChild(desc);

    var t = document.createElement('table'); t.className='data-table'; t.style.width='100%';
    var thead = document.createElement('thead'); var tr = document.createElement('tr');
    headers.forEach(function(h){ var th = document.createElement('th'); th.textContent = h; tr.appendChild(th); }); thead.appendChild(tr); t.appendChild(thead);

    var tbody = document.createElement('tbody'); var imgRow = document.createElement('tr');
    // Use the selectionSequence order to pick images (prefer server-resolved image srcs, fallback to per-row image and placeholder)
        selectionSequence.forEach(function(tr, idx){
        var td = document.createElement('td'); td.style.textAlign='center';
        var entry = selectedMap.get(tr) || {};
        var key = searchKeys[idx];
        var src = '/static/img/placeholder.svg';
        try{
            if(imagesMap && imagesMap[key]) src = imagesMap[key];
            else if(entry.image) src = entry.image;
        }catch(e){ src = (entry.image || '/static/img/placeholder.svg'); }
        var info = infos[idx] || '';
        td.innerHTML = '<img src="'+ String(src).replace(/"/g,'&quot;') + '" title="Ver Info" data-info="'+ String(info).replace(/"/g,'&quot;') +'" style="max-width:120px;max-height:80px;cursor:pointer">';
        imgRow.appendChild(td);
    });
    tbody.appendChild(imgRow);
    var infoRow = document.createElement('tr'); headers.forEach(function(){ var td = document.createElement('td'); td.textContent = ''; infoRow.appendChild(td); }); tbody.appendChild(infoRow);
        t.appendChild(tbody); modal.appendChild(t);

        var formDiv = document.createElement('div'); formDiv.style.display='flex'; formDiv.style.gap='8px'; formDiv.style.marginTop='10px'; formDiv.style.alignItems='center';
        var nameLabel = document.createElement('label'); nameLabel.textContent='Nombre de propuesta (se guardará como Proposal_<nombre>): ';
        var nameInput = document.createElement('input'); nameInput.type='text'; nameInput.id='proposal-name-input'; nameInput.setAttribute('data-i18n-placeholder','proposal_name_placeholder'); nameInput.placeholder='Nombre descriptivo'; nameInput.className='tech-btn'; nameInput.style.marginLeft='8px'; nameLabel.appendChild(nameInput); formDiv.appendChild(nameLabel); modal.appendChild(formDiv);

    var btns = document.createElement('div'); btns.style.display='flex'; btns.style.justifyContent='flex-end'; btns.style.gap='8px'; btns.style.marginTop='12px';
    var cancel = document.createElement('button'); cancel.className='btn'; cancel.setAttribute('data-i18n','cancel'); cancel.textContent='Cancelar';
    var exportBtn = document.createElement('button'); exportBtn.className='btn'; exportBtn.setAttribute('data-i18n','export_excel'); exportBtn.textContent='Guardar Excel'; exportBtn.style.background='#059669'; exportBtn.style.color='#fff';
    var save = document.createElement('button'); save.className='btn'; save.setAttribute('data-i18n','save_db'); save.textContent='Guardar Base de datos'; save.style.background='#0f172a'; save.style.color='#fff';
    btns.appendChild(cancel); btns.appendChild(exportBtn); btns.appendChild(save); modal.appendChild(btns);

        ov.appendChild(modal); document.body.appendChild(ov);
        try{ if(window.i18nApplyLanguage) window.i18nApplyLanguage(window.i18nGetLang ? window.i18nGetLang() : 'es'); }catch(e){}

        cancel.addEventListener('click', function(){ ov.remove(); });
        // Export CSV (Excel-compatible)
        exportBtn.addEventListener('click', function(){
            var suffix = nameInput.value.trim() || ('proposal_' + (Date.now()));
            var filename = 'Proposal_' + suffix + '.csv';
            // Build CSV rows: header row, image placeholder row, empty info row
            var rows = [];
            rows.push(headers);
            var imgRow = headers.map(function(){ return 'PLACEHOLDER_IMAGE'; }); rows.push(imgRow);
            var infoRow = headers.map(function(){ return ''; }); rows.push(infoRow);
            // Convert to CSV string
            var csv = rows.map(function(r){ return r.map(function(cell){ return '"' + String(cell).replace(/"/g,'""') + '"'; }).join(','); }).join('\r\n');
            var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = filename; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(a.href);
        });

        // Save to DB: first require credentials (login/create) in a separate panel, then save
        save.addEventListener('click', function(){
            var suffix = nameInput.value.trim(); if(!suffix){ alert('Ingrese un nombre para la propuesta'); return; }
            var countsArr = headers.map(function(){ return 1; });
            var payload = { name: suffix, columns: headers, counts: countsArr, rows: [] };
            // show auth modal in separate panel before attempting to save
            showAuthModal(function(authOk){
                if(!authOk){ alert('Debe iniciar sesión para guardar la propuesta'); return; }
                // after successful auth, attempt save
                attemptSave(payload, function(result){
                    if(result && result.success){ alert('Proposal creada: '+result.table); ov.remove(); try{ location.reload(); }catch(e){} }
                    else { alert('Error creando proposal: '+(result && result.error ? result.error : 'desconocido')); }
                });
            });
        });
    }

    function injectStyles(){ if(qs('#proposal-builder-styles')) return; var s = document.createElement('style'); s.id='proposal-builder-styles'; s.textContent = '\n.selectable-row{cursor:pointer}\n.selected-row{background:#dbeafe}\n#proposal-preview-float:disabled{opacity:0.5;cursor:not-allowed}\n.proposal-count-badge{padding-right:6px}\n'; document.head.appendChild(s); }
    injectStyles();

    // Restore feature disabled: clear any stored proposal selection so no prompt appears.
    (function disableRestore(){
        try{ clearState(); }catch(e){}
        return;
    })();

    function restoreFromState(st){
        try{
            startSelectionMode();
            restoring = true;
            var tables = qsa('.tabla-container table.data-table');
            var allRows = [];
            tables.forEach(function(t){ t.querySelectorAll('tbody tr').forEach(function(r){ allRows.push(r); }); });
            function rowCells(r){ return Array.from(r.querySelectorAll('td')).map(function(td){ return td.textContent.trim(); }); }
            function normalizeText(s){ return String(s||'').replace(/\s+/g,' ').trim().toLowerCase(); }
            function isNumericString(s){ return /^-?\d+(?:[\.,]\d+)?$/.test(String(s).trim()); }
            function toNumber(s){ if(!s) return NaN; return Number(String(s).replace(',', '.')); }

            function matchRow(sig){
                var parts = sig.split('||'); if(parts.length<2) return null;
                var tech = normalizeText(parts[0]);
                var cellParts = parts[1].split('|').map(function(p){ return normalizeText(p); }).filter(function(x){ return x !== ''; });
                for(var i=0;i<allRows.length;i++){
                    var tr = allRows[i];
                    var table = tr.closest('table');
                    var techLabel = normalizeText(getTechLabelForTable(table));
                    if(tech && techLabel !== tech) continue;
                    var rc = rowCells(tr).map(function(c){ return normalizeText(c); }).filter(function(x){ return x !== ''; });
                    if(rc.length === 0 || cellParts.length === 0) continue;
                    // Try to match each cellPart to some corresponding cell content; allow includes and numeric tolerance
                    var matchedAll = true;
                    for(var j=0;j<cellParts.length;j++){
                        var part = cellParts[j];
                        var found = false;
                        // attempt same index first
                        if(j < rc.length){
                            var cand = rc[j];
                            if(cand === part || cand.indexOf(part) !== -1 || part.indexOf(cand) !== -1) found = true;
                            else if(isNumericString(cand) && isNumericString(part)){
                                var n1 = toNumber(cand), n2 = toNumber(part);
                                if(!isNaN(n1) && !isNaN(n2) && Math.abs(n1 - n2) < 0.5) found = true;
                            }
                        }
                        // fallback: try to find the part in any cell of the row
                        if(!found){
                            for(var k=0;k<rc.length;k++){
                                var cand2 = rc[k];
                                if(cand2 === part || cand2.indexOf(part) !== -1 || part.indexOf(cand2) !== -1){ found = true; break; }
                                if(isNumericString(cand2) && isNumericString(part)){
                                    var m1 = toNumber(cand2), m2 = toNumber(part);
                                    if(!isNaN(m1) && !isNaN(m2) && Math.abs(m1 - m2) < 0.5){ found = true; break; }
                                }
                            }
                        }
                        if(!found){ matchedAll = false; break; }
                    }
                    if(matchedAll) return tr;
                }
                return null;
            }
            // Recreate aggregated counts by signature
            var processed = {};
            st.sequence.forEach(function(sig){
                var tr = matchRow(sig); if(!tr) return;
                var targetCount = (st.counts && st.counts[sig]) ? st.counts[sig] : 1;
                var currentCount = processed[sig] || 0;
                while(currentCount < targetCount){
                    onRowClick({ currentTarget: tr });
                    currentCount++;
                }
                processed[sig] = currentCount;
            });
            restoring = false;
            persistState();
            // return true if we restored at least one selection
            var restoredCount = 0; for(var k in processed) if(processed[k] && processed[k] > 0) restoredCount += processed[k];
            return restoredCount > 0;
        }catch(e){ console.error('restoreFromState error', e); restoring=false; }
    }

    // Attempt to save proposal; if server responds with no auth, prompt user to login/create account and retry
    function attemptSave(payload, cb){
        fetch('/create_proposal', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload), credentials: 'same-origin' })
        .then(function(res){ return res.json().catch(function(){ return { success: false, error: 'invalid response' }; }); })
        .then(function(j){
            if(j && j.success){ if(typeof cb === 'function') cb(j); return; }
            // if server indicates no auth, prompt credentials
            if(j && j.error && String(j.error).toLowerCase().indexOf('no auth') !== -1){
                showAuthModal(function(authOk){
                    if(authOk){
                        // retry once after successful auth
                        fetch('/create_proposal', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload), credentials: 'same-origin' })
                        .then(function(res2){ return res2.json().catch(function(){ return { success: false, error: 'invalid response' }; }); })
                        .then(function(j2){ if(typeof cb === 'function') cb(j2); })
                        .catch(function(err){ if(typeof cb === 'function') cb({ success:false, error: String(err) }); });
                    } else {
                        if(typeof cb === 'function') cb({ success:false, error: 'auth failed or cancelled' });
                    }
                });
                return;
            }
            if(typeof cb === 'function') cb(j);
        }).catch(function(err){ if(typeof cb === 'function') cb({ success:false, error: String(err) }); });
    }

    // Show auth modal: login or create account. Calls onSuccess(true) if auth succeeded, or onSuccess(false) otherwise.
    function showAuthModal(onSuccess){
        var ov = document.createElement('div'); ov.className='info-overlay visible'; ov.style.zIndex = 1400; ov.id = 'proposal-auth-overlay';
        var modal = document.createElement('div'); modal.className='info-modal';
        modal.innerHTML = '<h3 data-i18n="auth_title">Inicia sesión para guardar la propuesta</h3>';
        var box = document.createElement('div'); box.style.display='flex'; box.style.flexDirection='column'; box.style.gap='8px'; box.style.marginTop='8px';
        box.innerHTML = '\n            <label>Usuario: <input id="pb-auth-user" data-i18n-placeholder="auth_user" class="tech-btn" type="text"></label>\n            <label>Contraseña: <input id="pb-auth-pass" data-i18n-placeholder="auth_pass" class="tech-btn" type="password"></label>\n            <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:6px">\n              <button id="pb-login-btn" class="btn" data-i18n="auth_login">Iniciar sesión</button>\n              <button id="pb-create-btn" class="btn" data-i18n="auth_create">Crear cuenta</button>\n              <button id="pb-cancel-btn" class="btn" data-i18n="cancel">Cancelar</button>\n            </div>';
        modal.appendChild(box); ov.appendChild(modal); document.body.appendChild(ov);
        try{ if(window.i18nApplyLanguage) window.i18nApplyLanguage(window.i18nGetLang ? window.i18nGetLang() : 'es'); }catch(e){}

        var userIn = qs('#pb-auth-user'); var passIn = qs('#pb-auth-pass'); var loginBtn = qs('#pb-login-btn'); var createBtn = qs('#pb-create-btn'); var cancelBtn = qs('#pb-cancel-btn');

        // Tooltip guidance on create account button
        if(createBtn){
            var tip = 'Se creará con el usuario y contraseña que ingresaste en esta pantalla';
            createBtn.title = tip;
            createBtn.setAttribute('aria-label', tip);
        }

        function cleanup(){ try{ var e = qs('#proposal-auth-overlay'); if(e) e.remove(); }catch(e){} }

        cancelBtn.addEventListener('click', function(){ cleanup(); if(typeof onSuccess==='function') onSuccess(false); });

        loginBtn.addEventListener('click', function(){
            var u = (userIn.value||'').trim(); var p = passIn.value||''; if(!u || !p){ alert('Ingrese usuario y contraseña'); return; }
            fetch('/user/login', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ user: u, password: p }), credentials: 'same-origin' })
            .then(function(r){ return r.json(); }).then(function(j){ if(j && j.success){ cleanup(); if(typeof onSuccess==='function') onSuccess(true); } else { alert('Login falló: '+(j && j.error? j.error : 'credenciales inválidas')); } }).catch(function(err){ alert('Error al iniciar sesión'); console.error(err); });
        });

        createBtn.addEventListener('click', function(){
            var u = (userIn.value||'').trim(); var p = passIn.value||''; if(!u || !p){ alert('Ingrese usuario y contraseña para crear cuenta'); return; }
            // Confirm action before creating account
            var confirmMsg = 'Se creará una cuenta con el usuario y contraseña ingresados. ¿Deseas continuar?';
            if(!window.confirm(confirmMsg)) return;
            fetch('/user/create_account', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ user: u, password: p }), credentials: 'same-origin' })
            .then(function(r){ return r.json(); }).then(function(j){ if(j && j.success){
                    // after create, perform login to set session
                    fetch('/user/login', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ user: u, password: p }), credentials: 'same-origin' })
                    .then(function(r2){ return r2.json(); }).then(function(j2){ if(j2 && j2.success){ cleanup(); if(typeof onSuccess==='function') onSuccess(true); } else { alert('Cuenta creada, pero login automático falló. Intente iniciar sesión.'); } }).catch(function(err){ alert('Error al iniciar sesión después de crear cuenta'); console.error(err); });
                } else { alert('No se pudo crear cuenta: '+(j && j.error? j.error : 'desconocido')); } }).catch(function(err){ alert('Error creando cuenta'); console.error(err); });
        });
    }

})();
