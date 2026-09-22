# Raspberry Pi 4 Autonomous Agent Plan (`RPI_PLAN.md`)

This file is the top-level pointer and executive summary for autonomous tasks run from the dedicated Raspberry Pi 4 host (`msa-linuxRPi4`).

The full, step-by-step instruction set for the RPi agent is maintained at:  
👉 **[`docs/rpi_agent_instructions.md`](docs/rpi_agent_instructions.md)**

---

## Quick Reference for the RPi Agent

| Resource | Value / Path |
| :--- | :--- |
| **Host** | `msa-linuxRPi4` (`192.168.1.150`, Linux aarch64) |
| **Working Repository** | `/home/msa/bootlab-esp-latest` |
| **Active VirtualEnv** | `/home/msa/bootlab-esp-latest/.venv` |
| **Target Board (IDF)** | `192.168.1.152` (HTTPS port 443) |
| **Target Board (Zephyr)** | `192.168.1.153` (UDP SMP port 1337) |
| **Detailed Agent Guide** | [`docs/rpi_agent_instructions.md`](docs/rpi_agent_instructions.md) |

---

## Two-Phase Roadmap

### Phase 1: Immediate Network Testing & OTA Validation
1. **Network Health Baseline:** Ping both boards and query baseline JSON `/version` over HTTPS.
2. **ESP-IDF WiFi OTA Acceptance ([BL-056a](tickets/tickets.json)):**
   - Stage signed firmware binaries (`v1.bin`, `v2.bin`).
   - Trigger WiFi OTA from RPi via `labflash update idf --transport wifi --no-labid`.
   - Verify slot switch (`v1` $\to$ `v2` $\to$ `v1`), confirm image state, and generate evidence in `scripts/evidence/bl056a_rpi4_acceptance.md`.
3. **Zephyr UDP SMP Testing:**
   - Query SMP status with `scripts/test_udp_smp.py`.
   - Perform UDP OTA with `scripts/zephyr_udp_ota.py`.
4. **CI Runner Verification ([BL-056](tickets/tickets.json)):** Verify self-hosted runner process health.

### Phase 2: Modular Development & Local Compilation
1. **Adding Components & Modules:** Standards for adding C modules in `common/`, `esp_idf/components/`, and `esp_zephyr/app/src/`.
2. **Safe Compilation:** Leverage `~/.espressif` and `~/zephyr-ws` using parallel throttling (`-j2`) to protect the RPi power rail from brownouts.
3. **Local Staging:** Packaging and signing development images for network OTA deployment.
