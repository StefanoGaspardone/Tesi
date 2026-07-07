#!/usr/bin/env python3
# zlib

import argparse
import ast
import zlib
import struct
import time
import logging
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

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
# I/O stringhe
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
# Dictionary preset
# ---------------------------
def build_preset_dict(byte_strings: list, max_size: int = 32768) -> bytes:
    freq = Counter(byte_strings)
    sorted_strings = sorted(freq.keys(), key = lambda s: freq[s])
    combined = b''.join(sorted_strings)
    
    if len(combined) > max_size:
        combined = combined[-max_size:]
    
    return combined

# ---------------------------
# Encode / Decode
# ---------------------------
def encode_onefile(input_txt: str, output_bin: str, level: int = 9):
    t_start = time.time()

    strings = read_strings_text(input_txt)
    byte_strings = to_utf8_bytes(strings)

    preset_dict = build_preset_dict(byte_strings)

    compressed_strings = []
    for bs in byte_strings:
        c = zlib.compressobj(level, zlib.DEFLATED, zlib.MAX_WBITS, zlib.DEF_MEM_LEVEL, zlib.Z_DEFAULT_STRATEGY, preset_dict)
        compressed = c.compress(bs) + c.flush()
        compressed_strings.append(compressed)

    out = struct.pack('>I', len(preset_dict)) + preset_dict
    out += struct.pack('>I', len(compressed_strings))
    
    for cs in compressed_strings:
        out += struct.pack('>I', len(cs)) + cs

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
    logging.info(f"Dizionario preset (bytes): {len(preset_dict)}")
    logging.info(f"Output totale (bytes): {len(out)}")
    logging.info(f"Rapporto: {len(out) / orig_bytes:.3f}")
    logging.info(f"Tempo: {t_elapsed:.4f} s")

def decompress_onefile(path_bin: str) -> list:
    full_path = os.path.join("..", "outputs", path_bin)
    
    with open(full_path, "rb") as f:
        data = f.read()

    pos = 0
    dict_len = struct.unpack_from('>I', data, pos)[0]
    pos += 4
    preset_dict = data[pos : pos+dict_len]
    pos += dict_len
    n_strings = struct.unpack_from('>I', data, pos)[0]
    pos += 4

    strings = []
    for _ in range(n_strings):
        cs_len = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        cs = data[pos : pos+cs_len]
        pos += cs_len
        
        decompressed = zlib.decompressobj(zdict = preset_dict).decompress(cs)
        strings.append(decompressed.decode("utf-8"))

    return strings

# ---------------------------
# CLI
# ---------------------------
def main():
    ap = argparse.ArgumentParser(description = "zlib/DEFLATE con dizionario preset")
    ap.add_argument("mode", choices = ["compress", "decompress"])
    ap.add_argument("input")
    ap.add_argument("output", nargs = "?")
    ap.add_argument("--level", type = int, default = 9, choices = list(range(10)), help = "Livello di compressione zlib 0-9 (default: 9)")
    
    args = ap.parse_args()

    setup_logger(args.input)

    if args.mode == "compress":
        out = args.output or f"zlib_{args.input.split('.')[0]}_compressed.bin"
        encode_onefile(args.input, out, args.level)
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