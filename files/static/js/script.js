// Shared site behaviour — nav appearance on scroll
(function(){
  const nav = document.getElementById('siteNav');
  if(!nav) return;
  const hero = document.querySelector('.hero');

  function onScroll(){
    const y = window.scrollY;
    if(y > 40){
      nav.classList.add('is-scrolled');
    } else {
      nav.classList.remove('is-scrolled');
    }
    // Only pages with a dark full-bleed hero start with light-on-dark nav text
    if(hero){
      const heroBottom = hero.getBoundingClientRect().bottom;
      if(heroBottom < 90){
        nav.classList.remove('on-hero');
        nav.querySelector('#navLogo')?.setAttribute('src','/static/img/logo/logo-dark.png');
      } else {
        nav.classList.add('on-hero');
        nav.querySelector('#navLogo')?.setAttribute('src','/static/img/logo/logo-light.png');
      }
    }
  }
  window.addEventListener('scroll', onScroll, {passive:true});
  onScroll();
})();
