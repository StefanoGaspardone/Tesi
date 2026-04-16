import math
import re
import sys
from collections import Counter

B_CHAR = 7
B_TYPE = 2
B_ETX = 7
WORD_REGEX = r"[a-zA-Z0-9_\.\-]+"


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

    for mask in range(2 ** (n - 1)):
        start = 0
        current_partition: list[str] = []

        for j in range(n - 1):
            if (mask >> j) & 1:
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

        possible_fragments = { fragment for partition in partitions for fragment in partition if len(fragment) > 1 }
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


def stabilize_b_key(n_unique_words: int, word_frequencies: Counter, all_partitions: dict[str, list[list[str]]], fragment_occurrences: dict[str, dict[str, int]]) -> tuple[int, dict[str, int]]:
    """Iteratively adjusts key bits and stops when total saving no longer improves."""
    
    current_b_key = math.ceil(math.log2(n_unique_words)) if n_unique_words > 0 else 1

    best_results = (current_b_key, {})
    max_total_saving = -1
    
    substring_counts = aggregate_substring_counts(word_frequencies, fragment_occurrences)

    while True:
        candidate_scores = {
            sub: s for sub, occ in substring_counts.items() 
            if (s := calculate_u_di(sub, occ, current_b_key)) > 0
        }
                
        if not candidate_scores: break
        
        real_usage = compute_real_usage(word_frequencies, all_partitions, candidate_scores)
        final_usage = {
            f: occ for f, occ in real_usage.items() 
            if calculate_u_di(f, occ, current_b_key) > 0
        }

        current_saving = sum(calculate_u_di(f, occ, current_b_key) for f, occ in final_usage.items())
        print(f"{math.ceil(math.log2(len(final_usage))) if len(final_usage) > 0 else 1} bits -> saving {current_saving} bits")
        
        if current_saving > max_total_saving:
            max_total_saving = current_saving
            best_results = (current_b_key, final_usage)
            
            new_n_entries = len(final_usage)
            current_b_key = math.ceil(math.log2(new_n_entries)) if new_n_entries > 0 else 1
        else:
            break
        
    return best_results


def print_results(b_key: int, final_dict: dict[str, int]) -> None:
    rows = [
        (pos, fragment, count, calculate_u_di(fragment, count, b_key))
        for pos, (fragment, count) in enumerate(sorted(final_dict.items(), key=lambda item: item[1], reverse=True))
    ]

    pos_width = max(3, len(str(len(rows) - 1)) if rows else 3)
    fragment_width = max(8, max((len(fragment) for _, fragment, _, _ in rows), default=8))
    uses_width = max(4, max((len(str(count)) for _, _, count, _ in rows), default=4))
    saving_width = max(10, max((len(str(saving)) for _, _, _, saving in rows), default=10))

    table_width = pos_width + fragment_width + uses_width + saving_width + 13
    border = "+" + "-" * (table_width - 2) + "+"

    print(f"\nFinal Dict Length: {len(final_dict)}\n")
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
    
    b_key, final_dict = stabilize_b_key(
        n_unique_words = len(word_frequencies),
        word_frequencies = word_frequencies,
        all_partitions = all_partitions,
        fragment_occurrences = fragment_occurrences,
    )

    print_results(b_key, final_dict)


if __name__ == "__main__":
    main()