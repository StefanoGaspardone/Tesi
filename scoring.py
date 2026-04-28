import math
import re
import sys
from collections import Counter

B_FLAG = 1
WORD_REGEX = re.compile(rb"[a-zA-Z0-9_\-]+")

def load_binary_from_input_file() -> bytes:
    """Read an input file and return its raw bytes."""

    try:
        file_name = sys.argv[1] if len(sys.argv) > 1 else input("Enter file name: ")

        with open(f"inputs/{file_name}", "rb") as file:
            return file.read()
    except FileNotFoundError:
        print("The file does not exist")
        sys.exit(1)

def get_partitions(word: bytes) -> list[list[bytes]]:
    """Generate all possible contiguous partitions of a word."""

    partitions: list[list[bytes]] = []
    n = len(word)

    for i in range(2 ** (n - 1)):
        start = 0
        current_partition: list[bytes] = []

        for j in range(n - 1):
            if (i >> j) & 1:
                current_partition.append(word[start : j + 1])
                start = j + 1

        current_partition.append(word[start:])
        partitions.append(current_partition)

    return partitions

def build_data(words: list[bytes]) -> tuple[Counter[bytes], dict[bytes, list[list[bytes]]], dict[bytes, dict[bytes, int]]]:
    """Build needed data structures: frequencies, partitions, and fragment occurrences."""

    word_frequencies: Counter[bytes] = Counter(words)
    all_partitions: dict[bytes, list[list[bytes]]] = {}
    fragment_occurrences: dict[bytes, dict[bytes, int]] = {}

    for word in word_frequencies:
        partitions = get_partitions(word)
        all_partitions[word] = partitions

        possible_fragments = {frag for part in partitions for frag in part}
        fragment_occurrences[word] = {frag: word.count(frag) for frag in possible_fragments}

    return word_frequencies, all_partitions, fragment_occurrences

def aggregate_substring_counts(word_frequencies: Counter[bytes], fragment_occurrences: dict[bytes, dict[bytes, int]],) -> dict[bytes, int]:
    """Aggregate global occurrences for each fragment across all words."""

    substring_counts: dict[bytes, int] = {}

    for word, occ_map in fragment_occurrences.items():
        freq = word_frequencies[word]

        for frag, occ in occ_map.items():
            substring_counts[frag] = substring_counts.get(frag, 0) + (occ * freq)

    return substring_counts

def get_key_bits(n_entries: int) -> int:
    """Return the number of bits needed to address n_entries dictionary items."""

    return math.ceil(math.log2(n_entries)) if n_entries > 0 else 1

def calculate_u_di(fragment: bytes, count: int, b_key: int, b_unit: int) -> int:
    """Compute the bit gain of encoding a fragment with the current key width.
    
    Formula:
    Score = saving - (storage_cost + pointer_cost)
    
    Where:
    - saving: count * (len(fragment) * b_unit) -> Bits saved by not writing the fragment character by character.
    - storage_cost: (len(fragment) * b_unit) + b_unit -> Bits required to store the fragment in the dict + ETX terminator.
    - pointer_cost: count * (B_FLAG + b_key) -> Bits consumed in the text by the key pointing to the dict.
    """    

    l_bits = len(fragment) * b_unit

    saving = count * l_bits
    storage_cost = l_bits + b_unit # B_ETX = b_unit; B_TYPE is now useless, since an optimized encoding for chars is used
    pointer_cost = count * (B_FLAG + b_key)

    return saving - storage_cost - pointer_cost

def get_best_partition(partitions: list[list[bytes]], candidate_scores: dict[bytes, int]) -> list[bytes] | None:
    """Return the partition with the highest score."""

    best_partition = None
    best_score = -1

    for partition in partitions:
            current_score = sum(candidate_scores.get(frag, 0) for frag in partition)
            
            if current_score > best_score:
                best_score = current_score
                best_partition = partition
                
    return best_partition

def create_dict(word_frequencies: Counter[bytes], all_partitions: dict[bytes, list[list[bytes]]], fragment_occurrences: dict[bytes, dict[bytes, int]], b_unit: int) -> dict[bytes, int]:
    """Run the loop to create the final dict, trying to maximize the total saved bits."""

    best_saving = -1
    best_dict = {}
    current_candidates = aggregate_substring_counts(word_frequencies, fragment_occurrences)

    while True:
        b_key = get_key_bits(len(current_candidates))
        
        candidates_score = {
            sub: score
            for sub, occ in current_candidates.items()
            if (score := calculate_u_di(sub, occ, b_key, b_unit)) > 0
        }

        if not candidates_score:
            break

        current_dict = {}
        for word, freq in word_frequencies.items():
            best_part = get_best_partition(all_partitions[word], candidates_score)
            
            if best_part:
                for frag in best_part:
                    if frag in candidates_score:
                        current_dict[frag] = current_dict.get(frag, 0) + freq
                        
        current_key = get_key_bits(len(current_dict))
        current_saving = sum(calculate_u_di(f, occ, get_key_bits(len(current_dict)), b_unit) for f, occ in current_dict.items())
        
        print(f"Saving: {current_saving} | Key bits: {current_key} | Entries: {len(current_dict)}")

        if not current_dict or current_saving < best_saving or (current_saving == best_saving and current_key > b_key) or (current_saving == best_saving and current_key == b_key and len(current_dict) >= len(best_dict)):
            break

        best_saving = current_saving
        best_dict = current_dict
        current_candidates = current_dict

    return best_dict

def print_results(final_dict: dict[bytes, int], total_saving: int, raw_data_len: int, b_unit: int) -> None:
    n_entries = len(final_dict)
    effective_b_key = get_key_bits(n_entries)
    initial_bits_8 = raw_data_len * 8

    rows = [
        (pos, fragment, count, calculate_u_di(fragment, count, effective_b_key, b_unit))
        for pos, (fragment, count) in enumerate(sorted(final_dict.items(), key=lambda item: item[1], reverse=True))
    ]

    pos_width = max(3, len(str(len(rows) - 1)) if rows else 3)
    fragment_width = max(8, max((len(f.decode('utf-8', 'replace')) for _, f, _, _ in rows), default=8))
    uses_width = max(4, max((len(str(c)) for _, _, c, _ in rows), default=4))
    saving_width = max(10, max((len(str(s)) for _, _, _, s in rows), default=10))

    table_width = pos_width + fragment_width + uses_width + saving_width + 13
    border = "+" + "-" * (table_width - 2) + "+"

    print(f"\nFinal Dict Length: {n_entries}")
    print(f"Key bits: {effective_b_key}")
    print(border)
    print(f"| {'Pos':<{pos_width}} | {'Fragment':<{fragment_width}} | {'Uses':<{uses_width}} | {'Saving':<{saving_width}} |")
    print(border)

    for pos, fragment, count, saving in rows:
        display_frag = fragment.decode('utf-8', errors='replace')
        print(f"| {pos:<{pos_width}} | {display_frag:<{fragment_width}} | {count:<{uses_width}} | {saving:<{saving_width}} |")
    print(border)
    
    print(f"\nTotal savings: {total_saving} bit")
    print(f"Total original bits: {initial_bits_8} bits")
    
    perc = (total_saving / initial_bits_8) * 100
    print(f"Compression rate: {perc:.2f}%")
    
def calc_final_saving(raw_data: bytes, final_dict: dict[bytes, int], all_partitions: dict, b_unit: int) -> int:
    n_entries = len(final_dict)
    b_key = get_key_bits(n_entries)
    
    total_bits_payload = 0
    current_lit_accumulated = b""
    last_idx = 0
    candidates_score = dict.fromkeys(final_dict, 1)

    for match in WORD_REGEX.finditer(raw_data):
        start, end = match.start(), match.end()
        word = match.group()
        
        if start > last_idx:
            current_lit_accumulated += raw_data[last_idx:start]
        
        best_part = get_best_partition(all_partitions.get(word, []), candidates_score)
        
        if best_part:
            for frag in best_part:
                if frag in final_dict:
                    if current_lit_accumulated:
                        total_bits_payload += 1 + (len(current_lit_accumulated) * b_unit) + b_unit
                        current_lit_accumulated = b""
                    
                    total_bits_payload += 1 + b_key
                else:
                    current_lit_accumulated += frag
        else:
            current_lit_accumulated += word
        
        last_idx = end

    current_lit_accumulated += raw_data[last_idx:]
    if current_lit_accumulated:
        total_bits_payload += 1 + (len(current_lit_accumulated) * b_unit) + b_unit

    fragments_storage_cost = sum((len(frag) * b_unit) + b_unit for frag in final_dict.keys())

    protocol_prefix = 6 
    if n_entries > 0:
        # k 0s + k bits, the "bits" part necessarily starts with 1
        
        k = math.floor(math.log2(n_entries)) + 1
        bits_for_count = 2 * k
    else:
        bits_for_count = 1 # a "1" is enough -> no "0" read, the "1" is skipped
    
    # to specify how many bits for the single char
    # 11110 -> 4 bits (0 = escape bit)
    b_char_overhead = b_unit + 1
    
    dict_header_cost = protocol_prefix + bits_for_count + b_char_overhead
    
    original_bits = len(raw_data) * 8
    final_compressed_size = total_bits_payload + fragments_storage_cost + dict_header_cost
    
    return original_bits - final_compressed_size

def main():
    raw_data = load_binary_from_input_file()
    
    unique_chars = len(set(raw_data))
    bits_needed = math.ceil(math.log2(unique_chars + 1))
    
    words = WORD_REGEX.findall(raw_data)
    word_freq, all_parts, frag_occ = build_data(words)
    
    final_dict = create_dict(word_freq, all_parts, frag_occ, bits_needed)
    
    real_saving = calc_final_saving(raw_data, final_dict, all_parts, bits_needed)
    print_results(final_dict, real_saving, len(raw_data), bits_needed)

if __name__ == "__main__":
    main()