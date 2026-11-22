/* Shared behaviour for every HeatScape page:
 *  - the season (summer / winter) is stored in localStorage and applied to <body data-season>;
 *    pages react through the "seasonchange" event (detail = 'summer' | 'winter');
 *  - the header city menu (#citySelect) lists every city in GDP order and opens its map.
 */
(function () {
  const KEY = 'heatscape-season';
  const read = () => { try { return localStorage.getItem(KEY); } catch (e) { return null; } };
  const write = value => { try { localStorage.setItem(KEY, value); } catch (e) { /* storage blocked */ } };
  const month = new Date().getMonth() + 1;
  const param = new URLSearchParams(location.search).get('season');
  let season = [param, read()].find(v => v === 'summer' || v === 'winter') || (month >= 5 && month <= 9 ? 'summer' : 'winter');

  function apply(next, notify) {
    season = next;
    document.body.dataset.season = next;
    for (const id of ['summerMode', 'winterMode']) {
      const button = document.getElementById(id);
      if (button) button.setAttribute('aria-pressed', String(id === next + 'Mode'));
    }
    write(next);
    if (notify) document.dispatchEvent(new CustomEvent('seasonchange', {detail: next}));
  }

  window.HeatSeason = {
    get: () => season,
    set: next => { if (next !== season) apply(next, true); },
  };

  function init() {
    apply(season, false);
    for (const [id, value] of [['summerMode', 'summer'], ['winterMode', 'winter']]) {
      const button = document.getElementById(id);
      if (button) button.addEventListener('click', () => window.HeatSeason.set(value));
    }
    // Keep several open tabs in step.
    window.addEventListener('storage', event => {
      if (event.key === KEY && (event.newValue === 'summer' || event.newValue === 'winter') && event.newValue !== season) apply(event.newValue, true);
    });
    const select = document.getElementById('citySelect');
    if (select) {
      const current = new URLSearchParams(location.search).get('city') || document.body.dataset.city || '';
      fetch('cities/views.json').then(r => r.json()).then(views => {
        select.innerHTML = '';
        if (!current) select.append(new Option('Choose a city', '', true, true));
        for (const [slug, city] of Object.entries(views)) select.append(new Option(city.name, slug));
        if (current) select.value = current;
        select.addEventListener('change', () => {
          const slug = select.value;
          if (!slug) return;
          location.href = (views[slug].shade ? 'shade.html' : 'cities.html') + '?city=' + slug;
        });
      }).catch(() => {});
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
