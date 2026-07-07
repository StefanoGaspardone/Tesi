#!/usr/bin/env python3
# c2 exhaustive restricted

import argparse
import ast
import math
import heapq
import time
import os
import logging
from datetime import datetime
from collections import defaultdict
from pathlib import Path

MAGIC = b"SDB1"
VERSION = 1

RAW = 0
TOK = 1

ENC_FIXED = 0
ENC_HUFF_FREQ = 1
ENC_HUFF_LEN = 2
ENC_POSITIONAL = 3

ENC_NAME = {
    'fixed': ENC_FIXED,
    'huffman-freq': ENC_HUFF_FREQ,
    'huffman-len': ENC_HUFF_LEN,
    'positional': ENC_POSITIONAL,
}

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

def needed_bits(n: int) -> int:
    return 1 if n <= 1 else math.ceil(math.log2(n))

# ---------------------------
# Bit reader / writer
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
# Huffman
# ---------------------------
def huffman_lengths(freq_map: dict) -> dict:
    if not freq_map:
        return {}
    
    if len(freq_map) == 1:
        return {next(iter(freq_map)): 1}
    
    heap = [[f, i, [s]] for i, (s, f) in enumerate(sorted(freq_map.items()))]
    heapq.heapify(heap)
    
    lengths = dict.fromkeys(freq_map, 0)
    tie = len(heap)
    
    while len(heap) > 1:
        f1, _, s1 = heapq.heappop(heap)
        f2, _, s2 = heapq.heappop(heap)
        
        for s in s1:
            lengths[s] += 1
        for s in s2:
            lengths[s] += 1
        
        heapq.heappush(heap, [f1 + f2, tie, s1 + s2])
        tie += 1
    
    return lengths

def canonical_codes(lengths: dict) -> dict:
    syms = sorted(lengths.keys(), key = lambda s: (lengths[s], s))
    
    codes = {}
    code = 0
    prev = 0
    
    for s in syms:
        L = lengths[s]
        
        if L > prev:
            code <<= (L - prev)
        
        codes[s] = (code, L)
        code += 1
        prev = L
    
    return codes

def canonical_lookup(lengths: dict) -> tuple:
    syms = sorted(lengths.keys(), key = lambda s: (lengths[s], s))
    lookup = {}
    code = 0
    prev = 0
    max_len = 0
    
    for s in syms:
        L = lengths[s]
        
        if L > prev:
            code <<= (L - prev)
        
        lookup[(code, L)] = s
        code += 1
        prev = L
        max_len = max(max_len, L)
    
    return lookup, max_len

def normalize_freqs(freq_map: dict, n: int) -> list:
    max_f = max(freq_map.values()) if freq_map else 1
    return [max(1, min(255, round(freq_map.get(i, 1) * 255 / max_f))) for i in range(n)]

# ---------------------------
# Elias gamma
# ---------------------------
def elias_length(i: int) -> int:
    n = i + 1
    k = n.bit_length() - 1
    
    return 2 * k + 1

def elias_write(bw: BitWriter, i: int):
    n = i + 1
    k = n.bit_length() - 1
    bw.write_bits(n, 2 * k + 1)

def elias_read(br: BitReader) -> int:
    k = 0
    
    while br.read_bits(1) == 0:
        k += 1
    
    if k == 0:
        return 0
    
    return ((1 << k) | br.read_bits(k)) - 1

# ---------------------------
# Encoding modules
# ---------------------------
def _uniform_lengths(count: int) -> dict:
    bits = needed_bits(count)
    return {i: bits for i in range(count)}

def _huffman_freq_lengths(freqs: dict, count: int) -> dict:
    if count == 0:
        return {}
    
    return huffman_lengths(dict(enumerate(normalize_freqs(freqs, count))))

def _huffman_len_lengths(freqs: dict, count: int) -> dict:
    return huffman_lengths({i: freqs.get(i, 1) for i in range(count)})

def _fixed_write_symbol(bw: BitWriter, sym_id: int, codes: dict, fixed_bits: int):
    bw.write_bits(sym_id, fixed_bits)

def _fixed_read_symbol(br: BitReader, decoder: dict) -> int:
    return br.read_bits(decoder['bits'])

def _fixed_decoder_from_lengths(lengths: dict, count: int) -> dict:
    return {'bits': needed_bits(count)}

def _positional_write_symbol(bw: BitWriter, sym_id: int, codes: dict, fixed_bits: int):
    elias_write(bw, sym_id)

def _positional_read_symbol(br: BitReader, decoder: dict) -> int:
    return elias_read(br)

def _positional_decoder_from_lengths(lengths: dict, count: int) -> dict:
    return {}

def _no_codes(lengths: dict) -> dict:
    return {}

def _no_overhead_write(bw: BitWriter, freqs: dict, count: int):
    pass

def _no_overhead_read(br: BitReader, count: int) -> dict:
    return {}

def _no_overhead_bits(count: int) -> int:
    return 0

_DIRECT_BASE = {
    'write_overhead': _no_overhead_write,
    'read_overhead': _no_overhead_read,
    'overhead_bits': _no_overhead_bits,
}

def _huffman_write_symbol(bw: BitWriter, sym_id: int, codes: dict, fixed_bits: int):
    val, length = codes[sym_id]
    bw.write_bits(val, length)

def _huffman_read_symbol(br: BitReader, decoder: dict) -> int:
    lookup, max_len = decoder['lookup'], decoder['max_len']
    cur = 0
    
    for L in range(1, max_len + 1):
        cur = (cur << 1) | br.read_bits(1)
        
        if (cur, L) in lookup:
            return lookup[(cur, L)]
    
    raise ValueError("Codice Huffman non valido")

def _huffman_encode_codes(lengths: dict) -> dict:
    return canonical_codes(lengths)

def _huffman_decoder_from_lengths(lengths: dict, count: int) -> dict:
    lookup, max_len = canonical_lookup(lengths)
    return {'lookup': lookup, 'max_len': max_len}

_HUFFMAN_BASE = {
    'write_symbol': _huffman_write_symbol,
    'read_symbol': _huffman_read_symbol,
    'encode_codes_from_lengths': _huffman_encode_codes,
    'decoder_from_lengths': _huffman_decoder_from_lengths,
}

def _huffman_freq_write_overhead(bw: BitWriter, freqs: dict, count: int):
    norm = normalize_freqs(dict(freqs), count)
    bw.write_bytes_aligned(bytes(norm))

def _huffman_freq_read_overhead(br: BitReader, count: int) -> dict:
    freq_bytes = br.read_bytes_aligned(count)
    norm = {i: freq_bytes[i] for i in range(count)}
    return huffman_lengths(norm)

def _huffman_freq_overhead_bits(count: int) -> int:
    return count * 8

def _huffman_len_write_overhead(bw: BitWriter, freqs: dict, count: int):
    bw.flush_to_byte()
    
    lens = _huffman_len_lengths(freqs, count) if count > 0 else {}
    for i in range(count):
        bw.write_bits(lens.get(i, 1), 4)
    
    bw.flush_to_byte()

def _huffman_len_read_overhead(br: BitReader, count: int) -> dict:
    br.align_to_byte()
    lens = {i: br.read_bits(4) for i in range(count)}
    br.align_to_byte()
    
    return lens

def _huffman_len_overhead_bits(count: int) -> int:
    return math.ceil(count * 4 / 8) * 8

FIXED_CODEC = {
    **_DIRECT_BASE,
    'char_lengths': lambda alphabet, char_freqs: _uniform_lengths(len(alphabet)),
    'token_lengths': lambda tok_freqs, D: _uniform_lengths(D),
    'write_symbol': _fixed_write_symbol,
    'read_symbol': _fixed_read_symbol,
    'encode_codes_from_lengths': _no_codes,
    'decoder_from_lengths': _fixed_decoder_from_lengths,
}

POSITIONAL_CODEC = {
    **_DIRECT_BASE,
    'char_lengths': lambda alphabet, char_freqs: {i: elias_length(i) for i in range(len(alphabet))},
    'token_lengths': lambda tok_freqs, D: {
        tok_id: elias_length(rank)
        for rank, tok_id in enumerate(sorted(range(D), key = lambda i: tok_freqs.get(i, 0), reverse = True))
    } if D > 0 else {},
    'write_symbol': _positional_write_symbol,
    'read_symbol': _positional_read_symbol,
    'encode_codes_from_lengths': _no_codes,
    'decoder_from_lengths': _positional_decoder_from_lengths,
}

HUFFMAN_FREQ_CODEC = {
    **_HUFFMAN_BASE,
    'char_lengths': lambda alphabet, char_freqs: _huffman_freq_lengths(char_freqs, len(alphabet)),
    'token_lengths': lambda tok_freqs, D: _huffman_freq_lengths(dict(tok_freqs), D),
    'write_overhead': _huffman_freq_write_overhead,
    'read_overhead': _huffman_freq_read_overhead,
    'overhead_bits': _huffman_freq_overhead_bits,
}

HUFFMAN_LEN_CODEC = {
    **_HUFFMAN_BASE,
    'char_lengths': lambda alphabet, char_freqs: _huffman_len_lengths(char_freqs, len(alphabet)),
    'token_lengths': lambda tok_freqs, D: _huffman_len_lengths(dict(tok_freqs), D),
    'write_overhead': _huffman_len_write_overhead,
    'read_overhead': _huffman_len_read_overhead,
    'overhead_bits': _huffman_len_overhead_bits,
}

CODECS = {
    ENC_FIXED: FIXED_CODEC,
    ENC_HUFF_FREQ: HUFFMAN_FREQ_CODEC,
    ENC_HUFF_LEN: HUFFMAN_LEN_CODEC,
    ENC_POSITIONAL: POSITIONAL_CODEC,
}

# ---------------------------
# Symbols
# ---------------------------
def write_sym(bw: BitWriter, sym_id: int, encoding: int, codes: dict, fixed_bits: int):
    CODECS[encoding]['write_symbol'](bw, sym_id, codes, fixed_bits)

def read_sym(br: BitReader, encoding: int, decoder: dict) -> int:
    return CODECS[encoding]['read_symbol'](br, decoder)

def compute_char_bit_lengths(alphabet: bytes, char_freqs: dict, encoding: int) -> dict:
    lengths_by_id = CODECS[encoding]['char_lengths'](alphabet, char_freqs)
    return {alphabet[i]: lengths_by_id[i] for i in range(len(alphabet))}

# ---------------------------
# I/O
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

def build_alphabet(byte_strings: list, sort_by_freq: bool = False) -> tuple:
    freq = defaultdict(int)
    
    for bs in byte_strings:
        for bv in bs:
            freq[bv] += 1
    
    srt = (sorted(freq, key = lambda bv: freq[bv], reverse = True) if sort_by_freq else sorted(freq))
    alph = bytes(srt)
    inv = {alph[i]: i for i in range(len(alph))}
    
    return alph, inv, needed_bits(len(alph)), freq

# ---------------------------
# Alphabet
# ---------------------------
def write_alphabet_section(bw: BitWriter, alphabet: bytes, char_freqs: dict, encoding: int):
    A = len(alphabet)
    
    bw.write_bytes_aligned(uvarint_encode(A))
    bw.write_bytes_aligned(alphabet)
    
    CODECS[encoding]['write_overhead'](bw, char_freqs, A)

def read_alphabet_section(data: bytes, pos: int, encoding: int) -> tuple:
    A, pos = uvarint_decode(data, pos)
    alphabet = data[pos : pos + A]
    pos += A
    
    if A == 0:
        alphabet = b"\x00"
        A = 1
    
    codec = CODECS[encoding]
    br_tmp = BitReader(data, pos)
    lengths = codec['read_overhead'](br_tmp, A)
    pos = br_tmp.pos
    
    decoder = codec['decoder_from_lengths'](lengths, A)
    
    return alphabet, decoder, pos

# ---------------------------
# Dictionary
# ---------------------------
def write_dictionary_section(bw: BitWriter, dictionary: list, byte_to_id: dict, tok_freqs: dict, char_codes: dict, char_bits: int, encoding: int):
    D = len(dictionary)
    bw.write_bytes_aligned(uvarint_encode(D))
    
    for entry in dictionary:
        bw.write_bytes_aligned(uvarint_encode(len(entry)))
        
        for b in entry:
            write_sym(bw, byte_to_id[b], encoding, char_codes, char_bits)
    
    CODECS[encoding]['write_overhead'](bw, tok_freqs, D)

def read_dictionary_section(br: BitReader, alphabet: bytes, char_decoder: dict, encoding: int, num_entries: int) -> tuple:
    dictionary = []
    
    for _ in range(num_entries):
        br.align_to_byte()
        L, br.pos = uvarint_decode(br.data, br.pos)
        
        entry = bytearray()
        for _ in range(L):
            cid = read_sym(br, encoding, char_decoder)
            entry.append(alphabet[cid])
        
        dictionary.append(bytes(entry))
    
    codec = CODECS[encoding]
    br.align_to_byte()
    lengths = codec['read_overhead'](br, num_entries)
    tok_decoder = codec['decoder_from_lengths'](lengths, num_entries)
    
    return dictionary, tok_decoder

# ---------------------------
# Stream
# ---------------------------
def write_stream(bw: BitWriter, seqs: list, byte_to_id: dict, char_codes: dict, char_bits: int, tok_codes: dict, token_bits: int, encoding: int):
    bw.write_bytes_aligned(uvarint_encode(len(seqs)))
    
    for seq in seqs:
        bw.write_bytes_aligned(uvarint_encode(len(seq)))
        
        for typ, val in seq:
            if typ == RAW:
                bw.write_bits(0, 1)
                write_sym(bw, byte_to_id[val], encoding, char_codes, char_bits)
            else:
                bw.write_bits(1, 1)
                write_sym(bw, val, encoding, tok_codes, token_bits)

def read_stream(br: BitReader, alphabet: bytes, dictionary: list, encoding: int, char_decoder: dict, tok_decoder: dict) -> list:
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
                cid = read_sym(br, encoding, char_decoder)
                out.append(alphabet[cid])
            else:
                tid = read_sym(br, encoding, tok_decoder)
                out.extend(dictionary[tid])
        
        out_strings.append(out.decode("utf-8"))
    
    return out_strings

# ---------------------------
# Scoring
# ---------------------------
def count_tok_freqs(seqs: list) -> dict:
    tok_freqs = defaultdict(int)
    
    for seq in seqs:
        for typ, val in seq:
            if typ == TOK:
                tok_freqs[val] += 1
    
    return tok_freqs

def score_dictionary_bits(dictionary: list, seqs: list, char_bit_lengths: dict, encoding: int) -> int:
    D = len(dictionary)
    codec = CODECS[encoding]
    
    tok_bits = codec['token_lengths'](count_tok_freqs(seqs), D)
    
    dict_bits = codec['overhead_bits'](D)
    for entry in dictionary:
        dict_bits += varint_size(len(entry)) * 8
        dict_bits += sum(char_bit_lengths[b] for b in entry)
    
    stream_bits = 0
    for seq in seqs:
        stream_bits += varint_size(len(seq)) * 8
        
        for typ, val in seq:
            stream_bits += 1
            stream_bits += char_bit_lengths[val] if typ == RAW else tok_bits[val]
    
    return dict_bits + stream_bits

# ---------------------------
# Dictionary build
# ---------------------------
def initial_sequences(byte_strings: list) -> list:
    return [[(RAW, x) for x in bs] for bs in byte_strings]

def find_candidates(seqs: list, min_len: int = 2, max_len: int = 32) -> dict:
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

def count_non_overlapping(seq: list, pat_bytes: bytes) -> int:
    pat = [(RAW, b) for b in pat_bytes]
    m = len(pat)
    i = 0
    c = 0
    
    while i <= len(seq) - m:
        if seq[i : i + m] == pat:
            c += 1
            i += m
        else:
            i += 1
    
    return c

def total_non_overlapping(seqs: list, pat_bytes: bytes) -> int:
    return sum(count_non_overlapping(seq, pat_bytes) for seq in seqs)

def replace_non_overlapping(seqs: list, pat_bytes: bytes, token_id: int) -> list:
    pat = [(RAW, b) for b in pat_bytes]
    m = len(pat)
    token = (TOK, token_id)
    
    out_all = []
    
    for seq in seqs:
        out = []
        i   = 0
        
        while i < len(seq):
            if i <= len(seq) - m and seq[i : i + m] == pat:
                out.append(token)
                i += m
            else:
                out.append(seq[i])
                i += 1
        
        out_all.append(out)
    
    return out_all

def token_bits_for_candidate(codec: dict, tok_freqs: dict, d: int, occ: int) -> int:
    combined = dict(tok_freqs)
    combined[d] = occ
    
    return codec['token_lengths'](combined, d + 1)[d]

def scoring_function(pat_bytes: bytes, occ: int, char_bit_lengths: dict, token_bits_after: int) -> float:
    L = len(pat_bytes)
    pat_bits = sum(char_bit_lengths[b] for b in pat_bytes)
    
    old_cost = occ * (L + pat_bits)
    new_cost = occ * (1 + token_bits_after)
    dict_cost = (varint_size(L) * 8) + pat_bits
    
    return old_cost - new_cost - dict_cost

def greedy_build(byte_strings: list, char_bit_lengths: dict, encoding: int, min_len: int = 2, max_len: int = 32, max_dict: int = 1023, init_dict: list | None = None, init_seqs: list | None = None) -> tuple:
    seqs = init_seqs[:] if init_seqs is not None  else initial_sequences(byte_strings)
    dictionary = list(init_dict) if init_dict is not None  else []
    codec = CODECS[encoding]
    
    current_bits = score_dictionary_bits(dictionary, seqs, char_bit_lengths, encoding)
    
    while len(dictionary) < max_dict:
        D = len(dictionary)
        tok_freqs = count_tok_freqs(seqs)
        candidates = find_candidates(seqs, min_len, max_len)
        
        best = None
        best_gain = 0
        
        for pat in candidates:
            occ  = total_non_overlapping(seqs, pat)
            if occ < 2:
                continue
            
            token_bits_after = token_bits_for_candidate(codec, tok_freqs, D, occ)
            gain = scoring_function(pat, occ, char_bit_lengths, token_bits_after)
            
            if gain > best_gain:
                best_gain = gain
                best = pat
        
        if best is None or best_gain <= 0:
            break
        
        trial_dict = dictionary + [best]
        trial_seqs = replace_non_overlapping(seqs, best, D)
        trial_bits = score_dictionary_bits(trial_dict, trial_seqs, char_bit_lengths, encoding)
        
        if trial_bits >= current_bits:
            break
        
        dictionary = trial_dict
        seqs = trial_seqs
        current_bits = trial_bits
    
    return dictionary, seqs

def build_dictionary_restricted(byte_strings: list, char_bit_lengths: dict, encoding: int, min_len: int = 2, max_len: int = 32, max_dict: int = 1023, lookahead_depth: int = 0, lookahead_topk: int = 1) -> tuple:
    if lookahead_depth <= 0 and lookahead_topk <= 1:
        return greedy_build(byte_strings, char_bit_lengths, encoding, min_len, max_len, max_dict)
    
    codec = CODECS[encoding]
    init_seqs = initial_sequences(byte_strings)
    
    states = [([], init_seqs)]
    
    for _ in range(lookahead_depth):
        new_states = []
        
        for dict_so_far, seqs_so_far in states:
            D = len(dict_so_far)
            
            if D >= max_dict:
                new_states.append((dict_so_far, seqs_so_far))
                continue
            
            tok_freqs = count_tok_freqs(seqs_so_far)
            candidates = find_candidates(seqs_so_far, min_len, max_len)
            
            scored = []
            for pat in candidates:
                occ = total_non_overlapping(seqs_so_far, pat)
                if occ < 2:
                    continue
                
                token_bits_after = token_bits_for_candidate(codec, tok_freqs, D, occ)
                gain = scoring_function(pat, occ, char_bit_lengths, token_bits_after)
                
                if gain > 0:
                    scored.append((gain, pat))
            
            if not scored:
                new_states.append((dict_so_far, seqs_so_far))
                continue
            
            scored.sort(key = lambda x: x[0], reverse = True)
            
            for _, pat in scored[:lookahead_topk]:
                new_dct = list(dict_so_far) + [pat]
                new_sqs = replace_non_overlapping(seqs_so_far, pat, D)
                new_states.append((new_dct, new_sqs))
        
        states = new_states
    
    best_score = None
    best = None
    
    for dct, sqs in states:
        dct2, sqs2 = greedy_build(byte_strings, char_bit_lengths, encoding, min_len, max_len, max_dict, dct, sqs)
        bits = score_dictionary_bits(dct2, sqs2, char_bit_lengths, encoding)
        
        if best_score is None or bits < best_score:
            best_score = bits
            best = (dct2, sqs2)
    
    if best is None:
        return [], init_seqs
    
    return best

def _reorder_dict_for_positional(dictionary: list, seqs: list) -> tuple:
    D = len(dictionary)
    tok_freqs = count_tok_freqs(seqs)
    
    old_order = sorted(range(D), key = lambda i: tok_freqs.get(i, 0), reverse = True)
    new_dict = [dictionary[i] for i in old_order]
    old_to_new = {old: new for new, old in enumerate(old_order)}
    new_seqs = [[(TOK, old_to_new[v]) if t == TOK else (RAW, v) for t, v in seq] for seq in seqs]
    
    return new_dict, new_seqs, count_tok_freqs(new_seqs)

# ---------------------------
# Encode / Decode
# ---------------------------
def encode_onefile(input_txt: str, output_bin: str, min_len: int = 2, max_len: int = 32, max_dict: int = 1023, lookahead_depth: int = 0, lookahead_topk: int = 1, encoding_name: str = 'fixed'):
    t_start  = time.time()
    encoding = ENC_NAME.get(encoding_name, ENC_FIXED)
    
    strings = read_strings_text(input_txt)
    byte_strings = to_utf8_bytes(strings)
    
    sort_by_freq = (encoding == ENC_POSITIONAL)
    alphabet, byte_to_id, char_bits, raw_freq = build_alphabet(byte_strings, sort_by_freq)
    char_freqs = {byte_to_id[bv]: cnt for bv, cnt in raw_freq.items()}
    char_bit_lengths = compute_char_bit_lengths(alphabet, char_freqs, encoding)
    
    dictionary, seqs = build_dictionary_restricted(byte_strings, char_bit_lengths, encoding, min_len, max_len, max_dict, lookahead_depth, lookahead_topk)
    
    D = len(dictionary)
    token_bits = needed_bits(D)
    
    tok_freqs = defaultdict(int)
    
    if encoding == ENC_POSITIONAL:
        dictionary, seqs, tok_freqs = _reorder_dict_for_positional(dictionary, seqs)
    else:
        for seq in seqs:
            for typ, val in seq:
                if typ == TOK:
                    tok_freqs[val] += 1
    
    codec = CODECS[encoding]
    
    char_lengths_by_id = codec['char_lengths'](alphabet, char_freqs)
    char_codes = codec['encode_codes_from_lengths'](char_lengths_by_id)
    
    tok_lengths_by_id = codec['token_lengths'](tok_freqs, D)
    tok_codes = codec['encode_codes_from_lengths'](tok_lengths_by_id)
    
    bw = BitWriter()
    bw.write_bytes_aligned(MAGIC)
    bw.write_bytes_aligned(bytes([VERSION, encoding]))

    write_alphabet_section(bw, alphabet, char_freqs, encoding)
    write_dictionary_section(bw, dictionary, byte_to_id, tok_freqs, char_codes, char_bits, encoding)
    
    write_stream(bw, seqs, byte_to_id, char_codes, char_bits, tok_codes, token_bits, encoding)
    
    data = bw.getvalue()
    
    output_dir = os.path.join("..", "outputs")
    os.makedirs(output_dir, exist_ok = True)
    full_output_path = os.path.join(output_dir, output_bin)
    
    with open(full_output_path, "wb") as f:
        f.write(data)
    
    orig_bytes = sum(len(b) for b in byte_strings)
    dict_bytes = sum(len(e) for e in dictionary)
    t_elapsed = time.time() - t_start
    
    logging.info(f"OK: scritto {output_bin}")
    logging.info(f"Stringhe: {len(strings)}")
    logging.info(f"Originale (UTF-8 bytes): {orig_bytes}")
    logging.info(f"Alfabeto A = {len(alphabet)} => char_bits = {char_bits}")
    logging.info(f"Dizionario D = {D} => token_bits = {token_bits}, bytes_dizionario_raw = {dict_bytes}")
    logging.info(f"Output totale (bytes): {len(data)}")
    logging.info(f"Tempo: {t_elapsed:.2f} s")

def decompress_onefile(path_bin: str) -> list:
    full_path = os.path.join("..", "outputs", path_bin)
    
    with open(full_path, "rb") as f:
        data = f.read()
    
    pos = 0
    
    if data[pos : pos+4] != MAGIC:
        raise ValueError("MAGIC non valido")
    
    pos += 4
    ver = data[pos]
    pos += 1
    encoding = data[pos]
    pos += 1
    
    if ver != VERSION:
        raise ValueError(f"Versione non supportata: {ver}")
    
    alphabet, char_decoder, pos = read_alphabet_section(data, pos, encoding)
    D, pos = uvarint_decode(data, pos)
    
    br = BitReader(data, pos)
    dictionary, tok_decoder = read_dictionary_section(br, alphabet, char_decoder, encoding, D)
    
    return read_stream(br, alphabet, dictionary, encoding, char_decoder, tok_decoder)

# ---------------------------
# CLI
# ---------------------------
def main():
    ap = argparse.ArgumentParser(description = "SDB1: beam search + encoding variabile")
    
    ap.add_argument("mode", choices = ["compress", "decompress"])
    ap.add_argument("input")
    ap.add_argument("output", nargs = "?")
    ap.add_argument("--min-len", type = int, default = 2)
    ap.add_argument("--max-len", type = int, default = 32)
    ap.add_argument("--max-dict", type = int, default = 1023)
    ap.add_argument("--lookahead-depth", type = int, default = 0, help = "Profondità beam (0 = greedy)")
    ap.add_argument("--lookahead-topk", type = int, default = 1, help = "Candidati per nodo (1 = greedy)")
    ap.add_argument("--encoding", default = 'fixed', choices = ['fixed', 'huffman-freq', 'huffman-len', 'positional'], help = "Modalità codifica simboli (default: fixed)")
    
    args = ap.parse_args()
    
    setup_logger(args.input)
    
    if args.mode == "compress":
        out = args.output or f"c2_exhaustive_restricted_{args.input.split('.')[0]}_compressed.bin"
        encode_onefile(args.input, out, args.min_len, args.max_len, args.max_dict, args.lookahead_depth, args.lookahead_topk, args.encoding)
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