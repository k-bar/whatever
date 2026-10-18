/**
 * What the presentation demo (demo/index.js) needs from the running app, kept fresh by App on every render:
 * the map, the interface settings and language (to put them back afterwards) and a way to close "+ Create event".
 * Its own tiny module so the demo itself can load only when Home is double-clicked.
 */
export const demoHost = { current: null }
