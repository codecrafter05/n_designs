// Shared site behaviour — nav appearance on scroll
(function(){
  const nav = document.getElementById('siteNav');
  if(!nav) return;
  const hero = document.querySelector('.hero');

  function onScroll(){
    const scrolled = window.scrollY > 8;
    nav.classList.toggle('is-scrolled', scrolled);
    // Homepage hero: switch bar, links, and logo together on the first scroll
    if(hero){
      if(scrolled){
        nav.classList.remove('on-hero');
        nav.querySelector('#navLogo')?.setAttribute('src','/static/img/logo/logo-dark-one.png');
      } else {
        nav.classList.add('on-hero');
        nav.querySelector('#navLogo')?.setAttribute('src','/static/img/logo/logo-light-one.png');
      }
    }
  }
  window.addEventListener('scroll', onScroll, {passive:true});
  onScroll();
})();

(function(){
  const btn = document.getElementById('navMenuBtn');
  const drawer = document.getElementById('navDrawer');
  const overlay = document.getElementById('navDrawerOverlay');
  const closeBtn = document.getElementById('navDrawerClose');
  if(!btn || !drawer || !overlay) return;

  function openMenu(){
    drawer.classList.add('is-open');
    overlay.classList.add('is-open');
    overlay.hidden = false;
    drawer.setAttribute('aria-hidden', 'false');
    btn.setAttribute('aria-expanded', 'true');
    document.body.classList.add('nav-open');
  }

  function closeMenu(){
    drawer.classList.remove('is-open');
    overlay.classList.remove('is-open');
    drawer.setAttribute('aria-hidden', 'true');
    btn.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('nav-open');
    window.setTimeout(function(){
      if(!drawer.classList.contains('is-open')) overlay.hidden = true;
    }, 400);
  }

  btn.addEventListener('click', function(){
    if(drawer.classList.contains('is-open')) closeMenu();
    else openMenu();
  });
  closeBtn?.addEventListener('click', closeMenu);
  overlay.addEventListener('click', closeMenu);
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape') closeMenu();
  });
})();

(function(){
  var badge = document.getElementById('cartBadge');
  var toast = document.getElementById('sfToast');
  var toastText = toast ? toast.querySelector('.sf-toast-text') : null;
  var toastAction = toast ? toast.querySelector('.sf-toast-action') : null;
  var toastTimer = null;
  var actionFn = null;

  window.updateCartBadge = function(count){
    if(!badge) return;
    var n = parseInt(count, 10) || 0;
    if(n > 0){
      badge.hidden = false;
      badge.textContent = n;
      badge.classList.remove('is-pulse');
      void badge.offsetWidth;
      badge.classList.add('is-pulse');
    } else {
      badge.hidden = true;
      badge.textContent = '';
    }
  };

  window.showStorefrontToast = function(text, opts){
    if(!toast || !toastText) return;
    opts = opts || {};
    clearTimeout(toastTimer);
    toastText.textContent = text;
    actionFn = opts.onAction || null;
    if(toastAction){
      if(opts.action){
        toastAction.hidden = false;
        toastAction.textContent = opts.action;
      } else {
        toastAction.hidden = true;
        toastAction.textContent = '';
      }
    }
    toast.hidden = false;
    requestAnimationFrame(function(){ toast.classList.add('is-open'); });
    toastTimer = setTimeout(function(){
      toast.classList.remove('is-open');
      setTimeout(function(){ toast.hidden = true; }, 280);
    }, opts.duration || 4200);
  };

  if(toastAction){
    toastAction.addEventListener('click', function(){
      if(actionFn) actionFn();
      toast.classList.remove('is-open');
      toast.hidden = true;
    });
  }

  window.flyToCart = function(fromEl, visualEl){
    var cart = document.getElementById('navCart');
    if(!fromEl || !cart) return;
    var from = fromEl.getBoundingClientRect();
    var size = 60;
    var startLeft = from.left + from.width / 2 - size / 2;
    var startTop = from.top + from.height / 2 - size / 2;
    var clone;
    if(visualEl && visualEl.tagName === 'IMG' && visualEl.src){
      clone = document.createElement('img');
      clone.src = visualEl.src;
      clone.alt = '';
    } else {
      clone = fromEl.cloneNode(true);
      clone.removeAttribute('id');
    }
    clone.className = 'cart-fly';
    clone.style.top = startTop + 'px';
    clone.style.left = startLeft + 'px';
    clone.style.width = size + 'px';
    clone.style.height = size + 'px';
    document.body.appendChild(clone);
    requestAnimationFrame(function(){
      var to = cart.getBoundingClientRect();
      var dx = to.left + to.width / 2 - (startLeft + size / 2);
      var dy = to.top + to.height / 2 - (startTop + size / 2);
      clone.style.transform = 'translate(' + dx + 'px,' + dy + 'px) scale(0.18)';
      clone.style.opacity = '0.15';
    });
    clone.addEventListener('transitionend', function(){ clone.remove(); });
    setTimeout(function(){ if(clone.parentNode) clone.remove(); }, 900);
  };

  var DIAL_CODES = [
    { code: '+973', country: 'Bahrain' },
    { code: '+966', country: 'Saudi Arabia' },
    { code: '+971', country: 'United Arab Emirates' },
    { code: '+965', country: 'Kuwait' }
  ];

  function parseDialPhone(raw) {
    var original = (raw || '').trim();
    var compact = original.replace(/[\s\-()]/g, '');
    if (!compact) return { code: null, local: '' };
    var ranked = DIAL_CODES.slice().sort(function (a, b) { return b.code.length - a.code.length; });
    for (var i = 0; i < ranked.length; i++) {
      var code = ranked[i].code;
      if (compact.indexOf(code) === 0) {
        return { code: code, local: compact.slice(code.length) };
      }
    }
    return { code: '', local: original };
  }

  function composeDialPhone(code, local) {
    local = (local || '').trim();
    if (!local) return '';
    if (!code) return local;
    var compact = local.replace(/[\s\-()]/g, '');
    if (compact.indexOf(code) === 0) {
      local = compact.slice(code.length);
    }
    local = local.replace(/^[\s\-()]+/, '');
    if (!local) return '';
    return code + ' ' + local;
  }

  function bindPhoneGroup(group) {
    var dial = group.querySelector('[data-phone-dial]');
    var local = group.querySelector('[data-phone-local]');
    var hidden = group.querySelector('[data-phone-full]');
    if (!dial || !local || !hidden) return;
    var form = group.closest('form');
    var country = form ? form.querySelector('#country, select[name="country"]') : null;

    function syncHidden() {
      hidden.value = composeDialPhone(dial.value, local.value);
    }

    function applyCountry() {
      if (!country) return;
      var match = DIAL_CODES.find(function (row) { return row.country === country.value; });
      dial.value = match ? match.code : '';
      syncHidden();
    }

    var parsed = parseDialPhone(hidden.value);
    if (parsed.code === null) {
      if (country) applyCountry();
      else dial.value = '+973';
      local.value = '';
    } else {
      dial.value = parsed.code;
      local.value = parsed.local;
    }
    syncHidden();

    dial.addEventListener('change', syncHidden);
    local.addEventListener('input', syncHidden);
    if (country) {
      country.addEventListener('change', applyCountry);
    }
    if (form) {
      form.addEventListener('submit', syncHidden);
    }
  }

  document.querySelectorAll('[data-phone-group]').forEach(bindPhoneGroup);
})();
