(function(){
    'use strict';
    function showOverlay(){
        var o = document.getElementById('loading-overlay');
        if(!o) return;
        o.classList.add('visible');
        o.setAttribute('aria-hidden','false');
    }
    function hideOverlay(){
        var o = document.getElementById('loading-overlay');
        if(!o) return;
        o.classList.remove('visible');
        o.setAttribute('aria-hidden','true');
    }

    document.addEventListener('DOMContentLoaded', function(){
        // ensure overlay hidden when page loads
        hideOverlay();

        // show overlay on clicks of links with .show-loading
        var links = document.querySelectorAll('a.show-loading');
        links.forEach(function(a){
            a.addEventListener('click', function(e){
                var href = a.getAttribute('href');
                // don't show for anchors or empty href
                if(!href || href.startsWith('#')) return;
                showOverlay();
                // allow navigation to proceed
            });
        });

        // show overlay on form submits with .show-loading
        var forms = document.querySelectorAll('form.show-loading');
        forms.forEach(function(f){
            f.addEventListener('submit', function(){ showOverlay(); });
        });

        // hide overlay when the page is fully loaded or revisited from bfcache
        window.addEventListener('load', hideOverlay);
        window.addEventListener('pageshow', hideOverlay);
    });
})();
