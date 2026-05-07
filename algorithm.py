import re
import sys

B_FLAG = 1
B_CHAR = 8

def load_input_file() -> bytes:
    try:
        file_name = sys.argv[1] if len(sys.argv) > 1 else input("Enter file name: ")

        with open(f"inputs/{file_name}", "rb") as file:
            return file.read()
    except FileNotFoundError:
        print("The file does not exist")
        sys.exit(1)
        
def get_strings(data: bytes) -> list[bytes]:
    strings = []
    is_string = False
    current_string = bytearray()
    
    for byte in data:
        if byte == ord(b'"'):
            if is_string:
                string = bytes(current_string)
                strings.append(string)
                
                current_string = bytearray()
                is_string = False
            else:
                is_string = True
        elif is_string:
            current_string.append(byte)
            
    return strings

def split_strings(strings: list[bytes]) -> tuple[list[bytes], dict[bytes, int]]:
    char_map = {}
    
    for s in strings:
        for i in range(len(s)):
            char = s[i : i+1] 
            if char not in char_map:
                char_map[char] = {'pre': [], 'post': [], 'count': 0}
            
            char_map[char]['count'] += 1
            
            if i > 0:
                char_map[char]['pre'].append(s[i-1])
            if i < len(s) - 1:
                char_map[char]['post'].append(s[i+1])
                
    separators = []
    final_dict = {}
    
    for char, data in char_map.items():
        pre_unique = len(set(data['pre'])) == len(data['pre'])
        post_unique = len(set(data['post'])) == len(data['post'])
        
        if pre_unique and post_unique:
            separators.append(char)
            final_dict[char] = data['count']
            
    if not separators:
        return strings, {}

    regex = b'|'.join(map(re.escape, separators))
    
    new_strings = []
    for s in strings:
        parts = re.split(regex, s)
        
        for p in parts:
            if p:
                new_strings.append(p)

    return new_strings, final_dict

def get_partitions(strings: list[bytes]) -> dict[bytes, list[list[bytes]]]:
    part = {}
    
    for s in strings:
        partitions = []
        
        for i in range(0, 1 << (len(s) - 1)):
            partitions.append(get_partition(s, i))
        
        part[s] = partitions
    
    return part

def get_partition(str: bytes, idx: int) -> list[bytes]:
    n = len(str)
    start = 0
    partition = []

    for j in range(n - 1):
        if (idx >> j) & 1:
            partition.append(str[start : j + 1])
            start = j + 1

    partition.append(str[start:])
    return partition

def calculate_u_di(fragment: bytes, freq: int, b_key: int) -> int:
    l_bits = len(fragment) * B_CHAR

    saving = freq * l_bits
    storage_cost = l_bits + B_CHAR # B_ETX = B_CHAR; B_TYPE is now useless, since an optimized encoding for chars is used (?)
    pointer_cost = freq * (B_FLAG + b_key)
    
    return saving - storage_cost - pointer_cost

def print_stats(strings: list[bytes]):
    print(f"> {len(strings)} strings")
    
    combination = 1
    avg_len = 0
    for s in strings:
        n = len(s)
        
        avg_len += n
        combination *= 1 << (n - 1)
        
    print(f"> {round(avg_len / len(strings))} avg string length")
    print(f"> {"{:.3e}".format(combination)} combinations\n\n")

def main():
    data = load_input_file()
    
    strings = get_strings(data)
    print_stats(strings)
    
    strings, dictionary = split_strings(strings)
    print_stats(strings)
    
    print(strings)
    print(dictionary)
    
    # partitions = get_partitions(strings)
    # print(partitions)

if __name__ == "__main__":
    main()