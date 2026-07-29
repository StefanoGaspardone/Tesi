#!/usr/bin/env python3
# zstd

import argparse
import ast
import time
import os
import logging
from datetime import datetime
from pathlib import Path

import zstandard as zstd

MAGIC = b"ZSD1"
VERSION = 1

DICT_RAW = 0
DICT_TRAINED = 1

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
def build_shared_dict(byte_strings: list, mode: str, dict_size: int) -> tuple:
    if mode == "raw":
        corpus = b"".join(byte_strings)
        d = zstd.ZstdCompressionDict(corpus, dict_type = zstd.DICT_TYPE_RAWCONTENT)

        return corpus, d, DICT_RAW

    d = zstd.train_dictionary(dict_size, byte_strings)
    raw = d.as_bytes()

    return raw, d, DICT_TRAINED

def load_shared_dict(raw: bytes, dict_kind: int) -> "zstd.ZstdCompressionDict":
    if dict_kind == DICT_RAW:
        return zstd.ZstdCompressionDict(raw, dict_type = zstd.DICT_TYPE_RAWCONTENT)

    return zstd.ZstdCompressionDict(raw)

# ---------------------------
# Compress / decompress
# ---------------------------
def compress_one(cctx: "zstd.ZstdCompressor", data: bytes) -> bytes:
    return cctx.compress(data)

def decompress_one(dctx: "zstd.ZstdDecompressor", data: bytes) -> bytes:
    return dctx.decompress(data)

def evaluate_dict_size(byte_strings: list, level: int, size: int):
    try:
        dict_raw, dict_obj, dict_kind = build_shared_dict(byte_strings, "trained", size)
    except Exception:
        return None

    cctx = zstd.ZstdCompressor(level = level, dict_data = dict_obj)
    stream_bytes = sum(len(compress_one(cctx, bs)) for bs in byte_strings)
    total = len(dict_raw) + stream_bytes + len(byte_strings) * 2

    return dict_raw, dict_obj, dict_kind, total

def auto_tune_dict_size(byte_strings: list, level: int) -> tuple:
    corpus_size = sum(len(bs) for bs in byte_strings)
    max_size = max(128, min(corpus_size, 65536))

    candidates = []
    s = 128
    while s < max_size:
        candidates.append(s)
        s = int(s * 1.6)
    candidates.append(max_size)
    candidates = sorted(set(candidates))

    results = {}
    for c in candidates:
        r = evaluate_dict_size(byte_strings, level, c)
        if r is not None:
            results[c] = r

    if not results:
        raise RuntimeError("Nessuna dimensione di dizionario valida trovata nello sweep iniziale")

    best_size = min(results, key = lambda k: results[k][3])

    for _ in range(2):
        step = max(64, best_size // 4)
        neighbors = [best_size - step, best_size + step]

        for c in neighbors:
            if c < 64 or c > max_size or c in results:
                continue

            r = evaluate_dict_size(byte_strings, level, c)
            if r is not None:
                results[c] = r

        new_best = min(results, key = lambda k: results[k][3])
        if new_best == best_size:
            break
        best_size = new_best

    dict_raw, dict_obj, dict_kind, _ = results[best_size]
    return dict_raw, dict_obj, dict_kind, best_size

# ---------------------------
# Encode / Decode file
# ---------------------------
def encode_onefile(input_txt: str, output_bin: str, level: int = 22, dict_mode: str = "raw", dict_size: int | None = None):
    t_start = time.time()

    strings = read_strings_text(input_txt)
    byte_strings = to_utf8_bytes(strings)

    if dict_mode == "trained" and dict_size is None:
        dict_raw, dict_obj, dict_kind, _chosen_size = auto_tune_dict_size(byte_strings, level)
    else:
        dict_raw, dict_obj, dict_kind = build_shared_dict(byte_strings, dict_mode, dict_size or 112640)

    cctx = zstd.ZstdCompressor(level = level, dict_data = dict_obj)

    out = bytearray()
    out += MAGIC
    out += bytes([VERSION, dict_kind])
    out += uvarint_encode(len(dict_raw))
    out += dict_raw
    out += uvarint_encode(len(byte_strings))

    stream_bytes = 0

    for bs in byte_strings:
        comp = compress_one(cctx, bs)
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
    logging.info(f"Dizionario condiviso ({dict_mode}) = {len(dict_raw)} bytes")
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
    dict_kind = data[pos]
    pos += 1

    if ver != VERSION:
        raise ValueError(f"Versione non supportata: {ver}")

    dict_len, pos = uvarint_decode(data, pos)
    dict_raw = data[pos : pos + dict_len]
    pos += dict_len

    dict_obj = load_shared_dict(dict_raw, dict_kind)
    dctx = zstd.ZstdDecompressor(dict_data = dict_obj)

    n, pos = uvarint_decode(data, pos)

    out_strings = []

    for _ in range(n):
        comp_len, pos = uvarint_decode(data, pos)
        comp = data[pos : pos + comp_len]
        pos += comp_len

        raw = decompress_one(dctx, comp)
        out_strings.append(raw.decode("utf-8"))

    return out_strings

# ---------------------------
# CLI
# ---------------------------
def main():
    ap = argparse.ArgumentParser(description = "Baseline zstandard con dizionario condiviso")

    ap.add_argument("mode", choices = ["compress", "decompress"])
    ap.add_argument("input")
    ap.add_argument("output", nargs = "?")
    ap.add_argument("--level", type = int, default = 22, help = "Livello compressione zstd (1-22, default 22 = ultra)")
    ap.add_argument("--dict-mode", default = "raw", choices = ["raw", "trained"], help = "raw = corpus concatenato come dizionario; trained = dizionario ottimizzato COVER (richiede corpus abbastanza grande/vario)")
    ap.add_argument("--dict-size", type = int, default = None, help = "Dimensione target del dizionario trained (bytes). Se omesso con --dict-mode trained, viene cercata automaticamente la dimensione migliore.")

    args = ap.parse_args()

    setup_logger(args.input)

    if args.mode == "compress":
        out = args.output or f"zstd_{args.input.split('.')[0]}_compressed.bin"
        encode_onefile(args.input, out, args.level, args.dict_mode, args.dict_size)
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