const form = document.querySelector('#controls');
const output = document.querySelector('#result');
const defaults = {a: 0, b: -1, c: 1, d: 0, x: 2, y: 1};
let api = null;

function values() {
  return Object.fromEntries(Object.keys(defaults).map(key => [key, Number(form.elements[key].value) || 0]));
}

function update() {
  const {a, b, c, d, x, y} = values();
  const rx = a * x + b * y;
  const ry = c * x + d * y;
  output.textContent = `A = [[${a}, ${b}], [${c}, ${d}]]\nv = (${x}, ${y})\nA · v = (${rx}, ${ry})`;
  if (!api) return;
  api.evalCommand(`A = {{${a}, ${b}}, {${c}, ${d}}}`);
  api.evalCommand(`v = Vector((0, 0), (${x}, ${y}))`);
  api.evalCommand(`Av = Vector((0, 0), (${rx}, ${ry}))`);
  api.setColor('v', 221, 170, 0);
  api.setColor('Av', 31, 105, 177);
  api.setLabelVisible('v', true);
  api.setLabelVisible('Av', true);
  api.setCaption('v', 'v (inicial)');
  api.setCaption('Av', 'A·v (resultante)');
  api.setLabelStyle('v', 3);
  api.setLabelStyle('Av', 3);
}

for (const input of form.querySelectorAll('input')) input.addEventListener('input', update);
document.querySelector('#restore').addEventListener('click', () => {
  for (const [key, value] of Object.entries(defaults)) form.elements[key].value = value;
  update();
});

const applet = new GGBApplet({
  appName: 'graphing',
  width: 760,
  height: 600,
  showToolBar: false,
  showAlgebraInput: false,
  showMenuBar: false,
  enableLabelDrags: false,
  appletOnLoad(loadedApi) {
    api = loadedApi;
    api.setCoordSystem(-5, 5, -4, 4);
    update();
  },
}, true);
applet.inject('geogebra');
update();
