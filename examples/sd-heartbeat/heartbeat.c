/* SPDX-License-Identifier: GPL-2.0-or-later */
/* sd-heartbeat: the smallest loadable mod. core 0.3 loads it from the SD card; it double-blinks the Teensy's
 * LED (pin 13), three short flashes if a song tempo change is seen. Proves loading, relocation, .bss and two
 * events on a bare Teensy 4.1 running M8 Headless.
 *
 *     python -m dirtyloader.core.build_headless <stock.hex> <out>    (builds this as <out>/sd/...) */
#include "dl/mod.h"
#include "m8-headless/fw.h"

#define GPIO7_GDIR   (*(volatile uint32_t *)0x42004004u)
#define GPIO7_SET    (*(volatile uint32_t *)0x42004084u)
#define GPIO7_CLEAR  (*(volatile uint32_t *)0x42004088u)
#define LED          (1u << 3)

static uint32_t tempo_seen;           /* .bss: zeroed by the loader */
static const uint8_t pattern[8] = { 1, 0, 1, 0, 0, 0, 0, 0 };

static void on_boot(void)
{
    *(volatile uint32_t *)0x401F8148u = 5;          /* pad GPIO_B0_03 -> GPIO */
    *(volatile uint32_t *)0x401F8338u = 0x38;
    *(volatile uint32_t *)0x400AC06Cu |= LED;       /* GPR27: route it to GPIO7 */
    GPIO7_GDIR |= LED;
}

static void on_tick(void)
{
    uint32_t phase = (fw_millis >> 7) & 7;
    int on = tempo_seen ? (phase < 6 && !(phase & 1)) : pattern[phase];
    if (on) GPIO7_SET = LED; else GPIO7_CLEAR = LED;
}

static int on_tempo(float bpm)
{
    tempo_seen = 1;
    return 0;                                       /* never take it: the tempo still changes */
}

DL_MOD("sd-heartbeat", "0.1.0", "SD heartbeat",
       DL_ON(EV_BOOT, 50, on_boot),
       DL_ON(EV_TICK, 50, on_tick),
       DL_ON(EV_TEMPO, 50, on_tempo));
