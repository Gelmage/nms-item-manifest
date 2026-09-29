"""
LZ4 block decompression, in plain Python.

No Man's Sky saves are a chain of LZ4-compressed blocks. Decoding them normally
means installing python3-lz4, which is a real obstacle for someone who just wants
to run a small tool. The block format is simple enough to implement directly, so
this file exists to keep the project's install instructions at "you need Python".

Decompression only. This never produces a .hg file, only reads one.
"""


def decompress(src, uncompressed_size):
    """Decode one LZ4 block. `src` is bytes, the return value is a bytearray."""
    dst = bytearray(uncompressed_size)
    s, d, end = 0, 0, len(src)

    while s < end:
        token = src[s]
        s += 1

        # High nibble: how many bytes to copy verbatim. 15 means "keep reading".
        literals = token >> 4
        if literals == 15:
            while True:
                b = src[s]
                s += 1
                literals += b
                if b != 255:
                    break

        dst[d:d + literals] = src[s:s + literals]
        s += literals
        d += literals
        if s >= end:
            break

        # Then a back-reference: how far behind to look, and how much to repeat.
        offset = src[s] | (src[s + 1] << 8)
        s += 2
        if offset == 0:
            raise ValueError("corrupt LZ4 block: zero back-reference offset")

        length = token & 15
        if length == 15:
            while True:
                b = src[s]
                s += 1
                length += b
                if b != 255:
                    break
        length += 4  # the minimum match length is 4

        # Ranges may overlap (that is how LZ4 encodes runs), so copy byte by byte
        # rather than slicing -- a slice would read the pre-overlap bytes.
        m = d - offset
        if m < 0:
            raise ValueError("corrupt LZ4 block: back-reference before start of output")
        for _ in range(length):
            dst[d] = dst[m]
            d += 1
            m += 1

    return dst[:d]
