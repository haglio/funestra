from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .drawn_file import DrawnFile
from .mpv_engine import _import_mpv, _MpvControl, _shared_options
from .mpv_gate import mpv_call

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
        options = _shared_options(muted=muted, loop_file=loop_file, prefetch=prefetch, audio=audio)
        # No window to own: libmpv renders on demand into the caller's FBO.
        options["vo"] = "libmpv"
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
    def has_frame_to_draw(self) -> bool:
        if self._render_context.update():
            self._drawn_file.announced()
        return self._drawn_file.owed

    @mpv_call()
    def render(self, fbo: int, width: int, height: int, *, flip_y: bool = False) -> str | None:
        # Without block_for_target_time=False libmpv holds the call until the frame's display time.
        self._viewport = (int(width), int(height))
        flags = self._next_frame_flags()
        self._render_context.render(
            flip_y=flip_y,
            block_for_target_time=False,
            opengl_fbo={"fbo": int(fbo), "w": int(width), "h": int(height)},
        )
        return self._drawn_file.drawn(
            new_frame=bool(flags & _FRAME_PRESENT) and not flags & _FRAME_REDRAW)

    def _release(self) -> None:
        # libmpv: a render context outstanding when the core is destroyed is undefined behavior.
        try:
            self._render_context.free()
        except Exception:
            pass
        super()._release()
