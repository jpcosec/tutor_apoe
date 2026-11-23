// Regenera mock-data.json evaluando las constantes del bundle de la maqueta.
// Uso: node extract-mock.cjs "<maqueta extraida: app.js>"   (por defecto /tmp/mock2/app.js)
const fs = require("fs");
const s = fs.readFileSync(process.argv[2] || "/tmp/mock2/app.js", "utf8");
const a = s.indexOf("var Wt={regla:"), b = s.indexOf(";var mi=Pe(At())", a);
const o = eval(s.slice(a, b) + ";({Wt,Hn,Xy,pi,op,Sn,sp,Ky,hi,nu})");
const c = s.indexOf("sM={prompt:"), d = s.indexOf(",lM=", c);
const desc = eval("(" + s.slice(c + 3, d) + ")");
fs.writeFileSync(__dirname + "/mock-data.json", JSON.stringify({
  tipos: o.Wt, fuentes: o.Hn, fuenteCorta: o.Xy, fuenteDescripcion: desc, parrafos: o.pi, atomos: o.op,
  bases: o.Sn.map(x => ({ id: x.id, groups: x.groups.map(g => g.id) })), tiposRelacion: o.sp,
  relaciones: o.Ky, informe: o.hi, frases: o.nu }, null, 1));
