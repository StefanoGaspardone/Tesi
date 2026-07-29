#!/usr/bin/env python3
# brotli

import argparse
import ast
import ctypes
import time
import os
import logging
from ctypes import c_int, c_size_t, c_uint8, c_void_p, c_uint32, POINTER, byref
from datetime import datetime
from pathlib import Path

MAGIC = b"BRT1"
VERSION = 1

BROTLI_PARAM_QUALITY = 1
BROTLI_PARAM_LGWIN = 2
BROTLI_OPERATION_FINISH = 2
BROTLI_SHARED_DICTIONARY_RAW = 0

BROTLI_MAX_WINDOW_BITS = 24

# ---------------------------
# Logger
# ---------------------------
def setup_logger(input_filename):
    project_root = Path(__file__).resolve().parent.parent

    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents = True, exist_ok = True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_name = Path(__file__).stem
    base_input = Path(input_filename).stem

    log_filename = logs_dir / f"{script_name}_{timestamp}_{base_input}.log"

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    logging.basicConfig(
        level = logging.INFO,
        format = "%(message)s",
        handlers = [
            logging.FileHandler(log_filename, encoding = "utf-8"),
            logging.StreamHandler(),
        ],
    )

# ---------------------------
# Varint (LEB128 unsigned)
# ---------------------------
def uvarint_encode(x: int) -> bytes:
    out = bytearray()

    while True:
        b = x & 0x7F
        x >>= 7

        out.append(b | 0x80 if x else b)

        if not x:
            break

    return bytes(out)

def uvarint_decode(data: bytes, pos: int):
    x = 0
    shift = 0

    while True:
        b = data[pos]
        pos += 1
        x |= (b & 0x7F) << shift

        if not (b & 0x80):
            return x, pos

        shift += 7

def varint_size(x: int) -> int:
    return len(uvarint_encode(x))

# ---------------------------
# Ponte ctypes verso libbrotlienc / libbrotlidec
# ---------------------------
def _load_brotli_native():
    lib_enc = ctypes.CDLL("libbrotlienc.so.1")
    lib_dec = ctypes.CDLL("libbrotlidec.so.1")

    lib_enc.BrotliEncoderCreateInstance.restype = c_void_p
    lib_enc.BrotliEncoderCreateInstance.argtypes = [c_void_p, c_void_p, c_void_p]
    lib_enc.BrotliEncoderSetParameter.restype = c_int
    lib_enc.BrotliEncoderSetParameter.argtypes = [c_void_p, c_int, c_uint32]
    lib_enc.BrotliEncoderPrepareDictionary.restype = c_void_p
    lib_enc.BrotliEncoderPrepareDictionary.argtypes = [c_int, c_size_t, POINTER(c_uint8), c_int, c_void_p, c_void_p, c_void_p]
    lib_enc.BrotliEncoderAttachPreparedDictionary.restype = c_int
    lib_enc.BrotliEncoderAttachPreparedDictionary.argtypes = [c_void_p, c_void_p]
    lib_enc.BrotliEncoderCompressStream.restype = c_int
    lib_enc.BrotliEncoderCompressStream.argtypes = [c_void_p, c_int, POINTER(c_size_t), POINTER(POINTER(c_uint8)), POINTER(c_size_t), POINTER(POINTER(c_uint8)), c_void_p]
    lib_enc.BrotliEncoderDestroyInstance.argtypes = [c_void_p]
    lib_enc.BrotliEncoderDestroyPreparedDictionary.argtypes = [c_void_p]

    lib_dec.BrotliDecoderCreateInstance.restype = c_void_p
    lib_dec.BrotliDecoderCreateInstance.argtypes = [c_void_p, c_void_p, c_void_p]
    lib_dec.BrotliDecoderAttachDictionary.restype = c_int
    lib_dec.BrotliDecoderAttachDictionary.argtypes = [c_void_p, c_int, c_size_t, POINTER(c_uint8)]
    lib_dec.BrotliDecoderDecompressStream.restype = c_int
    lib_dec.BrotliDecoderDecompressStream.argtypes = [c_void_p, POINTER(c_size_t), POINTER(POINTER(c_uint8)), POINTER(c_size_t), POINTER(POINTER(c_uint8)), c_void_p]
    lib_dec.BrotliDecoderDestroyInstance.argtypes = [c_void_p]

    return lib_enc, lib_dec

_LIB_ENC, _LIB_DEC = _load_brotli_native()

def compress_one(data: bytes, zdict: bytes, quality: int, lgwin: int) -> bytes:
    state = _LIB_ENC.BrotliEncoderCreateInstance(None, None, None)
    _LIB_ENC.BrotliEncoderSetParameter(state, BROTLI_PARAM_QUALITY, quality)
    _LIB_ENC.BrotliEncoderSetParameter(state, BROTLI_PARAM_LGWIN, lgwin)

    prepared = None

    if zdict:
        dict_buf = (c_uint8 * len(zdict)).from_buffer_copy(zdict)
        prepared = _LIB_ENC.BrotliEncoderPrepareDictionary(
            BROTLI_SHARED_DICTIONARY_RAW, len(zdict),
            ctypes.cast(dict_buf, POINTER(c_uint8)), quality, None, None, None)

        if not prepared:
            raise RuntimeError("BrotliEncoderPrepareDictionary fallita")

        if not _LIB_ENC.BrotliEncoderAttachPreparedDictionary(state, prepared):
            raise RuntimeError("BrotliEncoderAttachPreparedDictionary fallita")

    in_buf = (c_uint8 * max(1, len(data))).from_buffer_copy(data)
    avail_in = c_size_t(len(data))
    next_in = ctypes.cast(in_buf, POINTER(c_uint8))

    cap = len(data) * 2 + 1024
    out_buf = (c_uint8 * cap)()
    avail_out = c_size_t(cap)
    next_out = ctypes.cast(out_buf, POINTER(c_uint8))

    ok = _LIB_ENC.BrotliEncoderCompressStream(
        state, BROTLI_OPERATION_FINISH,
        byref(avail_in), byref(next_in), byref(avail_out), byref(next_out), None)

    if not ok:
        raise RuntimeError("BrotliEncoderCompressStream fallita")

    produced = cap - avail_out.value
    result = bytes(out_buf[:produced])

    if prepared:
        _LIB_ENC.BrotliEncoderDestroyPreparedDictionary(prepared)

    _LIB_ENC.BrotliEncoderDestroyInstance(state)

    return result

def decompress_one(data: bytes, zdict: bytes) -> bytes:
    state = _LIB_DEC.BrotliDecoderCreateInstance(None, None, None)

    if zdict:
        dict_buf = (c_uint8 * len(zdict)).from_buffer_copy(zdict)

        if not _LIB_DEC.BrotliDecoderAttachDictionary(
            state, BROTLI_SHARED_DICTIONARY_RAW, len(zdict), ctypes.cast(dict_buf, POINTER(c_uint8))
        ):
            raise RuntimeError("BrotliDecoderAttachDictionary fallita")

    in_buf = (c_uint8 * max(1, len(data))).from_buffer_copy(data)
    avail_in = c_size_t(len(data))
    next_in = ctypes.cast(in_buf, POINTER(c_uint8))

    out = bytearray()

    while True:
        chunk_cap = 65536
        out_buf = (c_uint8 * chunk_cap)()
        avail_out = c_size_t(chunk_cap)
        next_out = ctypes.cast(out_buf, POINTER(c_uint8))

        res = _LIB_DEC.BrotliDecoderDecompressStream(
            state, byref(avail_in), byref(next_in), byref(avail_out), byref(next_out), None)

        produced = chunk_cap - avail_out.value
        out += bytes(out_buf[:produced])

        if res == 1:  # BROTLI_DECODER_RESULT_SUCCESS
            break
        elif res == 3:  # BROTLI_DECODER_RESULT_NEEDS_MORE_OUTPUT
            continue
        else:
            raise RuntimeError(f"BrotliDecoderDecompressStream errore (result={res})")

    _LIB_DEC.BrotliDecoderDestroyInstance(state)

    return bytes(out)

# ---------------------------
# I/O stringhe (stessa logica degli altri script)
# ---------------------------
def read_strings_text(path: str) -> list:
    out = []

    full_path = os.path.join("..", "inputs", path)

    with open(full_path, "r", encoding = "utf-8") as f:
        for line in f:
            line = line.rstrip("\n\r")

            if not line:
                continue

            try:
                v = ast.literal_eval(line)
                out.append(v if isinstance(v, str) else line)
            except Exception:
                out.append(line)

    return out

def to_utf8_bytes(strings: list) -> list:
    return [s.encode("utf-8") for s in strings]

# ---------------------------
# Dizionario condiviso (corpus concatenato, come raw dictionary)
# ---------------------------
def build_shared_dict(byte_strings: list) -> bytes:
    return b"".join(byte_strings)

# ---------------------------
# Encode / Decode file
# ---------------------------
def encode_onefile(input_txt: str, output_bin: str, quality: int = 11, lgwin: int = BROTLI_MAX_WINDOW_BITS):
    t_start = time.time()

    strings = read_strings_text(input_txt)
    byte_strings = to_utf8_bytes(strings)

    zdict = build_shared_dict(byte_strings)

    out = bytearray()
    out += MAGIC
    out += bytes([VERSION])
    out += uvarint_encode(len(zdict))
    out += zdict
    out += uvarint_encode(len(byte_strings))

    stream_bytes = 0

    for bs in byte_strings:
        comp = compress_one(bs, zdict, quality, lgwin)
        out += uvarint_encode(len(comp))
        out += comp
        stream_bytes += len(comp)

    output_dir = os.path.join("..", "outputs")
    os.makedirs(output_dir, exist_ok = True)
    full_output_path = os.path.join(output_dir, output_bin)

    with open(full_output_path, "wb") as f:
        f.write(bytes(out))

    orig_bytes = sum(len(b) for b in byte_strings)
    t_elapsed = time.time() - t_start

    logging.info(f"OK: scritto {output_bin}")
    logging.info(f"Stringhe: {len(strings)}")
    logging.info(f"Originale (UTF-8 bytes): {orig_bytes}")
    logging.info(f"Dizionario condiviso (raw) = {len(zdict)} bytes")
    logging.info(f"Stream compressi (per-stringa, somma): {stream_bytes} bytes")
    logging.info(f"Output totale (bytes): {len(out)}")
    logging.info(f"Tempo: {t_elapsed:.2f} s")

def decompress_onefile(path_bin: str) -> list:
    full_path = os.path.join("..", "outputs", path_bin)

    with open(full_path, "rb") as f:
        data = f.read()

    pos = 0

    if data[pos : pos + 4] != MAGIC:
        raise ValueError("MAGIC non valido")

    pos += 4
    ver = data[pos]
    pos += 1

    if ver != VERSION:
        raise ValueError(f"Versione non supportata: {ver}")

    dict_len, pos = uvarint_decode(data, pos)
    zdict = data[pos : pos + dict_len]
    pos += dict_len

    n, pos = uvarint_decode(data, pos)

    out_strings = []

    for _ in range(n):
        comp_len, pos = uvarint_decode(data, pos)
        comp = data[pos : pos + comp_len]
        pos += comp_len

        raw = decompress_one(comp, zdict)
        out_strings.append(raw.decode("utf-8"))

    return out_strings

# ---------------------------
# CLI
# ---------------------------
def main():
    ap = argparse.ArgumentParser(description = "Baseline brotli con dizionario condiviso vero (ctypes su API nativa)")

    ap.add_argument("mode", choices = ["compress", "decompress"])
    ap.add_argument("input")
    ap.add_argument("output", nargs = "?")
    ap.add_argument("--quality", type = int, default = 11, help = "Qualita' brotli (0-11, default 11 = massima)")
    ap.add_argument("--lgwin", type = int, default = BROTLI_MAX_WINDOW_BITS, help = f"log2 finestra (10-{BROTLI_MAX_WINDOW_BITS}, default {BROTLI_MAX_WINDOW_BITS})")

    args = ap.parse_args()

    setup_logger(args.input)

    if args.mode == "compress":
        out = args.output or f"brotli_{args.input.split('.')[0]}_compressed.bin"
        encode_onefile(args.input, out, args.quality, args.lgwin)
    else:
        strings = decompress_onefile(args.input)

        if args.output:
            output_dir = os.path.join("..", "outputs")
            os.makedirs(output_dir, exist_ok = True)
            full_out = os.path.join(output_dir, args.output)

            with open(full_out, "w", encoding = "utf-8") as f:
                for s in strings:
                    f.write(s + "\n")

            logging.info(f"OK: scritto {args.output}")
        else:
            for s in strings:
                logging.info(s)

if __name__ == "__main__":
    main()