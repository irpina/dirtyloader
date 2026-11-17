/* SPDX-License-Identifier: GPL-2.0-or-later */
/* What gcc may call on its own in a freestanding mod (struct copies, zeroing, comparisons). Linked into every
 * .m8x after the mod's sources; --gc-sections drops what a mod does not use. Plain byte loops: small, and fast
 * enough from ITCM. A mod may define its own instead (its definition wins: this is linked as a library). */
#include <stddef.h>

void *memcpy(void *d, const void *s, size_t n)
{
    unsigned char *o = d;
    const unsigned char *i = s;
    while (n--) *o++ = *i++;
    return d;
}

void *memmove(void *d, const void *s, size_t n)
{
    unsigned char *o = d;
    const unsigned char *i = s;
    if (o < i) while (n--) *o++ = *i++;
    else { o += n; i += n; while (n--) *--o = *--i; }
    return d;
}

void *memset(void *d, int c, size_t n)
{
    unsigned char *o = d;
    while (n--) *o++ = (unsigned char)c;
    return d;
}

int memcmp(const void *a, const void *b, size_t n)
{
    const unsigned char *x = a, *y = b;
    for (; n; n--, x++, y++) if (*x != *y) return *x - *y;
    return 0;
}

size_t strlen(const char *s)
{
    const char *p = s;
    while (*p) p++;
    return (size_t)(p - s);
}
