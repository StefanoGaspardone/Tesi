import math
import re
import sys
from collections import Counter

# --- CONFIGURAZIONE ---
B_UNIT, B_FLAG, B_TYPE, B_ETX = 8, 1, 2, 8
MIN_FRAGMENT_LENGTH = 3
BLOCK_OPTIONS = (8, 16, 32, 64)
WORD_REGEX = re.compile(rb"[a-zA-Z0-9_\-]+")

def load_data():
    """Carica il file dagli argomenti o da input manuale."""
    try:
        path = sys.argv[1] if len(sys.argv) > 1 else input("File: ")
        with open(f"inputs/{path}", "rb") as f:
            return f.read()
    except FileNotFoundError:
        sys.exit("Errore: File non trovato.")

def get_partitions(word):
    """Scompone una parola in tutti i modi possibili (Potere risolutivo)."""
    n = len(word)
    parts = []
    for i in range(1 << (n - 1)):
        start, current = 0, []
        for j in range(n - 1):
            if (i >> j) & 1:
                current.append(word[start : j+1])
                start = j + 1
        current.append(word[start:])
        parts.append(current)
    return parts

def get_key_cost(pos, b_size):
    """Calcola il costo del puntatore VLC (Unario + Indice Blocco)."""
    return (pos // b_size + 1) + math.ceil(math.log2(b_size))

def score_fragment(frag, count, pos, b_size):
    """Calcola il guadagno netto (Risparmio - Costo Dizionario)."""
    gain_per_hit = (len(frag) * B_UNIT) - (B_FLAG + get_key_cost(pos, b_size))
    storage_cost = (len(frag) * B_UNIT) + B_ETX + B_TYPE
    return (count * gain_per_hit) - storage_cost

def find_best_partition(word, partitions, gains):
    """Sceglie la combinazione di frammenti più vantaggiosa per una parola."""
    best_partition, max_score = None, -1
    for p in partitions:
        score = sum(gains.get(f, 0) for f in p)
        if score > max_score:
            max_score, best_partition = score, p
    return best_partition if max_score > 0 else None

def evaluate_strategy(word_freq, all_parts, candidates, b_size):
    """Valuta il risparmio totale per una specifica dimensione di blocco."""
    # 1. Filtra frammenti con guadagno unitario positivo
    unit_gains = {f: (len(f)*B_UNIT - (B_FLAG + get_key_cost(i, b_size))) 
                  for i, f in enumerate(candidates)}
    unit_gains = {f: g for f, g in unit_gains.items() if g > 0}

    # 2. Conta l'uso reale dei frammenti scegliendo le partizioni migliori
    usage = Counter()
    for word, freq in word_freq.items():
        best_p = find_best_partition(word, all_parts[word], unit_gains)
        if best_p:
            for f in best_p:
                if f in unit_gains: usage[f] += freq

    # 3. Calcola risparmio finale e filtra chi non è più profittevole dopo il riordino
    sorted_usage = usage.most_common()
    final_list, total_saving = [], 0
    for pos, (f, count) in enumerate(sorted_usage):
        s = score_fragment(f, count, pos, b_size)
        if s > 0:
            total_saving += s
            final_list.append((f, count))
    
    return total_saving, final_list

def main():
    raw_data = load_data()
    words = WORD_REGEX.findall(raw_data)
    word_freq = Counter(words)
    
    # Pre-calcolo partizioni e frammenti potenziali
    all_parts = {w: get_partitions(w) for w in word_freq}
    sub_counts = Counter()
    for w, freq in word_freq.items():
        unique_frags = {f for p in all_parts[w] for f in p if len(f) >= MIN_FRAGMENT_LENGTH}
        for f in unique_frags: sub_counts[f] += (w.count(f) * freq)
    
    current_candidates = [f for f, _ in sub_counts.most_common()]
    best_glob_saving, best_glob_dict, best_glob_block = -1, {}, 8

    # Ciclo di ottimizzazione (Convergenza)
    while True:
        results = [(*evaluate_strategy(word_freq, all_parts, current_candidates, b), b) for b in BLOCK_OPTIONS]
        saving, f_list, b_size = max(results, key=lambda x: x[0])

        if saving <= best_glob_saving: break
        
        best_glob_saving, best_glob_block = saving, b_size
        best_glob_dict = dict(f_list)
        current_candidates = [f for f, _ in f_list]
        print(f"Iterazione: Saving {saving} bit | Blocchi: {b_size}")

    # Output finale
    print(f"\nCompressione Finale: {(best_glob_saving / (len(raw_data)*8)) * 100:.2f}%")
    print(f"Dizionario: {len(best_glob_dict)} elementi | Blocco ottimale: {best_glob_block}")

if __name__ == "__main__":
    main()