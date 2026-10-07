#!/usr/bin/env python3
# brotli

import argparse
import ast
import ctypes
import platform
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
# Ponte ctypes verso libbrotlienc / libbrotlidec
# ---------------------------
def _candidate_names(base: str) -> list:
    system = platform.system()

    if system == "Windows":
        # Nomi possibili a seconda di come sono state ottenute le DLL
        # (MSYS2/MinGW usa il prefisso "lib", vcpkg no).
        return [f"{base}.dll", f"lib{base}.dll", f"{base}-1.dll", f"lib{base}-1.dll"]
    elif system == "Darwin":
        return [f"lib{base}.1.dylib", f"lib{base}.dylib"]
    else:
        return [f"lib{base}.so.1", f"lib{base}.so"]

def _windows_extra_dll_dirs() -> list:
    candidates = [
        os.environ.get("MSYS2_ROOT"),
        r"C:\msys64\mingw64\bin",
        r"C:\msys64\ucrt64\bin",
        r"C:\DevTools\msys2\mingw64\bin",
        r"C:\DevTools\msys2\ucrt64\bin",
    ]
    return [c for c in candidates if c and os.path.isdir(c)]

def _load_one(base: str):
    tried = []

    def try_names():
        for name in _candidate_names(base):
            try:
                return ctypes.CDLL(name)
            except OSError as e:
                tried.append((name, str(e)))
        return None

    lib = try_names()
    added_dirs = []

    if lib is None and platform.system() == "Windows" and hasattr(os, "add_dll_directory"):
        for d in _windows_extra_dll_dirs():
            try:
                os.add_dll_directory(d)
                added_dirs.append(d)
            except OSError:
                pass

        if added_dirs:
            tried.clear()
            lib = try_names()

    if lib is not None:
        return lib

    system = platform.system()

    if system == "Windows":
        hint = (
            "Su Windows queste DLL non sono incluse di default. Se hai gia' MSYS2 "
            "installato (usato anche per compilare c2.dll), il modo piu' semplice e':\n"
            "  pacman -S mingw-w64-x86_64-brotli\n"
            + (f"(gia' cercate anche in: {', '.join(added_dirs)}, senza successo)\n" if added_dirs else
               "Le cartelle MSYS2 abituali (C:\\msys64\\mingw64\\bin, C:\\msys64\\ucrt64\\bin) "
               "non sono state trovate su questo sistema: se MSYS2 e' installato altrove, "
               "imposta la variabile d'ambiente MSYS2_ROOT alla cartella bin corretta, oppure "
               "copia le DLL (incluse le loro dipendenze) nella stessa cartella di questo file.")
        )
    elif system == "Darwin":
        hint = "Su macOS: brew install brotli"
    else:
        hint = "Su Linux: apt install libbrotli1 (o l'equivalente della tua distro)"

    details = "\n".join(f"  - {name}: {err}" for name, err in tried)
    raise OSError(f"Impossibile caricare la libreria nativa '{base}'. Nomi provati:\n{details}\n\n{hint}")

def _load_brotli_native():
    lib_enc = _load_one("brotlienc")
    lib_dec = _load_one("brotlidec")

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
    lib_enc.BrotliEncoderIsFinished.restype = c_int
    lib_enc.BrotliEncoderIsFinished.argtypes = [c_void_p]

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
    prepared = None

    try:
        _LIB_ENC.BrotliEncoderSetParameter(state, BROTLI_PARAM_QUALITY, quality)
        _LIB_ENC.BrotliEncoderSetParameter(state, BROTLI_PARAM_LGWIN, lgwin)

        if zdict:
            dict_buf = (c_uint8 * len(zdict)).from_buffer_copy(zdict)
            prepared = _LIB_ENC.BrotliEncoderPrepareDictionary(
                BROTLI_SHARED_DICTIONARY_RAW, len(zdict),
                ctypes.cast(dict_buf, POINTER(c_uint8)), quality, None, None, None)

            if not prepared:
                raise RuntimeError("BrotliEncoderPrepareDictionary fallita")

            if not _LIB_ENC.BrotliEncoderAttachPreparedDictionary(state, prepared):
                raise RuntimeError("BrotliEncoderAttachPreparedDictionary fallita")

        # ctypes gestisce correttamente array di lunghezza 0 -- niente bisogno
        # di un max(1, ...): forzare una capacita' di 1 byte mentre si copiano
        # 0 byte fa fallire from_buffer_copy su stringhe vuote.
        in_buf = (c_uint8 * len(data)).from_buffer_copy(data)
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

        # Senza questo controllo, un buffer di output troppo piccolo farebbe
        # tornare un output silenziosamente troncato (CompressStream puo'
        # restituire successo anche se lo stream non e' ancora completo).
        if not _LIB_ENC.BrotliEncoderIsFinished(state):
            raise RuntimeError("BrotliEncoderCompressStream non ha completato lo stream (buffer di output insufficiente?)")

        produced = cap - avail_out.value
        return bytes(out_buf[:produced])
    finally:
        if prepared:
            _LIB_ENC.BrotliEncoderDestroyPreparedDictionary(prepared)
        _LIB_ENC.BrotliEncoderDestroyInstance(state)

def decompress_one(data: bytes, zdict: bytes) -> bytes:
    state = _LIB_DEC.BrotliDecoderCreateInstance(None, None, None)

    try:
        if zdict:
            dict_buf = (c_uint8 * len(zdict)).from_buffer_copy(zdict)

            if not _LIB_DEC.BrotliDecoderAttachDictionary(
                state, BROTLI_SHARED_DICTIONARY_RAW, len(zdict), ctypes.cast(dict_buf, POINTER(c_uint8))
            ):
                raise RuntimeError("BrotliDecoderAttachDictionary fallita")

        in_buf = (c_uint8 * len(data)).from_buffer_copy(data)
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

        return bytes(out)
    finally:
        _LIB_DEC.BrotliDecoderDestroyInstance(state)

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

    # I campi di lunghezza usano la codifica esponenziale (stessa dei metodi proposti);
    # i blocchi di byte grezzi (dizionario, stream brotli) restano allineati al byte
    bw = BitWriter()
    bw.write_bytes_aligned(MAGIC)
    bw.write_bytes_aligned(bytes([VERSION]))
    exp_write(bw, len(zdict))
    bw.write_bytes_aligned(zdict)
    exp_write(bw, len(byte_strings))

    stream_bytes = 0

    for bs in byte_strings:
        comp = compress_one(bs, zdict, quality, lgwin)
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