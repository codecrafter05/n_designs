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

  function codesFromDial(dial) {
    return Array.from(dial.options).filter(function (opt) { return opt.value; }).map(function (opt) {
      return { code: opt.value, country: opt.getAttribute('data-country') || '' };
    });
  }

  function parseDialPhone(raw, dialCodes) {
    var original = (raw || '').trim();
    var compact = original.replace(/[\s\-()]/g, '');
    if (!compact) return { code: null, local: '' };
    var ranked = (dialCodes || []).slice().sort(function (a, b) { return b.code.length - a.code.length; });
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
    var dialCodes = codesFromDial(dial);
    var fallback = (dial.options[0] && dial.options[0].value) || '+973';

    function syncHidden() {
      hidden.value = composeDialPhone(dial.value, local.value);
    }

    function applyCountry() {
      if (!country) return;
      var match = dialCodes.find(function (row) { return row.country === country.value; });
      if (match) dial.value = match.code;
      syncHidden();
    }

    var parsed = parseDialPhone(hidden.value, dialCodes);
    if (parsed.code === null) {
      if (country) applyCountry();
      else dial.value = fallback;
      local.value = '';
    } else {
      dial.value = parsed.code;
      if (!dial.value) dial.value = fallback;
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
    group.addEventListener('nd-phone-refresh', function () {
      var parsed = parseDialPhone(hidden.value, dialCodes);
      if (parsed.code === null) {
        if (country) applyCountry();
        else {
          dial.value = fallback;
          local.value = '';
        }
      } else {
        dial.value = parsed.code;
        if (!dial.value) dial.value = fallback;
        local.value = parsed.local;
      }
      syncHidden();
    });
  }

  document.querySelectorAll('[data-phone-group]').forEach(bindPhoneGroup);
})();

(function () {
  var KEY = 'nd_checkout_draft';
  window.clearCheckoutDraft = function () {
    try { localStorage.removeItem(KEY); } catch (e) {}
  };
})();

(function(){
  var DRESS_SIZES = [
    { size: 'XS', uk: '4-6', us: '0-2', eu: '32-34', chest: [78.7, 81.3], waist: [61.0, 63.5], hips: [83.8, 86.4] },
    { size: 'S', uk: '8-10', us: '4-6', eu: '36-38', chest: [83.8, 88.9], waist: [66.0, 71.1], hips: [88.9, 94.0] },
    { size: 'M', uk: '12-14', us: '8-10', eu: '40-42', chest: [94.0, 99.1], waist: [76.2, 78.7], hips: [99.1, 104.1] },
    { size: 'L', uk: '16-18', us: '12-14', eu: '44-46', chest: [104.1, 109.2], waist: [83.8, 91.4], hips: [109.2, 116.8] },
    { size: 'XL', uk: '20-22', us: '16-18', eu: '48-50', chest: [116.8, 121.9], waist: [99.1, 104.1], hips: [124.5, 129.5] },
    { size: 'XXL', uk: '24-26', us: '20-22', eu: '52-54', chest: [129.5, 137.2], waist: [111.8, 119.4], hips: [137.2, 144.8] },
    { size: 'XXXL', uk: '28-30', us: '24-26', eu: '56-58', chest: [144.8, 149.9], waist: [127.0, 132.1], hips: [152.4, 157.5] },
    { size: '4XL', uk: '32-34', us: '28-30', eu: '60-62', chest: [154.9, 162.6], waist: [139.7, 147.3], hips: [161.3, 166.4] }
  ];

  var overlay = document.getElementById('sizeModal');
  if (!overlay) return;

  function formatMeasure(range, unit) {
    if (unit === 'in') {
      return (range[0] / 2.54).toFixed(1) + '-' + (range[1] / 2.54).toFixed(1);
    }
    return range[0].toFixed(1) + '-' + range[1].toFixed(1);
  }

  function renderDressTable(unit) {
    var body = document.getElementById('dressSizeBody');
    if (!body) return;
    var suffix = unit === 'in' ? ' (in)' : ' (cm)';
    document.getElementById('dressColChest').textContent = 'Chest' + suffix;
    document.getElementById('dressColWaist').textContent = 'Waist' + suffix;
    document.getElementById('dressColHips').textContent = 'Hips' + suffix;
    body.replaceChildren();
    DRESS_SIZES.forEach(function (row) {
      var tr = document.createElement('tr');
      [row.size, row.uk, row.us, row.eu,
        formatMeasure(row.chest, unit),
        formatMeasure(row.waist, unit),
        formatMeasure(row.hips, unit)
      ].forEach(function (value) {
        var td = document.createElement('td');
        td.textContent = value;
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    overlay.querySelectorAll('[data-size-unit]').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.getAttribute('data-size-unit') === unit);
    });
  }

  function openSizeGuideModal(event) {
    if (event) event.preventDefault();
    overlay.classList.add('is-open');
  }

  function closeSizeGuideModal() {
    overlay.classList.remove('is-open');
  }

  window.openSizeGuideModal = openSizeGuideModal;
  window.closeSizeGuideModal = closeSizeGuideModal;

  renderDressTable('cm');
  overlay.querySelectorAll('[data-size-unit]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      renderDressTable(btn.getAttribute('data-size-unit'));
    });
  });

  document.querySelectorAll('[data-open-size-guide]').forEach(function (trigger) {
    trigger.addEventListener('click', openSizeGuideModal);
  });

  var closeBtn = document.getElementById('sizeModalClose');
  if (closeBtn) closeBtn.addEventListener('click', closeSizeGuideModal);
  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) closeSizeGuideModal();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeSizeGuideModal();
  });
})();
