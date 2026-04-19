import math
import re
import sys
from collections import Counter


B_UNIT = 8
B_FLAG = 1
B_TYPE = 2
B_ETX = 8
WORD_REGEX_BIN = re.compile(rb"[a-zA-Z0-9_\-]+")


def load_binary_from_input_file() -> bytes:
    """Reads the input text file and returns its full content as a string."""
    
    try:
        file_name = sys.argv[1] if len(sys.argv) > 1 else input("Enter file name: ")
        
        with open(f"inputs/{file_name}", "rb") as file:
            return file.read()
    except FileNotFoundError:
        print("The file does not exist")
        sys.exit(1)


def get_partitions(word: bytes) -> list[list[bytes]]:
    """Generates all possible ways to split a word into contiguous fragments."""
    
    partitions: list[list[bytes]] = []
    n = len(word)
    
    for i in range(2 ** (n - 1)):
        start = 0
        current_partition: list[bytes] = []
        
        for j in range(n - 1):
            if (i >> j) & 1:
                current_partition.append(word[start : j+1])
                start = j + 1
        
        current_partition.append(word[start:])
        partitions.append(current_partition)
    
    return partitions


def build_data(words: list[bytes]) -> tuple[Counter, dict[bytes, list[list[bytes]]], dict[bytes, dict[bytes, int]]]:
    """Builds the base data: word counts, all partitions, and fragment occurrences per word."""
    
    word_frequencies = Counter(words)
    all_partitions: dict[bytes, list[list[bytes]]] = {}
    fragment_occurrences: dict[bytes, dict[bytes, int]] = {}

    for word in word_frequencies:
        partitions = get_partitions(word)
        all_partitions[word] = partitions
        
        possible_fragments = { frag for part in partitions for frag in part }
        fragment_occurrences[word] = {frag: word.count(frag) for frag in possible_fragments}

    return word_frequencies, all_partitions, fragment_occurrences


def aggregate_substring_counts(word_frequencies: Counter, fragment_occurrences: dict[bytes, dict[bytes, int]]) -> dict[bytes, int]:
    """Computes how many times each fragment appears in the whole text."""
    
    substring_counts: dict[bytes, int] = {}
    
    for word, occ_map in fragment_occurrences.items():
        freq = word_frequencies[word]
        
        for frag, occ in occ_map.items():
            substring_counts[frag] = substring_counts.get(frag, 0) + (occ * freq)
    
    return substring_counts


def compute_real_usage(word_frequencies: Counter, all_partitions: dict[bytes, list[list[bytes]]], candidate_scores: dict[bytes, int]) -> dict[bytes, int]:
    """Chooses, for each word, the best partition by score and count the real fragment usage."""
    
    real_usage: dict[bytes, int] = {}
    
    for word, frequency in word_frequencies.items():
        best_partition = None
        best_score = -1

        for partition in all_partitions[word]:
            current_score = sum(candidate_scores.get(frag, 0) for frag in partition)
            
            if current_score > best_score:
                best_score = current_score
                best_partition = partition

        if best_score <= 0 or best_partition is None:
            continue

        for frag in best_partition:
            if frag in candidate_scores:
                real_usage[frag] = real_usage.get(frag, 0) + frequency
    
    return real_usage


def calculate_u_di(fragment: bytes, n_occ: int, b_key: int) -> int:
    """Calculate the utility score of a fragment using savings, storage cost, and pointer cost."""
    
    l_bits = len(fragment) * B_UNIT
    
    saving = n_occ * l_bits
    storage_cost = l_bits + B_ETX + B_TYPE
    pointer_cost = n_occ * (B_FLAG + b_key)
    
    return saving - storage_cost - pointer_cost


def compute_key_bits(n_entries: int) -> int:
    """Returns the number of bits needed to encode a dictionary of this size."""
    
    return math.ceil(math.log2(n_entries)) if n_entries > 0 else 1


def normalize_dict(usage: dict[bytes, int]) -> tuple[int, dict[bytes, int], int]:
    """Prunes fragments and returns effective key width, filtered usage, and total saving."""
    
    current_usage = usage
    
    while True:
        if not current_usage:
            return 1, {}, 0
        
        effective_b_key = compute_key_bits(len(current_usage))
        filtered_usage = {}
        current_saving = 0
        
        for frag, occ in current_usage.items():
            score = calculate_u_di(frag, occ, effective_b_key)
            
            if score > 0:
                filtered_usage[frag] = occ
                current_saving += score
        
        if len(filtered_usage) == len(current_usage):
            return effective_b_key, filtered_usage, current_saving
        
        current_usage = filtered_usage


def stabilize_b_key(word_frequencies: Counter, all_partitions: dict[bytes, list[list[bytes]]], fragment_occurrences: dict[bytes, dict[bytes, int]]) -> tuple[int, dict[bytes, int]]:
    """Adjusts key bits and keeps iterating while total savings keep improving."""
    
    current_b_key = compute_key_bits(len(word_frequencies))
    best_results = (current_b_key, {})
    max_total_saving = -1
    substring_counts = aggregate_substring_counts(word_frequencies, fragment_occurrences)

    while True:
        candidate_scores = {
            sub: score for sub, occ in substring_counts.items()
            if (score := calculate_u_di(sub, occ, current_b_key)) > 0
        }
        
        if not candidate_scores:
            break

        real_usage = compute_real_usage(word_frequencies, all_partitions, candidate_scores)
        eff_b_key, final_usage, cur_saving = normalize_dict(real_usage)

        if not final_usage:
            break
        
        print(f"Saving: {cur_saving} bits | Key: {eff_b_key} | entries: {len(final_usage)}")

        if cur_saving <= max_total_saving:
            break
        
        max_total_saving = cur_saving
        best_results = (eff_b_key, final_usage)
        
        if eff_b_key == current_b_key:
            break
        
        current_b_key = eff_b_key

    return best_results


def print_results(final_dict: dict[bytes, int]) -> None:
    effective_b_key = compute_key_bits(len(final_dict))

    rows = [
        (pos, fragment, count, calculate_u_di(fragment, count, effective_b_key))
        for pos, (fragment, count) in enumerate(sorted(final_dict.items(), key=lambda item: item[1], reverse=True))
    ]

    pos_width = max(3, len(str(len(rows) - 1)) if rows else 3)
    fragment_width = max(8, max((len(fragment) for _, fragment, _, _ in rows), default=8))
    uses_width = max(4, max((len(str(count)) for _, _, count, _ in rows), default=4))
    saving_width = max(10, max((len(str(saving)) for _, _, _, saving in rows), default=10))

    table_width = pos_width + fragment_width + uses_width + saving_width + 13
    border = "+" + "-" * (table_width - 2) + "+"

    print(f"\nFinal Dict Length: {len(final_dict)}")
    print(f"Key bits: {effective_b_key}")
    print(border)
    print(f"| {'Pos':>{pos_width}} | {'Fragment':<{fragment_width}} | {'Uses':>{uses_width}} | {'Saving':>{saving_width}} |")
    print(border)

    for pos, fragment, count, saving in rows:
        display_frag = fragment.decode('utf-8', errors = 'replace')
        print(f"| {pos:>{pos_width}} | {display_frag:<{fragment_width}} | {count:>{uses_width}} | {saving:>{saving_width}} |")
    print(border)
    
    total_bits_saved = sum(saving for _, _, _, saving in rows)
    print(f"\nTotal savings: {total_bits_saved} bit")


def main():
    raw_data = load_binary_from_input_file()
    words = WORD_REGEX_BIN.findall(raw_data)
    
    word_frequencies, all_partitions, fragment_occurrences = build_data(words)
    
    _key_bit, final_dict = stabilize_b_key(word_frequencies, all_partitions, fragment_occurrences)
    
    print_results(final_dict)


if __name__ == "__main__":
    main()