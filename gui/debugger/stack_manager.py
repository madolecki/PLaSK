import sys

class StackManager:

    def __init__(self, dbg_path):
        self.stack = []
        self.dbg_path = dbg_path

    def _frame_id(self, frame):
        return id(frame)

    def _frame_info(self, frame):
        return {
            "id": self._frame_id(frame),
            "function": frame.f_code.co_name,
            "file": frame.f_code.co_filename,
            "line": frame.f_lineno,
            "locals": frame.f_locals,
        }

    def on_call(self, frame):
        entry = self._frame_info(frame)
        self.stack.append(entry)

    def on_return(self, frame):
        fid = self._frame_id(frame)

        while self.stack:
            top = self.stack[-1]
            self.stack.pop()
            if top["id"] == fid:
                break

    def on_line(self, frame):
        if not self.stack:
            return
        fid = self._frame_id(frame)
        top = self.stack[-1]
        if top["id"] == fid:
            top["line"] = frame.f_lineno

    def rebuild_from_frame(self, frame):
        new_stack = []
        f = frame
        while f is not None:
            if self._frame_info(f)['function'] != '<module>':
                new_stack.append(self._frame_info(f))
            f = f.f_back
            if self._frame_info(f)['file'] == self.dbg_path:
                break

        new_stack.pop(-1)
        new_stack.reverse()
        self.stack = new_stack

    def get_stack(self):
        return list(self.stack)
