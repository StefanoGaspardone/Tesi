import ast
import os
import re


def split_strings(strings: list[bytes]) -> tuple[list[bytes], dict[bytes, int]]:
    char_map = {}

    for s in strings:
        for i in range(len(s)):
            char = s[i : i + 1]

            if char not in char_map:
                char_map[char] = {"pre": [], "post": [], "count": 0}

            char_map[char]["count"] += 1

            if i > 0:
                char_map[char]["pre"].append(s[i - 1])
            if i < len(s) - 1:
                char_map[char]["post"].append(s[i + 1])

    separators = []
    initial_dict = {}

    for char, data in char_map.items():
        pre_unique = len(set(data["pre"])) == len(data["pre"])
        post_unique = len(set(data["post"])) == len(data["post"])

        if pre_unique and post_unique:
            separators.append(char)
            initial_dict[char] = data["count"]

    if not separators:
        return strings, {}

    regex = b"|".join(map(re.escape, separators))
    new_strings = []

    for s in strings:
        for p in re.split(regex, s):
            if p:
                new_strings.append(p)

    return new_strings, initial_dict


def get_partitions(s: bytes) -> list:
    n = len(s)
    partitions = []

    for mask in range(1 << (n - 1)):
        partition = []
        start = 0

        for j in range(n - 1):
            if (mask >> j) & 1:
                partition.append(s[start : j + 1])
                start = j + 1

        partition.append(s[start:])
        partitions.append(partition)

    return partitions


def read_strings_text(path: str) -> list:
    out = []

    full_path = os.path.join("..", "inputs", path)

    with open(full_path, "r", encoding="utf-8") as f:
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


def count_partition_combinations(byte_strings: list[bytes]) -> int:
    """Calcola il numero totale di combinazioni di partizioni per una lista di stringhe di byte."""
    total_combinations = 1
    for s in byte_strings:
        n = len(s)
        if n > 0:
            total_combinations *= 1 << (n - 1)
    return total_combinations


def format_scientific(number: int, decimals: int = 3) -> str:
    """Formatta un intero grande in notazione scientifica tipo 'X.XXX * 10^Y'."""
    if number == 0:
        return "0"

    s = str(number)
    exponent = len(s) - 1
    if exponent == 0:
        return s

    mantissa = f"{s[0]}.{s[1:1 + decimals]}".rstrip(".")
    return f"{mantissa} * 10^{exponent}"


def calc_avg_char_length(strings: list[str]) -> int:
    """Calcola la lunghezza media in caratteri (come numero intero)."""
    if not strings:
        return 0
    total_chars = sum(len(s) for s in strings)
    return round(total_chars / len(strings))


def main():
    path = "colonnina.txt"  # Sostituisci con il percorso del tuo file
    raw_strings = read_strings_text(path)
    original_bytes = to_utf8_bytes(raw_strings)

    # Elaborazione tramite split_strings
    split_bytes, separators_dict = split_strings(original_bytes)

    # Convertiamo i byte splittati di nuovo in stringhe di caratteri
    split_strings_text = [b.decode("utf-8", errors="replace") for b in split_bytes]

    # Calcolo delle combinazioni
    orig_combinations = count_partition_combinations(original_bytes)
    split_combinations = count_partition_combinations(split_bytes)

    # Calcolo delle lunghezze medie in caratteri (interi)
    orig_avg_chars = calc_avg_char_length(raw_strings)
    split_avg_chars = calc_avg_char_length(split_strings_text)

    # Stampa dei risultati (3 cifre decimali passate a format_scientific)
    print(
        f"Separatori individuati ({len(separators_dict)}):"
        f" {list(separators_dict.keys())}\n"
    )

    print("--- PRIMA DELLO SPLIT ---")
    print(f"Numero di stringhe : {len(original_bytes)}")
    print(f"Lunghezza media    : {orig_avg_chars} caratteri")
    print(f"Combinazioni tot.  : {format_scientific(orig_combinations, decimals=3)}\n")

    print("--- DOPO LO SPLIT ---")
    print(f"Numero di stringhe : {len(split_bytes)}")
    print(f"Lunghezza media    : {split_avg_chars} caratteri")
    print(f"Combinazioni tot.  : {format_scientific(split_combinations, decimals=3)}")


if __name__ == "__main__":
    main()