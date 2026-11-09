#!/usr/bin/env python3
# exhaustive combinations

import argparse
import ast
import math
import heapq
import re
import time
import logging
import os
import itertools
from datetime import datetime
from collections import defaultdict
from pathlib import Path

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

def needed_bits(n: int) -> int:
    return 1 if n <= 1 else math.ceil(math.log2(n))

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
# Huffman
# ---------------------------

# huffman code length of every symbol (only lengths: actual codes are built canonically from them).
def huffman_lengths(freq_map: dict) -> dict:
    if not freq_map:
        return {}
    
    if len(freq_map) == 1:
        return {next(iter(freq_map)): 1}
    
    # [freq, tie, symbols]: 'tie' makes the merge order deterministic, so encoder and decoder agree
    heap = [[f, i, [s]] for i, (s, f) in enumerate(sorted(freq_map.items()))]
    lengths = dict.fromkeys(freq_map, 0)
    tie = len(heap)
    heapq.heapify(heap)
    
    while len(heap) > 1:
        f1, _, s1 = heapq.heappop(heap)
        f2, _, s2 = heapq.heappop(heap)
        
        # every symbol of the two merged nodes moves one level deeper
        for s in s1:
            lengths[s] += 1
        for s in s2:
            lengths[s] += 1
        
        heapq.heappush(heap, [f1 + f2, tie, s1 + s2])
        tie += 1
    
    return lengths

# canonical Huffman codes {symbol: (code, length)}: fully determined by the lengths.
def canonical_codes(lengths: dict) -> dict:
    syms = sorted(lengths.keys(), key = lambda s: (lengths[s], s))
    codes = {}
    code = 0
    prev = 0
    
    for s in syms:
        L = lengths[s]
        
        # longer codes: shift left, so no shorter code is a prefix of a longer one
        if L > prev:
            code <<= (L - prev)
        
        codes[s] = (code, L)
        code += 1
        prev = L
    
    return codes

# decoder side of canonical_codes: {(code, length): symbol} and the maximum code length.
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

# scales frequencies to 1..255.
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

# huffman lengths computed on the normalized frequencies: the decoder only sees those, so it rebuilds the same tree.
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
        for rank, tok_id in enumerate(
            sorted(range(D), key = lambda i: tok_freqs.get(i, 0), reverse = True)
        )
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

# every encoding exposes the same interface, so the search and the writer never branch on the encoding.
# search side: char_lengths, token_lengths. Writer side: encode_codes_from_lengths, write_symbol, write_overhead.
# Decoder side: decoder_from_lengths, read_symbol, read_overhead.
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

# bit length of every byte under the chosen encoding, keyed by byte value (used by all cost functions).
def compute_char_bit_lengths(alphabet: bytes, char_freqs: dict, encoding: int) -> dict:
    lengths_by_id = CODECS[encoding]['char_lengths'](alphabet, char_freqs)
    return {alphabet[i]: lengths_by_id[i] for i in range(len(alphabet))}

# ---------------------------
# I/O strings
# ---------------------------

# reads one string per line
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

# builds the alphabet (distinct bytes), the byte -> id map, the fixed code width and the byte frequencies.
def build_alphabet(byte_strings: list, sort_by_freq: bool = False) -> tuple:
    freq = defaultdict(int)
    
    for bs in byte_strings:
        for bv in bs:
            freq[bv] += 1
    
    # positional: ids follow decreasing frequency, so the id is the rank used by Elias gamma
    srt = (sorted(freq, key = lambda bv: freq[bv], reverse = True) if sort_by_freq else sorted(freq))
    alph = bytes(srt)
    inv = {alph[i]: i for i in range(len(alph))}
    
    return alph, inv, needed_bits(len(alph)), freq

# ---------------------------
# Alphabet
# ---------------------------
def write_alphabet_section(bw: BitWriter, alphabet: bytes, char_freqs: dict, encoding: int):
    A = len(alphabet)
    
    exp_write(bw, A)
    bw.write_bytes_aligned(alphabet)
    
    CODECS[encoding]['write_overhead'](bw, char_freqs, A)

def read_alphabet_section(br: BitReader, encoding: int) -> tuple:
    A = exp_read(br)
    alphabet = br.read_bytes_aligned(A)
    
    if A == 0:
        alphabet = b"\x00"
        A = 1
    
    codec = CODECS[encoding]
    lengths = codec['read_overhead'](br, A)
    decoder = codec['decoder_from_lengths'](lengths, A)
    
    return alphabet, decoder

# ---------------------------
# Dictionary
# ---------------------------
def write_dictionary_section(bw: BitWriter, dictionary: list, byte_to_id: dict, tok_freqs: dict, char_codes: dict, char_bits: int, encoding: int):
    D = len(dictionary)
    exp_write(bw, D)
    
    for entry in dictionary:
        exp_write(bw, len(entry))
        
        for b in entry:
            write_sym(bw, byte_to_id[b], encoding, char_codes, char_bits)
    
    CODECS[encoding]['write_overhead'](bw, tok_freqs, D)

def read_dictionary_section(br: BitReader, alphabet: bytes, char_decoder: dict, encoding: int, num_entries: int) -> tuple:
    dictionary = []
    
    for _ in range(num_entries):
        L = exp_read(br)
        
        entry = bytearray()
        for _ in range(L):
            cid = read_sym(br, encoding, char_decoder)
            entry.append(alphabet[cid])
        
        dictionary.append(bytes(entry))
    
    codec = CODECS[encoding]
    lengths = codec['read_overhead'](br, num_entries)
    tok_decoder = codec['decoder_from_lengths'](lengths, num_entries)
    
    return dictionary, tok_decoder

# ---------------------------
# Stream
# ---------------------------
def write_stream(bw: BitWriter, seqs: list, byte_to_id: dict, char_codes: dict, char_bits: int, tok_codes: dict, token_bits: int, encoding: int):
    exp_write(bw, len(seqs))
    
    for seq in seqs:
        exp_write(bw, len(seq))
        
        for typ, val in seq:
            if typ == RAW:
                bw.write_bits(0, 1)
                write_sym(bw, byte_to_id[val], encoding, char_codes, char_bits)
            else:
                bw.write_bits(1, 1)
                write_sym(bw, val, encoding, tok_codes, token_bits)

def read_stream(br: BitReader, alphabet: bytes, dictionary: list, encoding: int, char_decoder: dict, tok_decoder: dict) -> list:
    N = exp_read(br)
    
    out_strings = []
    
    for _ in range(N):
        S = exp_read(br)
        
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
# String split (separators)
# ---------------------------

# a byte is a separator if all its predecessors are distinct and all its successors are distinct.
# strings are split on separators (fewer partitions to enumerate); returns the pieces and the separator counts.
def split_strings(strings: list[bytes]) -> tuple[list[bytes], dict[bytes, int]]:
    char_map = {}
    
    for s in strings:
        for i in range(len(s)):
            char = s[i : i + 1]
            
            if char not in char_map:
                char_map[char] = {'pre': [], 'post': [], 'count': 0}
            
            char_map[char]['count'] += 1
            
            if i > 0:
                char_map[char]['pre'].append(s[i - 1])
            if i < len(s) - 1:
                char_map[char]['post'].append(s[i + 1])
    
    separators = []
    initial_dict = {}
    
    for char, data in char_map.items():
        pre_unique  = len(set(data['pre']))  == len(data['pre'])
        post_unique = len(set(data['post'])) == len(data['post'])
        
        if pre_unique and post_unique:
            separators.append(char)
            initial_dict[char] = data['count']
    
    if not separators:
        return strings, {}
    
    regex = b'|'.join(map(re.escape, separators))
    new_strings = []
    
    for s in strings:
        for p in re.split(regex, s):
            if p:
                new_strings.append(p)
    
    return new_strings, initial_dict

# ---------------------------
# Partitions
# ---------------------------

# all the 2^(n-1) ways to cut s into contiguous fragments: bit j of mask = cut after byte j.
def get_partitions(s: bytes) -> list:
    n = len(s)
    partitions = []
    
    for mask in range(1 << (n - 1)):
        partition = []
        start = 0
        
        for j in range(n - 1):
            if (mask >> j) & 1:
                partition.append(s[start : j+1])
                start = j + 1
        
        partition.append(s[start:])
        partitions.append(partition)
    
    return partitions

# ---------------------------
# Scoring
# ---------------------------

# occurrences of every token id in the strings (input of the token code lengths).
def count_tok_freqs(seqs: list) -> dict:
    tok_freqs = defaultdict(int)
    
    for seq in seqs:
        for typ, val in seq:
            if typ == TOK:
                tok_freqs[val] += 1
    
    return tok_freqs

# estimated gain in bits of turning the occ occurrences of a fragment into a token
# (bytes and their control bits saved, minus the token codes and the dictionary entry).
def scoring_function(pat_bytes: bytes, occ: int, char_bit_lengths: dict, token_bits_after: int) -> float:
    L = len(pat_bytes)
    pat_bits = sum(char_bit_lengths[b] for b in pat_bytes)
    
    old_cost = occ * (L + pat_bits)
    new_cost = occ * (1 + token_bits_after)
    dict_cost = exp_size(L) + pat_bits
    
    return old_cost - new_cost - dict_cost

# ---------------------------
# Dictionary build (exhaustive over partitions)
# ---------------------------

# exhaustive search: tries every combination of one partition per string. Every distinct fragment of the combination
# becomes a dictionary entry (after the initial separators, if any); the combination with the highest total
# estimated gain wins.
def build_dictionary(byte_strings: list, char_bit_lengths: dict, encoding: int, init_dict: list | None = None, init_freqs: dict | None = None) -> list | None:
    codec = CODECS[encoding]
    base_dict = list(init_dict)  if init_dict  else []
    base_freqs = dict(init_freqs) if init_freqs else {}
    base_set = set(base_dict)
    
    all_partitions = [get_partitions(s) for s in byte_strings]
    
    n_combinations = 1
    for parts in all_partitions:
        n_combinations *= len(parts)
    
    logging.info(f"Strings: {len(byte_strings)}, combinations: {n_combinations:,}")
    
    best_score = None
    best_combination = None
    
    for combination in itertools.product(*all_partitions):
        all_fragments = []
        for partition in combination:
            all_fragments.extend(partition)
        
        # accumulation of frequencies and estimation of token costs
        frag_counts = defaultdict(int)
        for frag in all_fragments:
            if frag not in base_set:
                frag_counts[frag] += 1
        
        frags = list(frag_counts.keys())
        total_size = len(base_dict) + len(frags)
        
        pool_freqs = {}
        
        for i, sep in enumerate(base_dict):
            pool_freqs[i] = base_freqs.get(sep, 1)
        
        for j, frag in enumerate(frags):
            pool_freqs[len(base_dict) + j] = frag_counts[frag]
        
        tok_bits_by_id = codec['token_lengths'](pool_freqs, total_size)
        
        # evaluation via the gain function
        score = sum(
            scoring_function(frags[j], frag_counts[frags[j]], char_bit_lengths, tok_bits_by_id[len(base_dict) + j])
            for j in range(len(frags))
        )
        
        if best_score is None or score > best_score:
            best_score = score
            best_combination = all_fragments
    
    # extraction of the final dictionary
    if best_combination is None:
        return base_dict if base_dict else None
    
    final_counts = defaultdict(int)
    for frag in best_combination:
        if frag not in base_set:
            final_counts[frag] += 1
    
    return base_dict + list(final_counts.keys())

# ---------------------------
# Tokenization
# ---------------------------

# longest match: at every position the longest dictionary entry that matches becomes a token, otherwise a RAW byte.
def _tokenize(s: bytes, dictionary: list) -> list:
    seq = []
    i = 0
    
    while i < len(s):
        best_len = 0
        best_id  = -1
        
        for tok_id, frag in enumerate(dictionary):
            L = len(frag)
            
            if s[i : i + L] == frag and L > best_len:
                best_len = L
                best_id = tok_id
        
        if best_id >= 0:
            seq.append((TOK, best_id))
            i += best_len
        else:
            seq.append((RAW, s[i]))
            i += 1
    
    return seq

# sequences of the original strings. Separators in the dictionary: plain tokenization of the whole strings.
# separators as RAW: they are written as RAW bytes and only the pieces between them are tokenized.
def _rebuild_original_seqs(byte_strings: list, subseqs: list, sep_freqs: dict, dictionary: list, sep_in_dict: bool) -> list:
    separators = list(sep_freqs.keys())
    
    if not separators or sep_in_dict:
        return [_tokenize(s, dictionary) for s in byte_strings]
    
    seqs = []
    subseq_iter = iter(subseqs)
    
    for orig in byte_strings:
        seq = []
        i = 0
        current_subseq_bytes = bytearray()
        
        while i < len(orig):
            matched_sep = None
            
            for sep in separators:
                if orig[i : i + len(sep)] == sep:
                    matched_sep = sep
                    break
            
            if matched_sep is not None:
                if current_subseq_bytes:
                    sub = next(subseq_iter)
                    seq.extend(_tokenize(sub, dictionary))
                    current_subseq_bytes = bytearray()
                
                for bv in matched_sep:
                    seq.append((RAW, bv))
                
                i += len(matched_sep)
            else:
                current_subseq_bytes.append(orig[i])
                i += 1
        
        if current_subseq_bytes:
            sub = next(subseq_iter)
            seq.extend(_tokenize(sub, dictionary))
        
        seqs.append(seq)
    
    return seqs

# positional: renumbers the tokens by decreasing frequency, so the id written in the stream is its rank
# (the most frequent token gets id 0, the shortest elias gamma code).
# the dictionary is written in the new order, so the decoder rebuilds the same id -> entry mapping.
def _reorder_dict_for_positional(dictionary: list, seqs: list) -> tuple:
    D = len(dictionary)
    tok_freqs = count_tok_freqs(seqs)
    
    # old_order[r] = old id of the token with rank r (stable sort: ties keep their order, the size does not change)
    old_order = sorted(range(D), key = lambda i: tok_freqs.get(i, 0), reverse = True)
    new_dict = [dictionary[i] for i in old_order]
    old_to_new = {old: new for new, old in enumerate(old_order)}
    
    # only token ids change: raw bytes and positions in the stream are untouched
    new_seqs = [[(TOK, old_to_new[v]) if t == TOK else (RAW, v) for t, v in seq] for seq in seqs]
    
    return new_dict, new_seqs, count_tok_freqs(new_seqs)

# ---------------------------
# Encode / Decode
# ---------------------------
def encode_onefile(input_txt: str, output_bin: str, sep_in_dict: bool = True, encoding_name: str = 'fixed'):
    t_start = time.time()
    encoding = ENC_NAME.get(encoding_name, ENC_FIXED)
    
    strings = read_strings_text(input_txt)
    byte_strings = to_utf8_bytes(strings)
    
    subseqs, sep_freqs = split_strings(byte_strings)
    
    sort_by_freq = (encoding == ENC_POSITIONAL)
    all_bytes_for_alpha = list(subseqs) + list(sep_freqs.keys())
    alphabet, byte_to_id, char_bits, raw_freq = build_alphabet(all_bytes_for_alpha, sort_by_freq)
    char_freqs = {byte_to_id[bv]: cnt for bv, cnt in raw_freq.items()}
    # character costs are fixed for the whole search: the alphabet does not depend on the dictionary
    char_bit_lengths = compute_char_bit_lengths(alphabet, char_freqs, encoding)
    
    # separators in the dictionary: they are the first entries, with their counts as frequencies
    if sep_in_dict and sep_freqs:
        init_dict = list(sep_freqs.keys())
        init_freqs = dict(sep_freqs)
    else:
        init_dict = []
        init_freqs = {}
    
    dictionary = build_dictionary(subseqs, char_bit_lengths, encoding, init_dict, init_freqs)
    
    if dictionary is None:
        return
    
    D = len(dictionary)
    token_bits = needed_bits(D)
    
    # the chosen partition is not kept: the strings are tokenized again on the final dictionary
    seqs = _rebuild_original_seqs(byte_strings, subseqs, sep_freqs, dictionary, sep_in_dict)
    tok_freqs = count_tok_freqs(seqs)
    
    # positional: token ids must equal their frequency rank before writing
    if encoding == ENC_POSITIONAL:
        dictionary, seqs, tok_freqs = _reorder_dict_for_positional(dictionary, seqs)
    
    codec = CODECS[encoding]
    
    char_lengths_by_id = codec['char_lengths'](alphabet, char_freqs)
    char_codes = codec['encode_codes_from_lengths'](char_lengths_by_id)
    
    tok_lengths_by_id = codec['token_lengths'](tok_freqs, D)
    tok_codes = codec['encode_codes_from_lengths'](tok_lengths_by_id)
    
    bw = BitWriter()
    bw.write_bytes_aligned(bytes([encoding]))
    
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
    
    logging.info(f"\nOK: scritto {output_bin}")
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
    encoding = data[pos]
    pos += 1

    br = BitReader(data, pos)
    alphabet, char_decoder = read_alphabet_section(br, encoding)
    D = exp_read(br)
    dictionary, tok_decoder = read_dictionary_section(br, alphabet, char_decoder, encoding, D)
    
    return read_stream(br, alphabet, dictionary, encoding, char_decoder, tok_decoder)

# ---------------------------
# CLI
# ---------------------------
def main():
    ap = argparse.ArgumentParser(description = "Exhaustive compressor over partitions")
    
    ap.add_argument("mode", choices = ["compress", "decompress"])
    ap.add_argument("input")
    ap.add_argument("output", nargs = "?")
    ap.add_argument("--sep-as-raw", action = "store_true", default = False, help = "Write the separators as RAW instead of in the dictionary")
    ap.add_argument("--encoding", default = 'fixed', choices = ['fixed', 'huffman-freq', 'huffman-len', 'positional'], help = "Symbols encoding modes (default: fixed)")
    
    args = ap.parse_args()
    
    setup_logger(args.input)
    
    sep_in_dict = not args.sep_as_raw
    
    if args.mode == "compress":
        out = args.output or f"exhaustive_{args.input.split('.')[0]}_compressed.bin"
        encode_onefile(args.input, out, sep_in_dict, args.encoding)
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