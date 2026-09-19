"""Distinctive synthetic PNG generated with stdlib; no financial market content."""

import struct
import zlib


def capability_png() -> bytes:
    width, height = 320, 220
    pixels = bytearray([255] * (width * height * 3))

    def pixel(x, y, color):
        offset = (y * width + x) * 3
        pixels[offset:offset + 3] = bytes(color)

    for y in range(30, 145):
        for x in range(25, 145):
            if (x - 85) ** 2 + (y - 85) ** 2 < 50 ** 2:
                pixel(x, y, (140, 25, 200))
        for x in range(175, 300):
            if abs(x - 237) < (y - 30) / 2:
                pixel(x, y, (255, 130, 0))
    glyphs = ('10001 10001 10001 11111 10001 10001 10001', '11111 00001 00010 00100 01000 01000 01000')
    for index, glyph in enumerate(glyphs):
        for row, bits in enumerate(glyph.split()):
            for col, bit in enumerate(bits):
                if bit == '1':
                    for dy in range(7):
                        for dx in range(7):
                            pixel(110 + index * 49 + col * 7 + dx, 160 + row * 7 + dy, (0, 0, 0))

    def chunk(name, content):
        return struct.pack('>I', len(content)) + name + content + struct.pack('>I', zlib.crc32(name + content))

    rows = b''.join(b'\0' + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')
