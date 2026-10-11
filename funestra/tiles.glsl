//!PARAM tiles
//!TYPE int
//!MINIMUM 1
1

//!HOOK MAIN
//!BIND HOOKED
//!WIDTH HOOKED.w tiles *
//!HEIGHT HOOKED.h
//!DESC tiles
vec4 hook() {
    vec2 pos = HOOKED_pos;
    pos.x = fract(pos.x * float(tiles));
    return HOOKED_tex(pos);
}
