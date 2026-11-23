#!/usr/bin/env node
/**
 * Verificador estático del contrato de capas (`contracts/layers.json`).
 * Equivalente en frontend a `sldb/tools/check_layers.py`.
 *
 * Reglas verificadas:
 * 1. Ningún módulo importa de una capa de nivel superior (`level` mayor).
 * 2. `L0 (core)` no importa React ni librerías de UI (`forbiddenExternalPackages`).
 * 3. Las capas con `forbidDirectFetch: true` no llaman a `fetch(` directamente (todo pasa por `SldbClient`).
 * 4. Ningún archivo de producción contiene literales harcodeados del caso Levira (`forbiddenMockLiterals`).
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");
const srcDir = path.join(rootDir, "src");
const contractPath = path.join(rootDir, "contracts", "layers.json");

const contract = JSON.parse(fs.readFileSync(contractPath, "utf8"));
const PROD_EXTS = new Set([".ts", ".tsx"]);
const TEST_RE = /\.(test|spec)\.[jt]sx?$/;

function walkProdFiles(dir) {
  const results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "__fixtures__" || entry.name === "node_modules") continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkProdFiles(full));
    } else if (PROD_EXTS.has(path.extname(entry.name)) && !TEST_RE.test(entry.name) && entry.name !== "test-setup.ts") {
      results.push(full);
    }
  }
  return results;
}

function toPosix(p) {
  return p.split(path.sep).join("/");
}

function findLayer(relFromRoot) {
  for (const layer of contract.layers) {
    if (layer.files && layer.files.includes(relFromRoot)) return layer;
    if (layer.directories && layer.directories.some((d) => relFromRoot === d || relFromRoot.startsWith(`${d}/`))) {
      return layer;
    }
  }
  return null;
}

function parseImports(source) {
  const specs = [];
  const re = /(?:import|export)\s+(?:type\s+)?(?:[^'";]*?\s+from\s+)?['"]([^'"]+)['"]/g;
  let match;
  while ((match = re.exec(source)) !== null) {
    specs.push(match[1]);
  }
  return specs;
}

function resolveImportTarget(fromFile, spec) {
  if (!spec.startsWith(".")) return { kind: "external", pkg: spec };
  const resolvedAbs = path.resolve(path.dirname(fromFile), spec);
  const relFromRoot = toPosix(path.relative(rootDir, resolvedAbs));
  return { kind: "internal", rel: relFromRoot };
}

const files = walkProdFiles(srcDir);
const violations = [];

for (const file of files) {
  const rel = toPosix(path.relative(rootDir, file));
  const sourceLayer = findLayer(rel);
  if (!sourceLayer) {
    violations.push(`[UNCLASSIFIED] ${rel} no pertenece a ninguna capa declarada en contracts/layers.json`);
    continue;
  }

  const content = fs.readFileSync(file, "utf8");
  const imports = parseImports(content);

  for (const spec of imports) {
    if (spec.endsWith(".css")) continue;
    const target = resolveImportTarget(file, spec);

    if (target.kind === "external") {
      const forbidden = sourceLayer.forbiddenExternalPackages || [];
      if (forbidden.some((pkg) => target.pkg === pkg || target.pkg.startsWith(`${pkg}/`))) {
        violations.push(
          `[LAYER_PURITY] ${rel} (L${sourceLayer.level} ${sourceLayer.name}) importa paquete prohibido "${target.pkg}"`
        );
      }
    } else {
      const targetLayer = findLayer(target.rel);
      if (targetLayer && targetLayer.level > sourceLayer.level) {
        violations.push(
          `[UPWARD_IMPORT] ${rel} (L${sourceLayer.level} ${sourceLayer.name}) -> ${target.rel} (L${targetLayer.level} ${targetLayer.name})`
        );
      }
    }
  }

  if (sourceLayer.forbidDirectFetch) {
    // Ignorar comentarios al buscar llamadas directas a fetch(
    const stripped = content.replace(/\/\*[\s\S]*?\*\/|\/\/.*/g, "");
    if (/\bfetch\s*\(/.test(stripped)) {
      violations.push(
        `[DIRECT_FETCH] ${rel} (L${sourceLayer.level} ${sourceLayer.name}) invoca fetch() directamente; debe usar SldbClient`
      );
    }
  }

  for (const mockLiteral of contract.forbiddenMockLiterals || []) {
    if (content.includes(mockLiteral)) {
      violations.push(`[MOCK_LITERAL] ${rel} contiene literal harcodeado prohibido: "${mockLiteral}"`);
    }
  }
}

if (violations.length > 0) {
  console.error(`❌ Violaciones del contrato de capas (${violations.length}):`);
  for (const v of violations) {
    console.error(`  - ${v}`);
  }
  process.exit(1);
} else {
  console.log(`✓ Contrato de capas verificado (${files.length} módulos en L0..L3 sin violaciones ni mocks).`);
}
