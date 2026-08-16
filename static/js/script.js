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
