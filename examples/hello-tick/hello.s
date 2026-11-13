// hello-tick: a TICK handler, called by the Core's dispatcher every frame.
//
// Calling convention (docs/CORE.md): the event id is in r0 on entry, and a
// handler must preserve r4-r11 (AAPCS). This one does nothing and returns;
// replace the body with your mod's logic. Keep it small -- it lives in a code
// cave with only a few hundred bytes free.

bx lr
