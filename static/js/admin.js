(function(){
    'use strict';

    function qs(s){ return document.querySelector(s); }
    function qsa(s){ return document.querySelectorAll(s); }

    // sanitize a friendly tecnologia string into the same form server uses for table prefixes
    function sanitizeTechKey(s){
        if(!s) return '';
        try{
            // replace non-alphanumeric and non-underscore with underscore
            var t = String(s).replace(/[^A-Za-z0-9_]/g, '_');
            // collapse multiple underscores
            t = t.replace(/__+/g, '_');
            // trim leading/trailing underscores
            t = t.replace(/^_+|_+$/g, '');
            return t || '';
        }catch(e){ return String(s); }
    }
    // download helper: fetch URL and save blob to disk
    function downloadUrl(url, filenameFallback){
        fetch(url, { credentials: 'same-origin' })
        .then(function(resp){
            if(!resp.ok){
                try{ return resp.json().then(function(j){ alert('Error: '+(j.error||resp.status)); }); }catch(e){ alert('Error exporting'); }
                throw new Error('Export failed');
            }
            return resp.blob();
        })
        .then(function(blob){
            if(!blob) return;
            var blobUrl = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = blobUrl;
            // attempt to infer filename from response headers is skipped; use fallback
            a.download = filenameFallback || 'export.xlsx';
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(function(){ URL.revokeObjectURL(blobUrl); }, 2000);
        }).catch(function(err){ console.error('Download error', err); });
    }

    // Open admin login modal (on index) if present
    var openAdminBtn = qs('#open-admin');
    if(openAdminBtn){
        openAdminBtn.addEventListener('click', function(){
            // show a simple prompt modal to ask credentials (reuse info-overlay if present)
            var html = `
                <div style="display:flex;flex-direction:column;gap:8px;min-width:320px">
                    <label>Usuario:<input id="adm-user" type="text" class="tech-btn" placeholder="Usuario"></label>
                    <label>Contraseña:<input id="adm-pass" type="password" class="tech-btn" placeholder="Contraseña"></label>
                    <div id="caps-warning" class="caps-warning" style="display:none;margin-top:4px;font-size:12px;color:#9b1c1c">Mayúsculas activas</div>
                    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:6px">
                        <button id="adm-submit" class="btn">Acceder</button>
                        <button id="adm-close" class="btn">Cancelar</button>
                    </div>
                </div>`;
            // create overlay
            var ov = document.createElement('div');
            ov.className = 'info-overlay visible';
            ov.id = 'adm-overlay';
            ov.innerHTML = `<div class="info-modal"> <h2>Acceso administrador</h2> <div style='margin-top:8px'>${html}</div></div>`;
            document.body.appendChild(ov);

            var close = document.getElementById('adm-close');
            var submit = document.getElementById('adm-submit');
            var passInput = document.getElementById('adm-pass');
            var capsDiv = document.getElementById('caps-warning');

            // helper: update caps-lock state using the keyboard event if available
            function updateCapsStateFromEvent(e){
                try{
                    if(e && typeof e.getModifierState === 'function'){
                        var on = e.getModifierState('CapsLock');
                        capsDiv.style.display = on ? 'block' : 'none';
                        return;
                    }
                }catch(err){ /* ignore */ }
                // fallback: hide
                capsDiv.style.display = 'none';
            }

            if(passInput){
                passInput.addEventListener('keydown', updateCapsStateFromEvent);
                passInput.addEventListener('keyup', updateCapsStateFromEvent);
                // hide when leaving the field
                passInput.addEventListener('blur', function(){ capsDiv.style.display = 'none'; });
                // on focus we reset and wait for key events
                passInput.addEventListener('focus', function(){ capsDiv.style.display = 'none'; });
            }

            if(close) close.addEventListener('click', function(){ ov.remove(); });
            if(submit) submit.addEventListener('click', function(){
                var usv = document.getElementById('adm-user').value;
                var pv = document.getElementById('adm-pass').value;
                fetch('/admin/login', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({user: usv, password: pv})
                }).then(r=>r.json()).then(j=>{
                    if(j.success){ window.location = '/admin'; }
                    else{ alert('Credenciales incorrectas'); }
                }).catch(e=>{ alert('Error al validar'); console.error(e); });
            });
        });
    }

    // Admin page logic: load table list and render as accordion
    var gTechMap = null;
    function loadTechMap(){
        return fetch('/admin/tech_map').then(function(r){ return r.json(); }).then(function(j){ gTechMap = j.map || {}; }).catch(function(e){ console.error(e); gTechMap = {}; });
    }
    if(qs('#tables')){
        // initial load will populate tech and users, then render tables
            loadTechMap().then(function(){ 
                populateTechFilter();
                populateUserFilter();
                loadAndRenderTables(); 
            });
    }

    // Apply / clear filter buttons
    var applyFiltersBtn = qs('#apply-filters-btn');
    if(applyFiltersBtn){ applyFiltersBtn.addEventListener('click', function(){ loadAndRenderTables(); }); }
    var clearFiltersBtn = qs('#clear-filters-btn');
    if(clearFiltersBtn){ clearFiltersBtn.addEventListener('click', function(){ var t = qs('#admin-tech-filter'); if(t) t.value=''; var p = qs('#admin-proposal-user'); if(p) p.value='__all__'; loadAndRenderTables(); }); }

    function populateTechFilter(){
        fetch('/admin/technologies').then(r=>r.json()).then(function(j){
            var sel = qs('#admin-tech-filter'); if(!sel) return;
            // add empty option
            sel.innerHTML = '<option value="">(Todas)</option>';
            if(j.technologies){ j.technologies.forEach(function(t){ var opt = document.createElement('option'); opt.value = t; opt.textContent = t; sel.appendChild(opt); }); }
        }).catch(console.error);
    }

    function populateUserFilter(){
        fetch('/admin/users').then(r=>r.json()).then(function(j){
            var sel = qs('#admin-proposal-user'); if(!sel) return;
            // keep existing 'Todos' option
            if(j.users){ j.users.forEach(function(u){ var opt = document.createElement('option'); opt.value = u; opt.textContent = u; sel.appendChild(opt); }); }
        }).catch(console.error);
    }

    // Load tables and render with optional filtering by tecnologia and proposal user
    function loadAndRenderTables(){
        var techFilter = (qs('#admin-tech-filter') && qs('#admin-tech-filter').value) || '';
        var proposalUser = (qs('#admin-proposal-user') && qs('#admin-proposal-user').value) || '__all__';
        var filteringProposalsByUser = proposalUser !== '__all__';

        // Important: when filtering proposals by user, we must fetch ALL tables (including proposals),
        // even if a technology is selected, because /admin/tables_for_technology excludes proposals.
        var basePromise;
        if (filteringProposalsByUser) {
            basePromise = fetch('/admin/tables').then(function(r){ return r.json(); });
        } else if (techFilter) {
            basePromise = fetch('/admin/tables_for_technology?tech='+encodeURIComponent(techFilter)).then(function(r){ return r.json(); });
        } else {
            basePromise = fetch('/admin/tables').then(function(r){ return r.json(); });
        }

        basePromise.then(function(j){
            var list = qs('#tables');
            list.innerHTML = '';
            var tableNames = j.tables || [];

            // We'll render cards for tables that pass filters. For proposals filtered by user, we fetch table content to check matches.
            tableNames.forEach(function(t){
                var isProposal = String(t).toUpperCase().indexOf('PROPOSAL_') === 0;

                if (isProposal) {
                    if (!filteringProposalsByUser) {
                        // No user filter -> render all proposals
                        renderTableCard(t);
                    } else {
                        // User filter active -> check rows for matching Usuario
                        fetch('/admin/table?name='+encodeURIComponent(t))
                        .then(function(r2){
                            return r2.text().then(function(txt){
                                function tryParse(s){ try{ return JSON.parse(s); } catch(err){ return { __err: err }; } }
                                var parsed = tryParse(txt);
                                if(!parsed || parsed.__err){
                                    var repaired = String(txt).replace(/\bNaN\b/g, 'null').replace(/\bInfinity\b/g, 'null').replace(/\b-?Inf\b/g, 'null');
                                    var reparsed = tryParse(repaired);
                                    if(reparsed && !reparsed.__err){ return reparsed; }
                                    throw new Error('Respuesta no válida del servidor');
                                }
                                return parsed;
                            });
                        })
                        .then(function(j2){
                            try{
                                var rows = j2.rows || [];
                                var cols = j2.columns || [];
                                var userCol = null;
                                // prefer explicit 'Usuario' or column containing 'usuario'/'user'
                                for(var i=0;i<cols.length;i++){
                                    var c = String(cols[i]||'');
                                    var low = c.toLowerCase();
                                    if(c === 'Usuario' || low.indexOf('usuario') !== -1 || low.indexOf('user') !== -1){ userCol = cols[i]; break; }
                                }
                                var selected = String(proposalUser).trim().toLowerCase();
                                var matches = false;
                                if(userCol){
                                    for(var r=0;r<rows.length;r++){
                                        var v = rows[r][userCol];
                                        if(v != null && String(v).trim().toLowerCase() === selected){ matches = true; break; }
                                    }
                                }
                                if(matches) renderTableCard(t);
                            }catch(e){ /* ignore parsing/match errors per table */ }
                        })
                        .catch(function(){ /* ignore errors per-table */ });
                    }
                } else {
                    // Non-proposal table: render only if not filtering by user
                    if (!filteringProposalsByUser) {
                        renderTableCard(t);
                    }
                }
            });
        }).catch(console.error);
    }

    // Render a single table card (kept same as before)
    function renderTableCard(t){
        var list = qs('#tables');
        var btn = document.createElement('button'); btn.className='tech-btn'; btn.textContent = t;
        var wrap = document.createElement('div'); wrap.className='table-card';
        var body = document.createElement('div'); body.className = 'table-body'; body.style.display='none';
        wrap.appendChild(btn); wrap.appendChild(body);
        btn.addEventListener('click', function(){
            if(body.style.display === 'block'){ body.innerHTML = ''; body.style.display = 'none'; } else { document.querySelectorAll('.table-body').forEach(function(b){ if(b !== body){ b.innerHTML=''; b.style.display='none'; } }); loadTableIntoBody(t, body, wrap); }
        });
        list.appendChild(wrap);
    }

    // New Table button handler (if present on page)
    var newTableBtn = qs('#new-table-btn');
    if(newTableBtn){
        newTableBtn.addEventListener('click', function(){ openCreateTableModal(); });
    }

    var exportAllBtn = qs('#export-all-btn');
    if(exportAllBtn){
        exportAllBtn.addEventListener('click', function(){
            if(!confirm('Exportar todas las tablas en un solo archivo Excel? Las hojas se agruparán por tecnología.')) return;
            downloadUrl('/admin/export_all_tables_excel', 'all_tables_by_tecnologia.xlsx');
        });
    }

    // load table and render into provided body element (accordion behavior)
    function loadTableIntoBody(tableName, bodyEl, wrapEl){
        fetch('/admin/table?name='+encodeURIComponent(tableName))
        .then(function(r){
            return r.text().then(function(txt){
                // Robust JSON parsing with repair for NaN/Infinity if they appear
                function tryParse(s){ try{ return JSON.parse(s); }catch(err){ return { __err: err }; } }
                var parsed = tryParse(txt);
                if(!parsed || parsed.__err){
                    // attempt to repair common invalid tokens
                    var repaired = String(txt).replace(/\bNaN\b/g, 'null').replace(/\bInfinity\b/g, 'null').replace(/\b-?Inf\b/g, 'null');
                    var reparsed = tryParse(repaired);
                    if(reparsed && !reparsed.__err){ return reparsed; }
                    var snippet = (txt || '').slice(0, 400);
                    throw new Error('Respuesta no válida del servidor. Vista previa:\n' + snippet);
                }
                return parsed;
            });
        })
        .then(function(j){
            if(j.error){ alert(j.error); return; }
            bodyEl.innerHTML = '';
            // title + toolbar (delete)
            var titleWrap = document.createElement('div'); titleWrap.style.display='flex'; titleWrap.style.justifyContent='space-between'; titleWrap.style.alignItems='center';
            var title = document.createElement('div'); title.style.marginBottom='8px'; title.innerHTML = `<strong>${tableName}</strong>`;
            titleWrap.appendChild(title);
            var toolbar = document.createElement('div');
            // delete button
            var delBtn = document.createElement('button'); delBtn.className = 'btn'; delBtn.style.background='#b91c1c'; delBtn.style.border='none'; delBtn.style.padding='6px 10px'; delBtn.style.color='#fff'; delBtn.textContent = '🗑️ Eliminar tabla';
            // add spacing to match other toolbar buttons
            delBtn.style.marginRight = '6px';
            delBtn.addEventListener('click', function(){
                openConfirm(`¿Confirmas eliminar la tabla ${tableName}? Esta acción eliminará la tabla de la base de datos.`, function(){ deleteTable(tableName, bodyEl); });
            });
            toolbar.appendChild(delBtn);

            // edit button (pencil) to modify structure or rename
            var editBtn = document.createElement('button'); editBtn.className='btn'; editBtn.style.background='#0f172a'; editBtn.style.color='#fff'; editBtn.style.border='none'; editBtn.style.padding='6px 8px'; editBtn.textContent = '✏️ Editar tabla';
            // spacing to separate from delete button (match export button spacing)
            editBtn.style.marginLeft = '6px';
            editBtn.addEventListener('click', function(){
                openEditTableModal(tableName, j.columns, j.rows, j.tecnologia);
            });
            toolbar.appendChild(editBtn);
            // export table button
            var exportTableBtn = document.createElement('button'); exportTableBtn.className='btn'; exportTableBtn.style.marginLeft='6px'; exportTableBtn.textContent = '💾 Exportar Excel';
            // style to match Edit/Eliminar buttons (smaller, consistent padding)
            exportTableBtn.style.background = '#0f172a';
            exportTableBtn.style.color = '#fff';
            exportTableBtn.style.border = 'none';
            exportTableBtn.style.padding = '6px 8px';
            exportTableBtn.style.fontSize = '13px';
            exportTableBtn.addEventListener('click', function(evt){ evt.stopPropagation(); downloadUrl('/admin/export_table_excel?table='+encodeURIComponent(tableName), tableName + '.xlsx'); });
            toolbar.appendChild(exportTableBtn);
            titleWrap.appendChild(toolbar);
            bodyEl.appendChild(titleWrap);
            // container for table
            var dataWrap = document.createElement('div'); dataWrap.className='data-wrap'; dataWrap.style.maxHeight='45vh'; dataWrap.style.overflow='auto';
            var tbl = document.createElement('table'); tbl.className='data-table'; tbl.style.width='100%';
            // header
            var thead = document.createElement('thead'); var htr = document.createElement('tr');
                j.columns.forEach(function(c){ var th = document.createElement('th'); th.textContent = c; htr.appendChild(th); }); thead.appendChild(htr); tbl.appendChild(thead);
            // body
            var tbody = document.createElement('tbody');
            j.rows.forEach(function(row){
                var tr = document.createElement('tr');
                j.columns.forEach(function(c){
                    var td = document.createElement('td'); td.className='editable-cell';
                    var val = row[c];
                    td.textContent = (val === null ? '' : String(val));
                    td.dataset.table = tableName; td.dataset.col = c; td.dataset.row = JSON.stringify(row);
                    // make cell focusable so keyboard users can interact
                    td.tabIndex = 0;
                    td.addEventListener('click', onEditCell);
                    // allow Enter or Space to open edit modal when cell is focused
                    td.addEventListener('keydown', function(ev){
                        if(ev.key === 'Enter' || ev.key === ' '){ ev.preventDefault(); onEditCell.call(this, ev); }
                    });
                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
            });
            tbl.appendChild(tbody);
            dataWrap.appendChild(tbl);
            bodyEl.appendChild(dataWrap);
            bodyEl.style.display = 'block';
            // scroll into view a bit
            try{ wrapEl.scrollIntoView({behavior:'smooth', block:'start'}); }catch(e){}
        }).catch(function(err){ alert('No se pudo abrir la tabla: '+ (err && err.message ? err.message : String(err))); console.error(err); });
    }

    // Confirmation modal helper
    function openConfirm(message, onConfirm){
        var ov = document.createElement('div'); ov.className='info-overlay visible'; ov.id='confirm-overlay';
        ov.innerHTML = `<div class="info-modal"><h3>Confirmación</h3><div style="margin-top:8px">${escapeHtml(message)}</div><div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px"><button id="confirm-ok" class="btn">Confirmar</button><button id="confirm-cancel" class="btn">Cancelar</button></div></div>`;
        document.body.appendChild(ov);
        qs('#confirm-cancel').addEventListener('click', function(){ ov.remove(); });
        qs('#confirm-ok').addEventListener('click', function(){ try{ onConfirm(); }catch(e){ console.error(e); } ov.remove(); });
    }

    // Delete table via API
    function deleteTable(tableName, bodyEl){
        fetch('/admin/delete_table', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ table: tableName }) })
        .then(r=>r.json()).then(j=>{
            if(j.success){ alert('Tabla eliminada');
                // remove the card from the list and reload tables list
                try{ location.reload(); }catch(e){ }
            } else {
                alert('Error eliminando: '+(j.error||'desconocido'));
            }
        }).catch(e=>{ alert('Error en la petición: '+e); console.error(e); });
    }

    // Create table modal and flow
    function openCreateTableModal(){
        var ov = document.createElement('div'); ov.className='info-overlay visible'; ov.id='create-overlay';
        ov.innerHTML = `<div class="info-modal"><h3>Crear nueva tabla</h3>
            <div id="create-body" style="margin-top:8px;display:flex;flex-direction:column;gap:8px">
                <label>Nombre tabla: <input id="new-table-name" class="tech-btn" placeholder="Nombre de la tabla"></label>
                <div id="name-exists" style="color:#9b1c1c;display:none;font-size:13px">Ya existe una tabla con ese nombre</div>
                <label>Tecnología: <select id="new-table-tech" class="tech-btn"><option value="">(Seleccione)</option></select></label>
                <label>Cantidad de columnas: <input id="new-table-cols" type="number" min="1" value="3" class="tech-btn" style="width:100px"></label>
                <label>Cantidad de filas iniciales: <input id="new-table-rows" type="number" min="0" value="3" class="tech-btn" style="width:100px"></label>
                <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:6px"><button id="create-next" class="btn">Siguiente</button><button id="create-cancel" class="btn">Cancelar</button></div>
            </div></div>`;
        document.body.appendChild(ov);

        // fetch existing tables and technologies for validation & select
        var existingTables = [];
        fetch('/admin/tables').then(r=>r.json()).then(j=>{ if(j.tables) existingTables = j.tables.map(function(x){return String(x).toLowerCase();}); }).catch(console.error);
        fetch('/admin/technologies').then(r=>r.json()).then(j=>{ if(j.technologies){ var sel = qs('#new-table-tech'); j.technologies.forEach(function(t){ var opt = document.createElement('option'); opt.value = t; opt.textContent = t; sel.appendChild(opt); }); } }).catch(console.error);

        qs('#create-cancel').addEventListener('click', function(){ ov.remove(); });

        // validate name as user types
        var nameInput = qs('#new-table-name'); var nameExistsDiv = qs('#name-exists');
        nameInput.addEventListener('input', function(){ var v = nameInput.value.trim().toLowerCase(); if(v && existingTables.indexOf(v) !== -1){ nameExistsDiv.style.display='block'; } else { nameExistsDiv.style.display='none'; } });

        qs('#create-next').addEventListener('click', function(){
            var name = qs('#new-table-name').value.trim();
            var tech = qs('#new-table-tech').value || null;
            var cols = parseInt(qs('#new-table-cols').value,10) || 0;
            var rows = parseInt(qs('#new-table-rows').value,10) || 0;
            if(!name){ alert('Nombre de tabla requerido'); return; }
            if(existingTables.indexOf(name.toLowerCase()) !== -1){ alert('Ya existe una tabla con ese nombre. Elija otro nombre.'); return; }
            if(cols < 1){ alert('Debe haber al menos 1 columna'); return; }
            // build editable grid
            var body = qs('#create-body'); body.innerHTML = '';
            var info = document.createElement('div'); info.innerHTML = `<div style="font-size:13px;color:#333;margin-bottom:8px">Edite los nombres de columna (cabeceras) y los valores. Use los botones para agregar columnas o filas.</div>`;
            body.appendChild(info);
            var table = document.createElement('table'); table.className='data-table'; table.style.width='100%';
            var thead = document.createElement('thead'); var htr = document.createElement('tr');
            for(var c=0;c<cols;c++){ var th = document.createElement('th'); th.contentEditable = true; th.textContent = 'Col'+(c+1); htr.appendChild(th); }
            thead.appendChild(htr); table.appendChild(thead);
            var tbody = document.createElement('tbody');
            for(var r=0;r<rows;r++){ var tr = document.createElement('tr'); for(var c=0;c<cols;c++){ var td = document.createElement('td'); td.contentEditable = true; td.textContent = ''; tr.appendChild(td); } tbody.appendChild(tr); }
            table.appendChild(tbody); body.appendChild(table);

            // controls: add col, add row, save, cancel
            var controlsTop = document.createElement('div'); controlsTop.style.display='flex'; controlsTop.style.justifyContent='flex-start'; controlsTop.style.gap='8px';
            var addColBtn = document.createElement('button'); addColBtn.className='btn'; addColBtn.textContent='➕ Agregar columna';
            var addRowBtn = document.createElement('button'); addRowBtn.className='btn'; addRowBtn.textContent='➕ Agregar fila';
            controlsTop.appendChild(addColBtn); controlsTop.appendChild(addRowBtn);
            body.insertBefore(controlsTop, table);

            addColBtn.addEventListener('click', function(){
                // add header
                var newTh = document.createElement('th'); newTh.contentEditable = true; newTh.textContent = 'Col'+(table.querySelectorAll('thead th').length+1);
                table.querySelector('thead tr').appendChild(newTh);
                // add cell to each existing row
                table.querySelectorAll('tbody tr').forEach(function(tr){ var td = document.createElement('td'); td.contentEditable = true; td.textContent = ''; tr.appendChild(td); });
            });

            addRowBtn.addEventListener('click', function(){
                var colsCount = table.querySelectorAll('thead th').length;
                var tr = document.createElement('tr'); for(var i=0;i<colsCount;i++){ var td = document.createElement('td'); td.contentEditable = true; td.textContent = ''; tr.appendChild(td); } table.querySelector('tbody').appendChild(tr);
            });

            var controls = document.createElement('div'); controls.style.display='flex'; controls.style.justifyContent='flex-end'; controls.style.gap='8px'; controls.style.marginTop='10px';
            var saveBtn = document.createElement('button'); saveBtn.className='btn'; saveBtn.textContent='Guardar tabla';
            var cancelBtn = document.createElement('button'); cancelBtn.className='btn'; cancelBtn.textContent='Cancelar';
            controls.appendChild(saveBtn); controls.appendChild(cancelBtn); body.appendChild(controls);
            cancelBtn.addEventListener('click', function(){ ov.remove(); });
            saveBtn.addEventListener('click', function(){
                // collect columns
                var headers = Array.from(table.querySelectorAll('thead th')).map(function(th){ return th.textContent.trim() || 'col'; });
                // collect rows
                var dataRows = Array.from(table.querySelectorAll('tbody tr')).map(function(tr){ return Array.from(tr.children).map(function(td){ return td.textContent; }); });
                // confirm
                if(!confirm('¿Confirmas crear la tabla "'+name+'" con '+headers.length+' columnas y '+dataRows.length+' filas?')) return;
                var payload = { table: name, columns: headers, rows: dataRows, tecnologia: tech };
                fetch('/admin/create_table', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) })
                .then(r=>r.json()).then(j=>{
                    if(j.success){ alert('Tabla creada'); ov.remove(); try{ location.reload(); }catch(e){} }
                    else{ alert('Error creando: '+(j.error||'desconocido')); }
                }).catch(e=>{ alert('Error en la petición'); console.error(e); });
            });
        });
    }

    // Edit table modal: rename, add columns, add new rows
    function openEditTableModal(oldName, columns, rows, currentTech){
        var ov = document.createElement('div'); ov.className='info-overlay visible'; ov.id='edit-table-overlay';
        ov.innerHTML = `<div class="info-modal"><h3>Editar tabla: ${escapeHtml(oldName)}</h3>
            <div id="edit-table-body" style="margin-top:8px;display:flex;flex-direction:column;gap:8px">
                <label>Nuevo nombre base: <input id="edit-table-base" class="tech-btn" value="${escapeAttr(extractBaseName(oldName, currentTech))}"></label>
                <label>Tecnología: <select id="edit-table-tech" class="tech-btn"><option value="">(Seleccione)</option></select></label>
                <div style="font-size:13px;color:#333">Encabezados y filas existentes (no se duplicarán). Use los botones para agregar nuevas filas o columnas que serán insertadas.</div>
            </div></div>`;
        document.body.appendChild(ov);

        // populate technology select
        fetch('/admin/technologies').then(r=>r.json()).then(j=>{
            var sel = qs('#edit-table-tech');
            if(j.technologies){ j.technologies.forEach(function(t){ var opt = document.createElement('option'); opt.value=t; opt.textContent=t; sel.appendChild(opt); }); }
            if(currentTech){ sel.value = currentTech; }
        }).catch(console.error);

        // build table area (with left-side row delete control and a tfoot with column delete controls)
        var body = qs('#edit-table-body');
        var table = document.createElement('table'); table.className='data-table'; table.style.width='100%';
        var thead = document.createElement('thead'); var htr = document.createElement('tr');
        // control column header (empty)
        var controlTh = document.createElement('th'); controlTh.textContent = ''; htr.appendChild(controlTh);
        // column headers (editable)
        columns.forEach(function(c){ var th = document.createElement('th'); th.textContent = c; th.contentEditable = true; htr.appendChild(th); });
        thead.appendChild(htr); table.appendChild(thead);
        var tbody = document.createElement('tbody');
        var originalRowCount = rows.length;
        // store deleted columns and deleted rows info locally for this modal
        var deletedColumns = [];
        // render existing rows as editable so user can change existing values
        rows.forEach(function(r, rowIdx){
            var tr = document.createElement('tr');
            // row-delete control at left
            var ctl = document.createElement('td'); ctl.style.width='40px'; ctl.style.textAlign='center';
            var delBtn = document.createElement('button'); delBtn.className='btn'; delBtn.style.padding='4px 6px'; delBtn.style.fontSize='12px'; delBtn.textContent='🗑';
            delBtn.title = 'Eliminar fila';
            delBtn.addEventListener('click', function(){
                if(!confirm('¿Confirmas eliminar esta fila?')) return;
                // if original row, mark as deleted and hide; otherwise remove from DOM
                if(rowIdx < originalRowCount){ tr.dataset.deleted = '1'; tr.style.display = 'none'; }
                else { tr.remove(); }
            });
            ctl.appendChild(delBtn); tr.appendChild(ctl);
            columns.forEach(function(c){
                var td = document.createElement('td');
                var txt = (r && r[c] !== null && typeof r[c] !== 'undefined') ? String(r[c]) : '';
                td.textContent = txt;
                td.contentEditable = true; // allow editing existing cells
                // store original value and original row data for later change detection
                td.dataset.original = txt;
                td.dataset.rowIndex = rowIdx;
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        // foot row for column delete controls
        var tfoot = document.createElement('tfoot');
        var ftr = document.createElement('tr');
        // empty cell under control column
        var emptyFoot = document.createElement('td'); emptyFoot.textContent = '';
        ftr.appendChild(emptyFoot);
        // add a delete button under each column header
        columns.forEach(function(c, ci){
            var fd = document.createElement('td'); fd.style.textAlign='center';
            var colDel = document.createElement('button'); colDel.className='btn'; colDel.style.padding='4px 6px'; colDel.style.fontSize='12px'; colDel.textContent='✖';
            colDel.title = 'Eliminar columna';
            colDel.addEventListener('click', function(){
                if(!confirm('¿Confirmas eliminar la columna "'+c+'"? Esta acción eliminará los datos en esa columna.')) return;
                // determine header index (accounting for control column at index 0)
                // find current headers list to compute the index
                var headers = Array.from(table.querySelectorAll('thead th'));
                var targetIndex = -1;
                for(var i=1;i<headers.length;i++){ if(headers[i].textContent === c){ targetIndex = i; break; } }
                if(targetIndex === -1){ alert('No se encontró la columna en la tabla'); return; }
                // remove header
                headers[targetIndex].remove();
                // remove each cell in tbody for that column
                Array.from(table.querySelectorAll('tbody tr')).forEach(function(tr){ var cells = tr.children; if(cells[targetIndex]) cells[targetIndex].remove(); });
                // remove footer cell (we will rebuild footer below)
                // track deleted column
                deletedColumns.push(c);
                // rebuild footer to reflect remaining columns
                rebuildFooter();
            });
            fd.appendChild(colDel); ftr.appendChild(fd);
        });
        tfoot.appendChild(ftr); table.appendChild(tfoot);
        body.appendChild(table);

        function rebuildFooter(){
            // remove existing tfoot and recreate based on current headers
            var old = table.querySelector('tfoot'); if(old) old.remove();
            var headers = Array.from(table.querySelectorAll('thead th')).slice(1); // skip control
            var newTfoot = document.createElement('tfoot'); var newTr = document.createElement('tr');
            newTr.appendChild(document.createElement('td'));
            headers.forEach(function(th){ var td = document.createElement('td'); td.style.textAlign='center'; var b = document.createElement('button'); b.className='btn'; b.style.padding='4px 6px'; b.style.fontSize='12px'; b.textContent='✖'; b.title='Eliminar columna'; b.addEventListener('click', function(){ if(!confirm('¿Confirmas eliminar la columna "'+th.textContent+'"?')) return; // remove header and cells
                    // find index
                    var allHeaders = Array.from(table.querySelectorAll('thead th'));
                    var idx = allHeaders.indexOf(th);
                    if(idx === -1) return; allHeaders[idx].remove(); Array.from(table.querySelectorAll('tbody tr')).forEach(function(tr){ var c = tr.children; if(c[idx]) c[idx].remove(); }); deletedColumns.push(th.textContent); rebuildFooter(); }); td.appendChild(b); newTr.appendChild(td); });
            newTfoot.appendChild(newTr); table.appendChild(newTfoot);
        }

        // controls
        var controlsTop = document.createElement('div'); controlsTop.style.display='flex'; controlsTop.style.gap='8px';
        var addColBtn = document.createElement('button'); addColBtn.className='btn'; addColBtn.textContent='➕ Agregar columna';
        var addRowBtn = document.createElement('button'); addRowBtn.className='btn'; addRowBtn.textContent='➕ Agregar fila (nueva)';
        controlsTop.appendChild(addColBtn); controlsTop.appendChild(addRowBtn); body.insertBefore(controlsTop, table);

        addColBtn.addEventListener('click', function(){
            var newTh = document.createElement('th'); newTh.contentEditable = true; newTh.textContent = 'col'+(table.querySelectorAll('thead th').length); // account for control column
            table.querySelector('thead tr').appendChild(newTh);
            // add empty cell to each existing row (after control cell)
            table.querySelectorAll('tbody tr').forEach(function(tr){ var td = document.createElement('td'); td.textContent=''; td.contentEditable = true; tr.appendChild(td); });
            // rebuild footer
            rebuildFooter();
        });

        addRowBtn.addEventListener('click', function(){
            var colsCount = table.querySelectorAll('thead th').length; // includes control
            var tr = document.createElement('tr');
            // control cell
            var ctl = document.createElement('td'); ctl.style.width='40px'; ctl.style.textAlign='center';
            var delBtn = document.createElement('button'); delBtn.className='btn'; delBtn.style.padding='4px 6px'; delBtn.style.fontSize='12px'; delBtn.textContent='🗑'; delBtn.title='Eliminar fila';
            delBtn.addEventListener('click', function(){ if(!confirm('¿Confirmas eliminar esta fila?')) return; tr.remove(); });
            ctl.appendChild(delBtn); tr.appendChild(ctl);
            for(var i=1;i<colsCount;i++){ var td = document.createElement('td'); td.contentEditable = true; td.dataset.new = '1'; td.textContent=''; tr.appendChild(td); }
            table.querySelector('tbody').appendChild(tr);
        });

        var controls = document.createElement('div'); controls.style.display='flex'; controls.style.justifyContent='flex-end'; controls.style.gap='8px'; controls.style.marginTop='10px';
        var saveBtn = document.createElement('button'); saveBtn.className='btn'; saveBtn.textContent='Guardar cambios';
        var cancelBtn = document.createElement('button'); cancelBtn.className='btn'; cancelBtn.textContent='Cancelar';
        controls.appendChild(saveBtn); controls.appendChild(cancelBtn); body.appendChild(controls);
        cancelBtn.addEventListener('click', function(){ ov.remove(); });

            saveBtn.addEventListener('click', function(){
            var base = qs('#edit-table-base').value.trim();
            var tech = qs('#edit-table-tech').value || null;
            if(!base){ alert('El nombre base es requerido'); return; }
            // build headers array (skip the first control column)
            var headers = Array.from(table.querySelectorAll('thead th')).slice(1).map(function(th){ return th.textContent.trim() || 'col'; });
            // collect only new rows (those appended after originalRowCount)
            var newRows = [];
            table.querySelectorAll('tbody tr').forEach(function(tr, idx){
                if(idx >= originalRowCount){ // appended rows
                    // skip control cell
                    var vals = Array.from(tr.children).slice(1).map(function(td){ return td.textContent; });
                    // ignore entirely empty rows
                    var any = vals.some(function(v){ return String(v||'').trim() !== ''; });
                    if(any) newRows.push(vals);
                }
            });

            // detect edited existing cells (account for control cell at index 0)
            var editedCells = [];
            var tbodyRows = table.querySelectorAll('tbody tr');
            tbodyRows.forEach(function(tr, rIdx){
                if(rIdx < originalRowCount && tr.dataset.deleted !== '1'){
                    var tds = Array.from(tr.children).slice(1); // skip control cell
                    tds.forEach(function(td, cIdx){
                        var orig = td.dataset.original || '';
                        var cur = td.textContent || '';
                        if(String(orig) !== String(cur)){
                            editedCells.push({ rowIndex: rIdx, colIndex: cIdx, column: headers[cIdx], original: orig, value: cur });
                        }
                    });
                }
            });

            // compute final table name
            var finalName = base;
            if(tech){ finalName = (String(tech).trim() + '_' + String(base).trim()).replace(/[^A-Za-z0-9_]/g,'_'); }

            // collect deleted existing rows
            var deletedRows = [];
            table.querySelectorAll('tbody tr').forEach(function(tr, idx){ if(idx < originalRowCount && tr.dataset.deleted === '1'){ var origData = rows[idx] || {}; deletedRows.push(origData); }});
            // collect deleted columns (as tracked by rebuildFooter and deletedColumns array)
            var deletedColumnsList = (typeof deletedColumns !== 'undefined') ? deletedColumns.slice() : [];

            // confirm and send alter request first (rename, add cols, insert new rows)
            if(!confirm('¿Confirmas aplicar los cambios (añadir columnas/filas, renombrar y aplicar ediciones)?')) return;
            var payload = { old_table: oldName, columns: headers, rows: newRows, new_table: finalName, tecnologia: tech, deleted_rows: deletedRows, deleted_columns: deletedColumnsList, original_columns: columns };
            fetch('/admin/alter_table', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) })
            .then(r=>r.json()).then(function(j){
                if(!j.success){ alert('Error al aplicar estructura: '+(j.error||'desconocido')); return; }
                // After structure changes applied, run per-cell updates for edited existing cells
                if(editedCells.length === 0){ alert('Cambios aplicados'); ov.remove(); try{ location.reload(); }catch(e){}; return; }
                // perform updates sequentially to make debugging easier
                var seq = Promise.resolve();
                editedCells.forEach(function(ec){
                    seq = seq.then(function(){
                        // build original_row object from the original rows array passed into the modal
                        var original_row = {};
                        var originalData = rows[ec.rowIndex] || {};
                        headers.forEach(function(h, idx){ original_row[h] = originalData[h]; });
                        var updPayload = { table: finalName, column: ec.column, original_row: original_row, new_value: ec.value };
                        return fetch('/admin/update', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(updPayload) })
                        .then(function(res){ return res.json(); })
                        .then(function(rj){ if(!rj.success){ throw new Error(rj.error || 'update failed'); } });
                    });
                });
                seq.then(function(){ alert('Cambios aplicados'); ov.remove(); try{ location.reload(); }catch(e){}; })
                .catch(function(err){ alert('Error aplicando algunas ediciones: '+err); console.error(err); });
            }).catch(function(e){ alert('Error en la petición: '+e); console.error(e); });
        });
    }

    function extractBaseName(fullName, tech){
        try{
            if(tech && fullName.indexOf(tech+'_') === 0){ return fullName.substring(tech.length+1); }
            return fullName;
        }catch(e){ return fullName; }
    }

    // Edit modal handlers
    function onEditCell(e){
        var td = e.currentTarget;
        var table = td.dataset.table; var col = td.dataset.col; var row = JSON.parse(td.dataset.row);
        var original = td.textContent;
        openEditModal(table, col, row, original, td);
    }

    var currentEdit = null;
    function openEditModal(table, col, row, original, tdNode){
        currentEdit = {table:table, col:col, row:row, td:tdNode};
        var ov = qs('#edit-overlay'); ov.classList.add('visible'); ov.setAttribute('aria-hidden','false');
        qs('#edit-title').textContent = `Editar ${col} en ${table}`;
        qs('#edit-body').innerHTML = `<div style="display:flex;flex-direction:column;gap:8px">
            <div><strong>Valor original:</strong><div style="padding:8px;background:#f8fafc;border-radius:6px">${escapeHtml(original)}</div></div>
            <div><label>Nuevo valor:<input id="edit-new" class="tech-btn" value="${escapeAttr(original)}"></label></div>
            <div style="font-size:12px;color:#666">Al guardar se pedirá confirmación antes de ejecutar el UPDATE.</div>
        </div>`;
        qs('#edit-save').onclick = doSaveEdit;
        qs('#edit-cancel').onclick = closeEditModal;
        qs('#edit-close').onclick = closeEditModal;
    }

    function closeEditModal(){ var ov = qs('#edit-overlay'); if(ov){ ov.classList.remove('visible'); ov.setAttribute('aria-hidden','true'); } currentEdit=null; }

    function doSaveEdit(){
        var nv = qs('#edit-new').value;
        if(!confirm('¿Confirmas que deseas actualizar el valor seleccionado?')) return;
        var payload = { table: currentEdit.table, column: currentEdit.col, original_row: currentEdit.row, new_value: nv };
        fetch('/admin/update', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) })
        .then(r=>r.json()).then(j=>{
            if(j.success){
                alert('Actualizado');
                // update cell text
                currentEdit.td.textContent = nv;
                closeEditModal();
            } else {
                alert('Error: '+(j.error||'no se pudo actualizar'));
            }
        }).catch(e=>{ alert('Error en la petición'); console.error(e); });
    }

    function escapeHtml(s){ return String(s).replace(/[&<>]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; }); }
    function escapeAttr(s){ return String(s).replace(/"/g,'&quot;'); }

})();
