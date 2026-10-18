import errno
import struct
import zlib
from pathlib import Path


PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
PNG_PUBLIC_CHUNKS = frozenset((b'IHDR', b'PLTE', b'IDAT', b'IEND', b'sRGB', b'gAMA', b'cHRM', b'tRNS'))


def error_summary(error):
    kinds = (FileNotFoundError, FileExistsError, PermissionError, OSError, ValueError,
             TypeError, KeyError, IndexError, MemoryError, ImportError, RuntimeError)
    kind = next((item.__name__ for item in kinds if isinstance(error, item)), 'Exception')
    result = {'type': kind, 'message': 'Operation failed; inspect the preceding stage and validation reports. Raw host diagnostics are private.'}
    if isinstance(error, OSError) and type(error.errno) is int and error.errno in errno.errorcode:
        result['errno'] = error.errno
    return result


def create_output_directory(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / '.gitignore').write_text('*\n', encoding='utf-8')
    return directory


def ignore_output_file(filename):
    filename = Path(filename)
    if filename.name == '.gitignore' or any(c in filename.name for c in '\r\n'):
        raise ValueError('Choose a regular output filename')
    filename.parent.mkdir(parents=True, exist_ok=True)
    rule = '/' + ''.join('\\' + c if c in '\\*?[]!# ' else c for c in filename.name)
    ignore = filename.parent / '.gitignore'
    content = ignore.read_text(encoding='utf-8') if ignore.exists() else ''
    lines = content.splitlines()
    if content.strip() != '*' and (not lines or lines[-1] != rule):
        with ignore.open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(('\n' if content and not content.endswith('\n') else '') + rule + '\n')


def png_chunks(data):
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError('Invalid PNG signature')
    offset, first = len(PNG_SIGNATURE), True
    while offset + 12 <= len(data):
        size = struct.unpack_from('>I', data, offset)[0]
        end = offset + size + 12
        if end > len(data):
            raise ValueError('Truncated PNG chunk')
        kind = data[offset + 4:offset + 8]
        if first and kind != b'IHDR':
            raise ValueError('Missing PNG header')
        first = False
        crc = struct.unpack_from('>I', data, end - 4)[0]
        if zlib.crc32(data[offset + 4:end - 4]) & 0xffffffff != crc:
            raise ValueError('Invalid PNG checksum')
        yield kind, data[offset:end]
        offset = end
        if kind == b'IEND':
            if size or offset != len(data):
                raise ValueError('Unexpected data after PNG end')
            return
    raise ValueError('Missing PNG end')


def clean_png(filename):
    filename = Path(filename)
    data = filename.read_bytes()
    chunks = list(png_chunks(data))
    filename.write_bytes(PNG_SIGNATURE + b''.join(chunk for kind, chunk in chunks if kind in PNG_PUBLIC_CHUNKS))
