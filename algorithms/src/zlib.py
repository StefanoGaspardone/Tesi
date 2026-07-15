#!/usr/bin/env python3
# zlib

import argparse
import ast
import time
import os
import zlib
import logging
from datetime import datetime
from pathlib import Path

MAGIC = b"ZLB1"
VERSION = 1

ZLIB_MAX_ZDICT = 32768

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
# I/O strings
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
# Dictionary
# ---------------------------
def build_shared_dict(byte_strings: list, max_dict_bytes: int) -> bytes:
    corpus = b"".join(byte_strings)

    if len(corpus) > max_dict_bytes:
        corpus = corpus[-max_dict_bytes:]

    return corpus

def compress_one(data: bytes, zdict: bytes, level: int) -> bytes:
    co = zlib.compressobj(level, zlib.DEFLATED, 15, 9, zlib.Z_DEFAULT_STRATEGY, zdict = zdict)
    return co.compress(data) + co.flush()

def decompress_one(data: bytes, zdict: bytes) -> bytes:
    do = zlib.decompressobj(zdict = zdict)
    return do.decompress(data) + do.flush()

# ---------------------------
# Encode / Decode file
# ---------------------------
def encode_onefile(input_txt: str, output_bin: str, level: int = 9, max_dict_bytes: int = ZLIB_MAX_ZDICT):
    t_start = time.time()

    strings = read_strings_text(input_txt)
    byte_strings = to_utf8_bytes(strings)

    zdict = build_shared_dict(byte_strings, max_dict_bytes)

    out = bytearray()
    out += MAGIC
    out += bytes([VERSION])
    out += uvarint_encode(len(zdict))
    out += zdict
    out += uvarint_encode(len(byte_strings))

    dict_overhead_bytes = len(zdict)
    stream_bytes = 0

    for bs in byte_strings:
        comp = compress_one(bs, zdict, level)
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
    logging.info(f"Dizionario condiviso (zdict) = {dict_overhead_bytes} bytes (max {max_dict_bytes})")
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
    ap = argparse.ArgumentParser(description = "Baseline zlib/deflate con dizionario condiviso (zdict)")

    ap.add_argument("mode", choices = ["compress", "decompress"])
    ap.add_argument("input")
    ap.add_argument("output", nargs = "?")
    ap.add_argument("--level", type = int, default = 9, help = "Livello compressione zlib (0-9, default 9)")
    ap.add_argument("--max-dict-bytes", type = int, default = ZLIB_MAX_ZDICT, help = f"Dimensione massima zdict (hard limit zlib = {ZLIB_MAX_ZDICT})")

    args = ap.parse_args()

    setup_logger(args.input)

    if args.mode == "compress":
        out = args.output or f"zlib_{args.input.split('.')[0]}_compressed.bin"
        encode_onefile(args.input, out, args.level, args.max_dict_bytes)
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