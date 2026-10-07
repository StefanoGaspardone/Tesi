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

# ---------------------
# Exponential encoding
# ---------------------

EXP_N0 = 4

def exp_size(x: int, n0: int = EXP_N0) -> int:
    n = n0
    total_bits = 0
    first_ext = True
    while True:
        threshold = (1 << n) - 1
        total_bits += n
        if x < threshold:
            return total_bits
        x -= threshold
        if first_ext:
            first_ext = False
        else:
            n *= 2

def exp_write(bw, x: int, n0: int = EXP_N0):
    n = n0
    first_ext = True
    while True:
        threshold = (1 << n) - 1
        if x < threshold:
            bw.write_bits(x, n)
            return
        bw.write_bits(threshold, n)
        x -= threshold
        if first_ext:
            first_ext = False
        else:
            n *= 2

def exp_read(br, n0: int = EXP_N0) -> int:
    n = n0
    total = 0
    first_ext = True
    while True:
        v = br.read_bits(n)
        threshold = (1 << n) - 1
        if v < threshold:
            return total + v
        total += threshold
        if first_ext:
            first_ext = False
        else:
            n *= 2

# ---------------------------
# Bit packer / unpacker
# ---------------------------
class BitWriter:
    def __init__(self):
        self.buf = bytearray()
        self.acc = 0
        self.nbits = 0

    def write_bits(self, value: int, n: int):
        for i in reversed(range(n)):
            self.acc = (self.acc << 1) | ((value >> i) & 1)
            self.nbits += 1

            if self.nbits == 8:
                self.buf.append(self.acc & 0xFF)
                self.acc = 0
                self.nbits = 0

    def write_bytes_aligned(self, b: bytes):
        self.flush_to_byte()
        self.buf.extend(b)

    def flush_to_byte(self):
        if self.nbits:
            self.acc <<= (8 - self.nbits)
            self.buf.append(self.acc & 0xFF)
            self.acc = 0
            self.nbits = 0

    def getvalue(self) -> bytes:
        self.flush_to_byte()
        return bytes(self.buf)

class BitReader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos
        self.acc = 0
        self.nbits = 0

    def read_bits(self, n: int) -> int:
        v = 0

        for _ in range(n):
            if self.nbits == 0:
                self.acc = self.data[self.pos]
                self.pos += 1
                self.nbits = 8

            v = (v << 1) | ((self.acc >> (self.nbits - 1)) & 1)
            self.nbits -= 1

        return v

    def read_bytes_aligned(self, n: int) -> bytes:
        self.align_to_byte()

        b = self.data[self.pos : self.pos + n]
        self.pos += n

        return b

    def align_to_byte(self):
        self.nbits = 0

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

    bw = BitWriter()
    bw.write_bytes_aligned(MAGIC)
    bw.write_bytes_aligned(bytes([VERSION]))
    exp_write(bw, len(zdict))
    bw.write_bytes_aligned(zdict)
    exp_write(bw, len(byte_strings))

    dict_overhead_bytes = len(zdict)
    stream_bytes = 0

    for bs in byte_strings:
        comp = compress_one(bs, zdict, level)
        exp_write(bw, len(comp))
        bw.write_bytes_aligned(comp)
        stream_bytes += len(comp)

    out = bw.getvalue()

    output_dir = os.path.join("..", "outputs")
    os.makedirs(output_dir, exist_ok = True)
    full_output_path = os.path.join(output_dir, output_bin)

    with open(full_output_path, "wb") as f:
        f.write(out)

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

    br = BitReader(data, pos)

    dict_len = exp_read(br)
    zdict = br.read_bytes_aligned(dict_len)

    n = exp_read(br)

    out_strings = []

    for _ in range(n):
        comp_len = exp_read(br)
        comp = br.read_bytes_aligned(comp_len)

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