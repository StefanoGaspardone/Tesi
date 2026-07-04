#!/usr/bin/env python3
import argparse
import ast
import math
from collections import defaultdict

MAGIC = b"SDB1"
VERSION = 1
FLAGS = 0

RAW = 0
TOK = 1


# ---------------------------
# Varint (LEB128 unsigned)
# ---------------------------
def uvarint_encode(x: int) -> bytes:
    out = bytearray()
    while True:
        b = x & 0x7F
        x >>= 7
        if x:
            out.append(b | 0x80)
        else:
            out.append(b)
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


# ---------------------------
# Bit packer / unpacker
# ---------------------------
class BitWriter:
    def __init__(self):
        self.buf = bytearray()
        self.acc = 0
        self.nbits = 0

    def write_bits(self, value: int, n: int):
        # scrive i bit MSB-first di 'value' (n bit)
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
        b = self.data[self.pos:self.pos+n]
        self.pos += n
        return b

    def align_to_byte(self):
        self.nbits = 0


# ---------------------------
# Helpers
# ---------------------------
def needed_bits(n: int) -> int:
    return 1 if n <= 1 else math.ceil(math.log2(n))

def read_strings_text(path: str):
    """
    Legge una stringa per riga.
    Se la riga sembra una stringa Python tra virgolette, prova ast.literal_eval.
    """
    out = []
    with open(f"./inputs/{path}", "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n\r")
            if line == "":
                continue
            try:
                v = ast.literal_eval(line)
                if isinstance(v, str):
                    out.append(v)
                else:
                    out.append(line)
            except Exception:
                out.append(line)
    return out

def to_utf8_bytes(strings):
    return [s.encode("utf-8") for s in strings]

def build_alphabet(byte_strings):
    s = set()
    for b in byte_strings:
        s.update(b)
    alph = bytes(sorted(s))
    inv = {alph[i]: i for i in range(len(alph))}
    return alph, inv, needed_bits(len(alph))


# ---------------------------
# Dictionary building (greedy MDL-ish)
# ---------------------------
def initial_sequences(byte_strings):
    # sequenza di simboli: RAW(byte_val) o TOK(token_id)
    return [[(RAW, x) for x in bs] for bs in byte_strings]

def find_candidates(seqs, min_len=2, max_len=32):
    """
    Conta sottostringhe (solo RAW) per ciascuna stringa.
    Non attraversa token.
    """
    counts = defaultdict(int)
    for seq in seqs:
        n = len(seq)
        for i in range(n):
            if seq[i][0] != RAW:
                continue
            acc = []
            for j in range(i, min(n, i + max_len)):
                if seq[j][0] != RAW:
                    break
                acc.append(seq[j][1])
                if len(acc) >= min_len:
                    counts[bytes(acc)] += 1
    return {k: v for k, v in counts.items() if v >= 2}

def count_non_overlapping(seq, pat_bytes: bytes):
    pat = [(RAW, b) for b in pat_bytes]
    m = len(pat)
    i = 0
    c = 0
    while i <= len(seq) - m:
        if seq[i:i+m] == pat:
            c += 1
            i += m
        else:
            i += 1
    return c

def total_non_overlapping(seqs, pat_bytes: bytes):
    return sum(count_non_overlapping(seq, pat_bytes) for seq in seqs)

def replace_non_overlapping(seqs, pat_bytes: bytes, token_id: int):
    pat = [(RAW, b) for b in pat_bytes]
    m = len(pat)
    token = (TOK, token_id)
    out_all = []
    for seq in seqs:
        out = []
        i = 0
        while i < len(seq):
            if i <= len(seq) - m and seq[i:i+m] == pat:
                out.append(token)
                i += m
            else:
                out.append(seq[i])
                i += 1
        out_all.append(out)
    return out_all

def varint_size(x: int) -> int:
    return len(uvarint_encode(x))

def estimate_gain_bits(pat_bytes: bytes, occ: int, char_bits: int, token_bits_after: int):
    """
    Stima guadagno netto in bit includendo costo dizionario.
    Stream:
      RAW simbolo costa 1 + char_bits
      TOK simbolo costa 1 + token_bits
    Dizionario:
      len(varint)*8 + len(pat)*char_bits   (salvo entry come indici bitpacked)
    """
    L = len(pat_bytes)
    raw_sym = 1 + char_bits
    tok_sym = 1 + token_bits_after

    old_cost = occ * L * raw_sym
    new_cost = occ * tok_sym

    dict_cost = (varint_size(L) * 8) + (L * char_bits)
    return old_cost - new_cost - dict_cost

def build_dictionary(byte_strings, char_bits, min_len=2, max_len=32, max_dict=1023):
    seqs = initial_sequences(byte_strings)
    dictionary = []

    while len(dictionary) < max_dict:
        token_bits_after = needed_bits(len(dictionary) + 1)

        candidates = find_candidates(seqs, min_len=min_len, max_len=max_len)
        best = None
        best_gain = 0
        best_occ = 0

        for pat, _freq in candidates.items():
            occ = total_non_overlapping(seqs, pat)
            if occ < 2:
                continue
            gain = estimate_gain_bits(pat, occ, char_bits, token_bits_after)
            if gain > best_gain:
                best_gain = gain
                best = pat
                best_occ = occ

        if best is None or best_gain <= 0:
            break

        dictionary.append(best)
        seqs = replace_non_overlapping(seqs, best, len(dictionary) - 1)

    return dictionary, seqs


# ---------------------------
# Encode / Decode
# ---------------------------
def encode_onefile(input_txt: str, output_bin: str,
                   min_len=2, max_len=32, max_dict=1023):
    strings = read_strings_text(input_txt)
    byte_strings = to_utf8_bytes(strings)

    alphabet, byte_to_id, char_bits = build_alphabet(byte_strings)

    dictionary, seqs = build_dictionary(byte_strings, char_bits,
                                        min_len=min_len, max_len=max_len, max_dict=max_dict)
    D = len(dictionary)
    token_bits = needed_bits(D)

    bw = BitWriter()

    # Header
    bw.write_bytes_aligned(MAGIC)
    bw.write_bytes_aligned(bytes([VERSION, FLAGS]))

    # Alphabet
    bw.write_bytes_aligned(uvarint_encode(len(alphabet)))
    bw.write_bytes_aligned(alphabet)  # raw bytes

    # Dictionary (bitpacked indices)
    bw.write_bytes_aligned(uvarint_encode(D))
    for entry in dictionary:
        bw.write_bytes_aligned(uvarint_encode(len(entry)))
        for b in entry:
            bw.write_bits(byte_to_id[b], char_bits)

    # Stream
    bw.write_bytes_aligned(uvarint_encode(len(seqs)))
    for seq in seqs:
        bw.write_bytes_aligned(uvarint_encode(len(seq)))
        for typ, val in seq:
            if typ == RAW:
                bw.write_bits(0, 1)
                bw.write_bits(byte_to_id[val], char_bits)
            else:
                bw.write_bits(1, 1)
                bw.write_bits(val, token_bits)

    data = bw.getvalue()

    with open(output_bin, "wb") as f:
        f.write(data)

    # stats
    orig_bytes = sum(len(b) for b in byte_strings)
    dict_bytes = sum(len(e) for e in dictionary)
    print("OK: scritto", output_bin)
    print(f"Stringhe: {len(strings)}")
    print(f"Originale (UTF-8 bytes): {orig_bytes}")
    print(f"Alfabeto A={len(alphabet)} => char_bits={char_bits}")
    print(f"Dizionario D={D} => token_bits={token_bits}, bytes_dizionario_raw={dict_bytes}")
    print(f"Output totale (bytes): {len(data)}")


def decompress_onefile(path_bin: str):
    with open(path_bin, "rb") as f:
        data = f.read()

    pos = 0
    if data[pos:pos+4] != MAGIC:
        raise ValueError("MAGIC non valido")
    pos += 4

    ver = data[pos]
    flags = data[pos+1]
    pos += 2
    if ver != VERSION:
        raise ValueError(f"Versione non supportata: {ver}")

    # Alphabet
    A, pos = uvarint_decode(data, pos)
    alphabet = data[pos:pos+A]
    pos += A
    if A == 0:
        alphabet = b"\x00"
        A = 1
    char_bits = needed_bits(A)

    # Dictionary
    D, pos = uvarint_decode(data, pos)
    token_bits = needed_bits(D)
    br = BitReader(data, pos)

    dictionary = []
    for _ in range(D):
        br.align_to_byte()
        L, br.pos = uvarint_decode(br.data, br.pos)
        entry = bytearray()
        for _ in range(L):
            cid = br.read_bits(char_bits)
            entry.append(alphabet[cid])
        dictionary.append(bytes(entry))

    # Stream
    br.align_to_byte()
    N, br.pos = uvarint_decode(br.data, br.pos)

    out_strings = []
    for _ in range(N):
        br.align_to_byte()
        S, br.pos = uvarint_decode(br.data, br.pos)
        out = bytearray()
        for _ in range(S):
            flag = br.read_bits(1)
            if flag == 0:
                cid = br.read_bits(char_bits)
                out.append(alphabet[cid])
            else:
                tid = br.read_bits(token_bits)
                out.extend(dictionary[tid])
        out_strings.append(out.decode("utf-8"))

    return out_strings


# ---------------------------
# CLI
# ---------------------------
def main():
    ap = argparse.ArgumentParser(
        description="Compressore autosufficiente: header+alfabeto+dizionario+bitstream (UTF-8 byte-level, bitpacked)."
    )
    ap.add_argument("mode", choices=["compress", "decompress"], help="Modalità")
    ap.add_argument("input", help="Input: .txt per compress, .bin per decompress")
    ap.add_argument("output", nargs="?", help="Output: .bin per compress, .txt per decompress (opzionale)")
    ap.add_argument("--min-len", type=int, default=2, help="Lunghezza minima token")
    ap.add_argument("--max-len", type=int, default=32, help="Lunghezza massima token")
    ap.add_argument("--max-dict", type=int, default=1023, help="Max token nel dizionario")

    args = ap.parse_args()

    if args.mode == "compress":
        out = args.output or "compressed.bin"
        encode_onefile(args.input, out,
                       min_len=args.min_len, max_len=args.max_len, max_dict=args.max_dict)

    else:
        strings = decompress_onefile(args.input)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                for s in strings:
                    f.write(s + "\n")
            print("OK: scritto", args.output)
        else:
            # stampa a schermo
            for s in strings:
                print(s)


if __name__ == "__main__":
    main()
