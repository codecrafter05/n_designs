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
