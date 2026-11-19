/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Pixel UI for screens drawn with the firmware's fill-rect (Model:02, fw.h's fw_rect): a chunky 5 x 7 font, 10 x 10
 * pixel-art icons, outlined and filled boxes, header stripes. Everything goes through one rect function the caller
 * gives (pui_rect: x, y, w, h, colour), so a caller can count, clip or skip rects. Drawing is runs of rects: a
 * glyph row's lit run is one rect, an icon row's run of one colour is one rect. Include after the device's fw.h.
 * Header-only: each user gets its own copy. */
#ifndef DIRTYLOADER_DL_PIXUI_H
#define DIRTYLOADER_DL_PIXUI_H

#include <stdint.h>

typedef void (*pui_rect_fn)(int x, int y, int w, int h, uint16_t c);

/* colours (RGB565) of the dirtyloader screens */
#define PUI_BG      0x0000u
#define PUI_RGB(r, g, b) ((uint16_t)((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | ((b) >> 3)))
#define PUI_PURPLE  PUI_RGB(178, 82, 255)
#define PUI_DPURPLE PUI_RGB(84, 34, 140)
#define PUI_CREAM   PUI_RGB(246, 236, 206)
#define PUI_DIM     PUI_RGB(120, 110, 140)
#define PUI_MAGENTA PUI_RGB(255, 64, 196)
#define PUI_ORANGE  PUI_RGB(255, 150, 44)
#define PUI_YELLOW  PUI_RGB(255, 226, 92)
#define PUI_CYAN    PUI_RGB(44, 226, 255)
#define PUI_BLUE    PUI_RGB(72, 92, 255)

/* ---- the font: 5 x 7, a row a byte (bit 4 leftmost); lower case draws as upper; { } are filled triangles ---- */
__attribute__((unused)) static const char pui_chars[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.:/+-<>%!?()'_#,={}*";
__attribute__((unused)) static const uint8_t pui_glyphs[][7] = {
    {0x0E,0x11,0x11,0x1F,0x11,0x11,0x11}, {0x1E,0x11,0x11,0x1E,0x11,0x11,0x1E}, {0x0E,0x11,0x10,0x10,0x10,0x11,0x0E},
    {0x1E,0x11,0x11,0x11,0x11,0x11,0x1E}, {0x1F,0x10,0x10,0x1E,0x10,0x10,0x1F}, {0x1F,0x10,0x10,0x1E,0x10,0x10,0x10},
    {0x0E,0x11,0x10,0x17,0x11,0x11,0x0F}, {0x11,0x11,0x11,0x1F,0x11,0x11,0x11}, {0x0E,0x04,0x04,0x04,0x04,0x04,0x0E},
    {0x07,0x02,0x02,0x02,0x02,0x12,0x0C}, {0x11,0x12,0x14,0x18,0x14,0x12,0x11}, {0x10,0x10,0x10,0x10,0x10,0x10,0x1F},
    {0x11,0x1B,0x15,0x15,0x11,0x11,0x11}, {0x11,0x11,0x19,0x15,0x13,0x11,0x11}, {0x0E,0x11,0x11,0x11,0x11,0x11,0x0E},
    {0x1E,0x11,0x11,0x1E,0x10,0x10,0x10}, {0x0E,0x11,0x11,0x11,0x15,0x12,0x0D}, {0x1E,0x11,0x11,0x1E,0x14,0x12,0x11},
    {0x0F,0x10,0x10,0x0E,0x01,0x01,0x1E}, {0x1F,0x04,0x04,0x04,0x04,0x04,0x04}, {0x11,0x11,0x11,0x11,0x11,0x11,0x0E},
    {0x11,0x11,0x11,0x11,0x11,0x0A,0x04}, {0x11,0x11,0x11,0x15,0x15,0x15,0x0A}, {0x11,0x11,0x0A,0x04,0x0A,0x11,0x11},
    {0x11,0x11,0x11,0x0A,0x04,0x04,0x04}, {0x1F,0x01,0x02,0x04,0x08,0x10,0x1F},
    {0x0E,0x11,0x13,0x15,0x19,0x11,0x0E}, {0x04,0x0C,0x04,0x04,0x04,0x04,0x0E}, {0x0E,0x11,0x01,0x02,0x04,0x08,0x1F},
    {0x1F,0x02,0x04,0x02,0x01,0x11,0x0E}, {0x02,0x06,0x0A,0x12,0x1F,0x02,0x02}, {0x1F,0x10,0x1E,0x01,0x01,0x11,0x0E},
    {0x06,0x08,0x10,0x1E,0x11,0x11,0x0E}, {0x1F,0x01,0x02,0x04,0x08,0x08,0x08}, {0x0E,0x11,0x11,0x0E,0x11,0x11,0x0E},
    {0x0E,0x11,0x11,0x0F,0x01,0x02,0x0C},
    {0x00,0x00,0x00,0x00,0x00,0x0C,0x0C}, {0x00,0x0C,0x0C,0x00,0x0C,0x0C,0x00}, {0x01,0x01,0x02,0x04,0x08,0x10,0x10},
    {0x00,0x04,0x04,0x1F,0x04,0x04,0x00}, {0x00,0x00,0x00,0x1F,0x00,0x00,0x00}, {0x02,0x04,0x08,0x10,0x08,0x04,0x02},
    {0x08,0x04,0x02,0x01,0x02,0x04,0x08}, {0x18,0x19,0x02,0x04,0x08,0x13,0x03}, {0x04,0x04,0x04,0x04,0x04,0x00,0x04},
    {0x0E,0x11,0x01,0x02,0x04,0x00,0x04}, {0x02,0x04,0x08,0x08,0x08,0x04,0x02}, {0x08,0x04,0x02,0x02,0x02,0x04,0x08},
    {0x04,0x04,0x08,0x00,0x00,0x00,0x00}, {0x00,0x00,0x00,0x00,0x00,0x00,0x1F}, {0x0A,0x0A,0x1F,0x0A,0x1F,0x0A,0x0A},
    {0x00,0x00,0x00,0x00,0x0C,0x04,0x08}, {0x00,0x00,0x1F,0x00,0x1F,0x00,0x00},
    {0x02,0x06,0x0E,0x1E,0x0E,0x06,0x02}, {0x08,0x0C,0x0E,0x0F,0x0E,0x0C,0x08}, {0x00,0x15,0x0E,0x1F,0x0E,0x15,0x00},
};
static inline const uint8_t *pui_glyph(char ch)
{
    if (ch >= 'a' && ch <= 'z') ch = (char)(ch - 32);
    for (int i = 0; pui_chars[i]; i++)
        if (pui_chars[i] == ch) return pui_glyphs[i];
    return 0;                                       /* space and anything else: blank */
}
/* text at scale sc (a glyph is 5 sc wide, 7 sc tall, 6 sc apart); returns the x after it */
static inline int pui_text(pui_rect_fn rect, int x, int y, const char *s, int sc, uint16_t c)
{
    for (; *s; s++, x += 6 * sc) {
        const uint8_t *g = pui_glyph(*s);
        if (!g) continue;
        for (int r = 0; r < 7; r++)
            for (int b = 4; b >= 0; b--) {
                if (!(g[r] >> b & 1)) continue;
                int n = 1;
                while (b - n >= 0 && (g[r] >> (b - n) & 1)) n++;
                rect(x + (4 - b) * sc, y + r * sc, n * sc, sc, c);
                b -= n - 1;
            }
    }
    return x;
}
static inline int pui_len(const char *s) { int n = 0; while (s[n]) n++; return n; }
static inline int pui_width(const char *s, int sc) { int n = pui_len(s); return n ? n * 6 * sc - sc : 0; }

/* ---- boxes -------------------------------------------------------------------------------------------------- */
/* an outline t thick whose corners are cut by t (pixel-art rounding) */
static inline void pui_box(pui_rect_fn rect, int x, int y, int w, int h, int t, uint16_t c)
{
    rect(x + t, y, w - 2 * t, t, c);
    rect(x + t, y + h - t, w - 2 * t, t, c);
    rect(x, y + t, t, h - 2 * t, c);
    rect(x + w - t, y + t, t, h - 2 * t, c);
}
static inline void pui_fill(pui_rect_fn rect, int x, int y, int w, int h, uint16_t c)   /* corners cut by 2 */
{
    rect(x + 2, y, w - 4, h, c);
    rect(x, y + 2, 2, h - 4, c);
    rect(x + w - 2, y + 2, 2, h - 4, c);
}
/* corner brackets inside a box (selection, the pad's frame) */
static inline void pui_brackets(pui_rect_fn rect, int x, int y, int w, int h, int len, int t, uint16_t c)
{
    rect(x, y, len, t, c);                 rect(x, y, t, len, c);
    rect(x + w - len, y, len, t, c);       rect(x + w - t, y, t, len, c);
    rect(x, y + h - t, len, t, c);         rect(x, y + h - len, t, len, c);
    rect(x + w - len, y + h - t, len, t, c); rect(x + w - t, y + h - len, t, len, c);
}
/* diagonal stripes (\\\) from x, h tall, n of them, step 4 */
static inline void pui_stripes(pui_rect_fn rect, int x, int y, int h, int n, int gap, uint16_t c)
{
    for (int i = 0; i < n; i++)
        for (int r = 0; r < h; r += 4)
            rect(x + i * gap + (h - r) / 2, y + r, 6, 4, c);
}

/* ---- icons: 10 x 10, a palette letter a pixel ('.' none) ----------------------------------------------------- */
enum { PUI_I_SWIRL, PUI_I_WAVE, PUI_I_BARS, PUI_I_CUBE, PUI_I_DOTS, PUI_I_RINGS, PUI_I_STACK, PUI_I_HEART, PUI_I_GEAR,
       PUI_ICONS };
__attribute__((unused)) static const char *const pui_icons[PUI_ICONS][10] = {
    { "...kpppk..", ".kpmmmmpk.", "kpmo...mpk", "pmo.yyo.mp", "pm.yw.yomp", "pmoy.wy.mp", "pm.oyyo.mp",
      "kpmo...mpk", ".kpmmmmpk.", "..kpppk..." },
    { "..........", "..........", ".cc.......", "c..c......", "c...c....c", ".....c..c.", "......cc..",
      "..........", "..........", ".........." },
    { "........c.", "........c.", "......c.c.", "......c.c.", "....p.c.c.", "....p.c.c.", "..p.p.c.c.",
      "..p.p.c.c.", "p.p.p.c.c.", "p.p.p.c.c." },
    { "...cccccc.", "..c....cc.", ".c....c.c.", "cccccc..c.", "c....c..c.", "c....c..c.", "c....c.c..",
      "c....cc...", "cccccc....", ".........." },
    { "y...m....c", "...c..y...", ".m......m.", "....y.c...", "c..m....y.", "......m...", ".y..c....c",
      "....m..y..", "m.c.......", "....y..m.." },
    { "..wwwwww..", ".w......w.", "w..wwww..w", "w.w....w.w", "w.w.ww.w.w", "w.w.ww.w.w", "w.w....w.w",
      "w..wwww..w", ".w......w.", "..wwwwww.." },
    { "....wwwwww", "....w....w", "..wwwwww.w", "..w....w.w", "wwwwww.w.w", "w....w.www", "w....www..",
      "w....w....", "w....w....", "wwwwww...." },
    { "..........", ".mm...mm..", "mmmm.mmmm.", "mmmmmmmmm.", "mmmmmmmmm.", ".mmmmmmm..", "..mmmmm...",
      "...mmm....", "....m.....", ".........." },
    { "....ww....", ".w.wwww.w.", "..wwwwww..", ".www..www.", "wwww..wwww", "wwww..wwww", ".www..www.",
      "..wwwwww..", ".w.wwww.w.", "....ww...." },
};
static inline uint16_t pui_pal(char ch)
{
    switch (ch) {
    case 'k': return PUI_DPURPLE; case 'p': return PUI_PURPLE; case 'm': return PUI_MAGENTA;
    case 'o': return PUI_ORANGE;  case 'y': return PUI_YELLOW; case 'c': return PUI_CYAN;
    case 'b': return PUI_BLUE;    case 'w': return PUI_CREAM;  default: return PUI_DIM;
    }
}
static inline void pui_icon(pui_rect_fn rect, int x, int y, int icon, int sc)
{
    if ((unsigned)icon >= PUI_ICONS) return;
    for (int r = 0; r < 10; r++) {
        const char *row = pui_icons[icon][r];
        for (int c = 0; c < 10;) {
            char ch = row[c];
            int n = 1;
            while (c + n < 10 && row[c + n] == ch) n++;
            if (ch != '.') rect(x + c * sc, y + r * sc, n * sc, sc, pui_pal(ch));
            c += n;
        }
    }
}

#endif
