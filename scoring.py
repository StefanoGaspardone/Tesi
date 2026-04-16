import math
import re
import sys
from collections import Counter


B_CHAR = 7
B_TYPE = 2
B_ETX = 7
WORD_REGEX = r"[a-zA-Z0-9_\-]+"


def load_text_from_input_file() -> str:
    """Reads the input text file and returns its full content as a string."""
    
    try:
        file_name = sys.argv[1] if len(sys.argv) > 1 else input("Enter file name: ")
        
        with open(f"inputs/{file_name}", "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        print("The file does not exist")
        raise SystemExit(1)


def get_partitions(word: str) -> list[list[str]]:
    """Generates all possible ways to split a word into contiguous fragments."""
    
    partitions: list[list[str]] = []
    n = len(word)

    for i in range(2 ** (n - 1)):
        start = 0
        current_partition: list[str] = []

        for j in range(n - 1):
            if (i >> j) & 1:
                current_partition.append(word[start : j + 1])
                start = j + 1

        current_partition.append(word[start:])
        partitions.append(current_partition)

    return partitions


def build_data(words: list[str]) -> tuple[Counter, dict[str, list[list[str]]], dict[str, dict[str, int]]]:
    """Builds the base data: word counts, all partitions, and fragment occurrences per word."""
    
    word_frequencies = Counter(words)
    all_partitions: dict[str, list[list[str]]] = {}
    fragment_occurrences: dict[str, dict[str, int]] = {}

    for word in word_frequencies:
        partitions = get_partitions(word)
        all_partitions[word] = partitions

        possible_fragments = { fragment for partition in partitions for fragment in partition }
        fragment_occurrences[word] = {fragment: word.count(fragment) for fragment in possible_fragments}

    return word_frequencies, all_partitions, fragment_occurrences


def aggregate_substring_counts(word_frequencies: Counter, fragment_occurrences: dict[str, dict[str, int]]) -> dict[str, int]:
    """Computes how many times each fragment appears in the whole text."""
    
    substring_counts: dict[str, int] = {}
    
    for word, occurrences_map in fragment_occurrences.items():
        frequency = word_frequencies[word]
        
        for fragment, occurrences in occurrences_map.items():
            substring_counts[fragment] = substring_counts.get(fragment, 0) + (occurrences * frequency)
    
    return substring_counts


def compute_real_usage(word_frequencies: Counter, all_partitions: dict[str, list[list[str]]], candidate_scores: dict[str, int]) -> dict[str, int]:
    """Chooses, for each word, the best partition by score and count the real fragment usage."""
    
    real_usage: dict[str, int] = {}

    for word, frequency in word_frequencies.items():
        best_partition: list[str] | None = None
        best_score = -1

        for partition in all_partitions[word]:
            current_score = sum(candidate_scores.get(fragment, 0) for fragment in partition)
            
            if current_score > best_score:
                best_score = current_score
                best_partition = partition

        if best_score <= 0 or best_partition is None:
            continue

        for fragment in best_partition:
            if fragment in candidate_scores:
                real_usage[fragment] = real_usage.get(fragment, 0) + frequency

    return real_usage


def calculate_u_di(substr: str, n_occ: int, b_key: int) -> int:
    """Calculate the utility score of a fragment using savings, storage cost, and pointer cost."""
    
    l_bits = len(substr) * B_CHAR
    
    saving = n_occ * l_bits
    storage_cost = l_bits + B_ETX + B_TYPE
    pointer_cost = n_occ * (1 + b_key)
    
    return saving - storage_cost - pointer_cost


def compute_key_bits(n_entries: int) -> int:
    """Returns the number of bits needed to encode a dictionary of this size."""

    return math.ceil(math.log2(n_entries)) if n_entries > 0 else 1


def normalize_dict(usage: dict[str, int]) -> tuple[int, dict[str, int], int]:
    """Prunes fragments and returns effective key width, filtered usage, and total saving."""

    current_usage = usage

    while True:
        if not current_usage:
            return 1, {}, 0

        effective_b_key = compute_key_bits(len(current_usage))
        filtered_usage: dict[str, int] = {}
        current_saving = 0

        for fragment, occurrences in current_usage.items():
            saving = calculate_u_di(fragment, occurrences, effective_b_key)

            if saving > 0:
                filtered_usage[fragment] = occurrences
                current_saving += saving

        if len(filtered_usage) == len(current_usage):
            return effective_b_key, filtered_usage, current_saving

        current_usage = filtered_usage


def stabilize_b_key(n_unique_words: int, word_frequencies: Counter, all_partitions: dict[str, list[list[str]]], fragment_occurrences: dict[str, dict[str, int]]) -> tuple[int, dict[str, int]]:
    """Adjusts key bits and keeps iterating while total savings keep improving."""

    current_b_key = compute_key_bits(n_unique_words)
    best_results = (current_b_key, {})
    max_total_saving = -1
    substring_counts = aggregate_substring_counts(word_frequencies, fragment_occurrences)

    while True:
        candidate_scores = {
            sub: score
            for sub, occ in substring_counts.items()
            if (score := calculate_u_di(sub, occ, current_b_key)) > 0
        }

        if not candidate_scores:
            break

        real_usage = compute_real_usage(word_frequencies, all_partitions, candidate_scores)
        effective_b_key, final_usage, current_saving = normalize_dict(real_usage)

        if not final_usage:
            break

        print(f"Saving: {current_saving} bits (key bits {effective_b_key}): {len(final_usage)} dict entries")

        if current_saving <= max_total_saving:
            break

        max_total_saving = current_saving
        best_results = (effective_b_key, final_usage)

        if effective_b_key == current_b_key:
            break

        current_b_key = effective_b_key

    return best_results


def print_results(final_dict: dict[str, int]) -> None:
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
        print(f"| {pos:>{pos_width}} | {fragment:<{fragment_width}} | {count:>{uses_width}} | {saving:>{saving_width}} |")
    print(border)
    
    total_bits_saved = sum(saving for _, _, _, saving in rows)
    print(f"\nTotal savings: {total_bits_saved} bit")


def main() -> None:
    text = load_text_from_input_file()
    words = re.findall(WORD_REGEX, text)

    word_frequencies, all_partitions, fragment_occurrences = build_data(words)
    
    _, final_dict = stabilize_b_key(
        n_unique_words = len(word_frequencies),
        word_frequencies = word_frequencies,
        all_partitions = all_partitions,
        fragment_occurrences = fragment_occurrences,
    )

    print_results(final_dict)


if __name__ == "__main__":
    main()