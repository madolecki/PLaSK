import dis
import types

# find all lines in the file that contain code
def get_executable_lines(code_obj):
    executable = set()

    def _extract(co):
        for _, line in dis.findlinestarts(co):
            if line is not None:
                executable.add(line)
        for const in co.co_consts:
            if isinstance(const, types.CodeType):
                _extract(const)

    _extract(code_obj)
    return executable

# resolve empty line to the nearest one containing code
def resolve_line(code_obj, requested_line):
    valid_lines = sorted(get_executable_lines(code_obj))
    for line in valid_lines:
        if line >= requested_line:
            return line
    return requested_line
