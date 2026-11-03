// Runs before the page paints, so a saved theme never flashes the wrong colours.
(function () {
  try {
    const saved = localStorage.getItem("kairos-theme");
    if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
    if (localStorage.getItem("kairos-rail") === "collapsed") document.documentElement.dataset.rail = "collapsed";
  } catch (e) { /* no storage: follow the system */ }
})();
