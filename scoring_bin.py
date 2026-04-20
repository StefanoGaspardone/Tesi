import math
import re
import sys
from collections import Counter

B_UNIT = 8
B_FLAG = 1
B_TYPE = 2
B_ETX = 8
WORD_REGEX = re.compile(rb"[a-zA-Z0-9_\-]+")

def load_binary_from_input_file() -> bytes:
    """Read an input file from the inputs folder and return its raw bytes."""

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
    """Build core data structures: frequencies, partitions, and fragment occurrences."""

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

def calculate_u_di(fragment: bytes, count: int, b_key: int) -> int:
    """Compute the bit gain of encoding a fragment with the current key width."""

    l_bits = len(fragment) * B_UNIT

    saving = count * l_bits
    storage_cost = l_bits + B_ETX + B_TYPE
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

def normalize_dictionary(usage_counts: dict[bytes, int]) -> tuple[int, dict[bytes, int], int]:
    """Iteratively prune non-profitable entries until the dictionary stabilizes."""

    current = usage_counts
    while True:
        if not current:
            return 1, {}, 0

        b_key = get_key_bits(len(current))
        filtered = {
            fragment: occ
            for fragment, occ in current.items()
            if calculate_u_di(fragment, occ, b_key) > 0
        }

        if len(filtered) == len(current):
            total_saving = sum(calculate_u_di(fragment, occ, b_key) for fragment, occ in filtered.items())
            return b_key, filtered, total_saving

        current = filtered

def create_dict(word_frequencies: Counter[bytes], all_partitions: dict[bytes, list[list[bytes]]], fragment_occurrences: dict[bytes, dict[bytes, int]]) -> tuple[int, dict[bytes, int]]:
    """Run the optimization loop to stabilize key width and dictionary entries, in order to create the final dict."""

    b_key = get_key_bits(len(word_frequencies))
    best_saving = -1
    best_dict = {}
    substring_counts = aggregate_substring_counts(word_frequencies, fragment_occurrences)

    while True:
        candidates = {
            sub: score
            for sub, occ in substring_counts.items()
            if (score := calculate_u_di(sub, occ, b_key)) > 0
        }

        if not candidates:
            break

        real_usage: Counter[bytes] = Counter()
        for word, freq in word_frequencies.items():
            best_partition = get_best_partition(all_partitions[word], candidates)
            
            if best_partition is None:
                continue

            for fragment in best_partition:
                if fragment in candidates:
                    real_usage[fragment] += freq

        eff_key, final_usage, saving = normalize_dictionary(dict(real_usage))
        print(f"Saving: {saving} | Key: {eff_key} | Entries: {len(final_usage)}")

        if not final_usage or saving <= best_saving:
            break

        best_saving, best_dict, b_key = saving, final_usage, eff_key

    return best_saving, best_dict

def print_results(final_dict: dict[bytes, int], total_saving: int, initial_bits: int) -> None:
    effective_b_key = get_key_bits(len(final_dict))

    rows = [
        (pos, fragment, count, calculate_u_di(fragment, count, effective_b_key))
        for pos, (fragment, count) in enumerate(sorted(final_dict.items(), key = lambda item: item[1], reverse = True))
    ]

    pos_width = max(3, len(str(len(rows) - 1)) if rows else 3)
    fragment_width = max(8, max((len(fragment) for _, fragment, _, _ in rows), default = 8))
    uses_width = max(4, max((len(str(count)) for _, _, count, _ in rows), default = 4))
    saving_width = max(10, max((len(str(saving)) for _, _, _, saving in rows), default = 10))

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
    
    print(f"\nTotal savings: {total_saving} bit")
    print(f"Total original bits: {initial_bits} bits")
    
    perc = (total_saving / initial_bits) * 100
    print(f"Compression rate: {perc:.2f}%")

def main() -> None:
    raw_data = load_binary_from_input_file()
    words = WORD_REGEX.findall(raw_data)

    word_frequencies, all_partitions, fragment_occurrences = build_data(words)
    total_saving, final_dict = create_dict(word_frequencies, all_partitions, fragment_occurrences)

    print_results(final_dict, total_saving, len(raw_data) * B_UNIT)    

if __name__ == "__main__":
    main()