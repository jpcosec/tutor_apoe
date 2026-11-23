# Instalar Tutor APOE

Funciona en macOS y Linux. En Windows, dentro de WSL.

## 1. Lo que hace falta antes

- `git` y `curl`.
- Python 3.12 o más nuevo (`python3 --version`).
- Conexión a internet durante la instalación.

## 2. Instalar

Desde la carpeta del repositorio:

```bash
./install.sh
```

Tarda entre 5 y 10 minutos. Deja todo dentro de esta carpeta: el entorno de Python en
`.venv/` y las dependencias sldb y pron en `third_party/`. No pide claves ni toca nada
fuera del repositorio, y se puede volver a ejecutar las veces que haga falta.

Al final construye la base de conocimiento, la valida y hace una pregunta de prueba. Si
termina con `Instalación lista.`, funciona.

Para comprobar más adelante una instalación que ya existe: `./install.sh --check`.

## 3. Usarlo

```bash
.venv/bin/tutor web --kb kbs/apos --model test --port 8300
```

Y abrir <http://127.0.0.1:8300> en el navegador. Las pestañas son Conversación, Paquetes,
Grafo APOS, Scratch y Configuración (la wiki donde se cambia cómo responde el tutor).

Con Codex u otro agente: ábrelo en esta carpeta y pide lo que necesites con tus palabras
("abre el visor", "qué dice la base sobre encapsulación", "carga este PDF", "guarda los
cambios").

## 4. Respuestas reales del tutor (claves)

`--model test` no usa internet ni claves: sirve para comprobar que todo anda, pero no
redacta respuestas. Para respuestas reales hace falta la clave de un proveedor en el
entorno, sin escribirla en ningún archivo del repositorio:

```bash
export DEEPSEEK_API_KEY=...        # el modelo por defecto
.venv/bin/tutor web --kb kbs/apos --port 8300
```

Los otros proveedores y variables están en `.env.example`.

## Si algo falla

| Mensaje | Qué hacer |
|---|---|
| `falta git` o `falta curl` | Instálalos con el gestor de paquetes del sistema y vuelve a ejecutar `./install.sh` |
| `hace falta Python 3.12 o más nuevo` | Instálalo desde <https://www.python.org/downloads/> |
| `no se pudo crear .venv` | En Debian o Ubuntu: `sudo apt install python3-venv` |
| `no se pudo descargar 'repo'` o falla la descarga de sldb y pron | Revisa la conexión y vuelve a ejecutar; si sigue, pide ayuda a JP |
| `KB inválida` con `hash_d no calza` | `.venv/bin/tutor kb build` reconstruye la base derivada |
