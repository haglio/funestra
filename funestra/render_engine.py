"""Offscreen twin of MpvEngine: the same engine rendered into a caller's FBO.

``MpvEngine`` paints into a window mpv owns (``wid``); some hosts have no
window per video — a VR compositor draws several Funestras into one scene — so
this variant drives libmpv's render API instead: mpv decodes exactly as
before, but each frame is drawn on demand into whatever OpenGL framebuffer the
caller passes, for the host to composite wherever it likes.  libmpv renders
the OSD into that frame too, so overlays pushed through ``overlay_add`` (the
Funestras' HUDs) carry over unchanged.

The caller owns the GL context and must have it current on the calling thread
for construction, for every ``render`` and for ``close`` (which frees the
render context); *get_proc_address* resolves GL entry points by name (e.g.
wrapping ``glfw.get_proc_address``), because libmpv binds its own GL functions
through it.

The control surface is ``_MpvControl`` — MpvEngine's own — so a Funestra
drives either engine without knowing which rendering path is backing it.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .drawn_file import DrawnFile
from .mpv_engine import _import_mpv, _MpvControl, _shared_options
from .mpv_gate import mpv_call

__all__ = [
    "MpvRenderEngine",
]

_FRAME_PRESENT = 1
_FRAME_REDRAW = 2


class MpvRenderEngine(_MpvControl):
    def __init__(
        self,
        get_proc_address: Callable[[str], int | None],
        *,
        muted: bool = False,
        loop_file: bool = True,
        prefetch: bool = False,
        audio: bool = True,
    ) -> None:
        super().__init__(looping=loop_file)
        mpv = _import_mpv()
        options = _shared_options(muted=muted, loop_file=loop_file, prefetch=prefetch)
        # No window to own: libmpv renders on demand into the caller's FBO.
        options["vo"] = "libmpv"
        if not audio:
            # No audio track at all — stronger than muted.  mpv's default
            # clock follows audio, so a muted engine still stalls its VIDEO
            # the moment its output device stops draining (a VR headset's
            # sink parks whenever the headset isn't worn, and every engine
            # in the process opens some device).  A host whose engine is
            # silent by design opts out of audio selection entirely, and the
            # clock runs on video timing, immune to any device's state.
            options["aid"] = "no"
        self._adopt(mpv.MPV(**options))
        self._drawn_file = DrawnFile()
        self._file_heard = {
            mpv.MpvEventID.FILE_LOADED: self._drawn_file.opened,
            mpv.MpvEventID.PLAYBACK_RESTART: self._drawn_file.started,
        }
        self._mpv.register_event_callback(self._note_event)

        def _resolve(_ctx, name: bytes):
            return get_proc_address(name.decode("utf-8"))

        # Held on self: libmpv calls this for the context's whole lifetime, and
        # a garbage-collected ctypes callback is a hard crash, not an error.
        self._get_proc_address = mpv.MpvGlGetProcAddressFn(_resolve)
        self._render_context = mpv.MpvRenderContext(
            self._mpv,
            "opengl",
            opengl_init_params={"get_proc_address": self._get_proc_address},
        )

        def next_frame_flags() -> int:
            # python-mpv's own next_frame_info lookup builds its param without a value and raises.
            info = mpv.MpvRenderParam("next_frame_info", {"flags": 0, "target_time": 0})
            mpv._mpv_render_context_get_info(self._render_context.handle, info)
            return info.value.flags

        self._next_frame_flags = next_frame_flags

    def _note_event(self, event) -> None:
        heard = self._file_heard.get(event.event_id.value)
        if heard is not None:
            heard(self._path)

    def load(self, path: Path) -> None:
        self._drawn_file.asked_for(str(path))
        super().load(path)

    @property
    @mpv_call(False)
    def has_picture_to_draw(self) -> bool:
        if self._render_context.update():
            self._drawn_file.announced()
        return self._drawn_file.owed

    @mpv_call()
    def render(self, fbo: int, width: int, height: int, *, flip_y: bool = False) -> str | None:
        """Draw the current frame (video + OSD overlays) into *fbo* at width x height,
        and say which file the picture shows: None while it is not one to show.

        mpv scales to the target preserving aspect, so a target sized to the
        video's own aspect (see :attr:`video_dims`) fills edge to edge.

        Returns immediately: without block_for_target_time=False, libmpv holds
        the call until the frame's own display time — pacing the caller at the
        video's frame rate.  A host compositing several Funestras on its own
        clock (a 90Hz VR frame loop over 30fps videos) must never inherit that
        pacing; presentation timing is the host's, and mpv just supplies its
        latest frame.
        """
        flags = self._next_frame_flags()
        self._render_context.render(
            flip_y=flip_y,
            block_for_target_time=False,
            opengl_fbo={"fbo": int(fbo), "w": int(width), "h": int(height)},
        )
        return self._drawn_file.drawn(
            new_frame=bool(flags & _FRAME_PRESENT) and not flags & _FRAME_REDRAW)

    def _release(self) -> None:
        """The render context first, then the core it was created against.

        That order is libmpv's: a render context outstanding when the core is
        destroyed is undefined behavior.  Both frees reach here only once, and
        only once :meth:`close` has established that no thread is inside a
        ``render``, an ``update`` or a property read — python-mpv's
        ``MpvRenderContext.free`` is a bare ``mpv_render_context_free`` with no
        guard of its own, and a second one would free a freed context.
        """
        try:
            self._render_context.free()
        except Exception:
            pass
        super()._release()
