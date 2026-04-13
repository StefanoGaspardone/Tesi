import re
import sys
import math

B_CHAR = 7 # ?
B_TYPE = 2
B_ETX = 7

def get_partitions(word: str) -> list:
    partitions = []
    n = len(word)
    
    for i in range(2 ** (n - 1)):
        start = 0
        current_partition = []
        
        for j in range(n - 1):
            if (i >> j) & 1:
                current_partition.append(word[start:j+1])
                start = j + 1
                
        current_partition.append(word[start:])
        partitions.append(current_partition)
        
    # print(partitions)
    return partitions

def calculate_u_di(substr: str, n_occ: int, b_key: int) -> int:
    l_bits = len(substr) * B_CHAR
    
    saving = n_occ * l_bits
    storage_cost = l_bits + B_ETX + B_TYPE
    pointer_cost = n_occ * (1 + b_key)
    
    return saving - storage_cost - pointer_cost

def create_dict(unique_words: list, words_list: list, all_partitions: dict) -> tuple:
    current_b_key = math.ceil(math.log2(len(unique_words))) if unique_words else 1
    stable = False
    final_dict_entries = {}

    while not stable:
        substring_counts = {}
        for word in words_list:
            possible_fragments = set()
            
            for p in all_partitions[word]:
                for fragment in p:
                    if len(fragment) > 1:
                        possible_fragments.add(fragment)
            
            for f in possible_fragments:
                substring_counts[f] = substring_counts.get(f, 0) + word.count(f)

        candidate_scores = {}
        for sub, occ in substring_counts.items():
            score = calculate_u_di(sub, occ, current_b_key)
            
            if score > 0:
                candidate_scores[sub] = score

        real_usage = {}
        for word in words_list:
            best_p = None
            max_s = -1
            
            for p in all_partitions[word]:
                current_s = sum(candidate_scores.get(sub, 0) for sub in p)
                
                if current_s > max_s:
                    max_s = current_s
                    best_p = p
            
            if max_s > 0:
                for fragment in best_p:
                    if fragment in candidate_scores:
                        real_usage[fragment] = real_usage.get(fragment, 0) + 1

        new_n_entries = len(real_usage)
        new_b_key = math.ceil(math.log2(new_n_entries)) if new_n_entries > 0 else 1
        
        if new_b_key == current_b_key:
            stable = True
            final_dict_entries = real_usage
        else:
            current_b_key = new_b_key
            
    return (current_b_key, final_dict_entries)

def main():
    try:
        if len(sys.argv) > 1:
            file = sys.argv[1]
        else:
            file = input("Enter file name: ")
            
        with open(f"inputs/{file}", 'r', encoding = 'utf-8') as f:
            text = f.read()
    except FileNotFoundError:
        print("The file does not exist")
        exit(1)
        
    word_regex = r'[a-zA-Z0-9_\.\-]+'
    words_list = re.findall(word_regex, text)
    unique_words = list(dict.fromkeys(words_list))
    
    all_partitions = {}
    for word in words_list:
        all_partitions[word] = get_partitions(word)
    
    b_key, final_dict = create_dict(unique_words, words_list, all_partitions)

    # --- OUTPUT FINALE ---
    print(f"B_KEY STABILE: {b_key} bit")
    print(f"Voci effettive nel dizionario: {len(final_dict)}")
    print("-" * 30)
    for sub, count in sorted(final_dict.items(), key=lambda x: x[1], reverse=True):
        print(f"Frammento: {sub:15} | Usi reali: {count}")
    
if __name__ == "__main__":
    main()