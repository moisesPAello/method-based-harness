# method-based-harness

> Instala un arnés de código multi-agente, guiado por metodología, en cualquier repositorio.

*[English](README.md) · Español*

`method-based-harness` es una CLI pequeña que instala un **arnés multi-agente guiado por
metodología** dentro de un repo. El repo mismo se convierte en el runtime: tu host de
agentes (hoy Claude Code) lee las definiciones de roles, los hooks y el estado en disco que
se generan, y conduce el trabajo a través de las compuertas (*gates*) de la metodología
elegida. Sin API keys de modelos y sin servicio en ejecución — se apoya en la suscripción
de agente que ya tienes.

## Por qué

Dos herramientas existentes lo enmarcan:

- **GitHub Spec Kit** — la misma forma "instalar y listo", pero la metodología (desarrollo
  guiado por especificación) está fija en el código.
- **BMAD-METHOD** — una gramática rica de "metodología como código", pero la metodología
  está fusionada con su elenco de agentes.

Esta herramienta apunta al hueco entre ambas: **la ligereza de Spec Kit con la
intercambiabilidad de BMAD** — cambia la metodología, conserva el elenco.

## Cómo funciona — cuatro capas ortogonales

```
biblioteca de roles  ×  metodología   ×  perfil del proyecto  ×  host
(competencia)           (coreografía)    (de ESTE repo:          (destino de render:
roles agnósticos        estados +        comando de verify,      Claude Code ->
lente + postura         gates + relevos) constitución,           .claude/agents,
                                         gates por tipo)         settings.json)
```

`harness init` enlaza las cuatro y las **compila** a los archivos nativos del host. Como
metodología y host son independientes, añadir un host es un único renderizador que sirve a
todas las metodologías, y añadir una metodología es una única declaración que corre en todos
los hosts.

Dos ideas lo hacen funcionar:

- **Una metodología es estructura, no prosa.** Los gates son condiciones duras y
  verificables sobre las transiciones de estado — no texto sugerente que el modelo pueda
  ignorar. No le enseñas al modelo *sobre* un método; codificas el método *entre* sus turnos.
- **Los agentes se pasan el trabajo por disco.** Cada rol lee archivos de entrada, escribe
  su producto en un archivo y devuelve una sola línea de referencia — duradero, versionado
  y reanudable si un agente se atasca.

## Instalación

Aún no está en PyPI. Instala desde Git con [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/moisesPAello/method-based-harness
```

## Inicio rápido

```bash
cd tu-repo

# 1. Describe tu repo al arnés en .harness/profile.yaml:
#    el comando de verify, las reglas siempre-activas de "constitución" y los gates por tipo.
#    Parte del ejemplo incluido: harness/library/examples/sella-cruce/profile.yaml
$EDITOR .harness/profile.yaml

# 2. Compila el arnés dentro del repo.
harness init --methodology sdd --host claude

# 3. Abre tu host de agentes (Claude Code) y pídele que implemente la siguiente feature.
#    Actúa como orquestador y conduce los gates de la metodología.
```

## Comandos

| Comando | Qué hace |
|---|---|
| `harness init` | compila la biblioteca + tu perfil dentro del repo (`--methodology`, `--host`, `--from-profile`, `--dry-run`, `--force`) |
| `harness upgrade` | re-renderiza los archivos gestionados desde la biblioteca (actualizada); preserva el estado local, elimina huérfanos y rechaza archivos editados a mano sin `--force` |
| `harness list` | muestra metodologías, hosts y roles disponibles |
| `harness selftest` | renderiza un fixture incluido y verifica la salida (sin red) |

### Mantenerlo al día — dos capas

- **La herramienta en sí** (y su biblioteca incluida) → tu gestor de paquetes:
  `uv tool upgrade method-based-harness`.
- **Un repo ya instalado** → esta CLI, por repo: `harness upgrade`.

`harness upgrade` re-renderiza desde la biblioteca dentro de la herramienta *instalada*, así
que actualiza primero la herramienta y luego haz `upgrade` en cada repo. Los archivos
gestionados son derivados — personaliza la **fuente** (tu perfil o la biblioteca), no la
salida generada.

## Estado

Temprano (`0.0.1`). La metodología **SDD** sobre el host **Claude Code** está validada de
extremo a extremo: un prototipo escrito a mano condujo una feature real por
`pending → spec_ready → ⏸ humano → in_progress → in_review` sobre una suscripción Claude Pro,
en un repositorio real (una herramienta Python de procesamiento de estados de cuenta
bancarios, incluida como ejemplo), con los gates sosteniéndose bajo revisión independiente.
Esa salida probada es lo que la CLI ahora genera. Una metodología **TDD** está esbozada para
demostrar la costura de intercambiabilidad.

## Estructura

| Ruta | Qué |
|---|---|
| `harness/` | la CLI, el compilador y el renderizador de Claude |
| `harness/library/roles/` | lentes de rol agnósticas (competencia + postura) |
| `harness/library/methodologies/` | declaraciones de metodología (`sdd/`, `tdd/`) |
| `harness/library/examples/` | un perfil de proyecto real (también el fixture de selftest) |
| `docs/` | arquitectura, autoría de metodologías, esquema de roles, bitácora de hallazgos |

## Licencia

MIT
