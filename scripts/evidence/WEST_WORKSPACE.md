# BL-002 — Zephyr workspace (west update) evidence

Date: 2026-09-16

## west update approach (honest note)
The owner requested `west update --name-allowlist <proj,...>`, but West v1.5.0
does NOT support `--name-allowlist`:

  $ west update --name-allowlist zephyr,hal_espressif,mcuboot,zcbor,mbedtls,tinycrypt,segger
  west update: error: unexpected arguments: ['--name-allowlist']

Positional-project updates also fail because the manifest uses `import: true`
(imported projects can't be targeted by name):

  FATAL ERROR: one or more projects are unknown or defined via imports;
  please run plain "west update".

Per the tool's own guidance, I fell back to plain `west update` (fetches all
manifest projects). This is a deliberate deviation from the allowlist request
because the requirement is not implementable with West v1.5.0; the full
workspace was instead used. If a strict allowlist is required, the fix is to
set the manifest's `group-filter` (disable groups) rather than rely on a
nonexistent flag.

## Resolved workspace
  west topdir            : /home/msa/bootlab-esp
  zephyr  -> v4.4.2      (revision pinned in west.yml, verified git describe)
  mcuboot -> v2.4.0      (RESOLVED from Zephyr's west manifest via import;
                           recorded here as required after west update)
  hal_espressif          : present (modules/hal/espressif)

## check_env.sh checks this via
  west list zephyr mcuboot
  git -C <repo> describe --tags
